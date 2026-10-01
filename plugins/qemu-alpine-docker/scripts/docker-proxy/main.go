// Docker CLI proxy: filter local contexts with Docker's upstream matcher and build over SSH.
package main

import (
	"archive/tar"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"

	"github.com/moby/patternmatcher"
	"github.com/moby/patternmatcher/ignorefile"
)

func archiveContext(root, dockerfile string, output io.Writer) error {
	root, err := filepath.Abs(root)
	if err != nil {
		return err
	}
	if filepath.IsAbs(dockerfile) {
		dockerfile, err = filepath.Rel(root, dockerfile)
		if err != nil {
			return err
		}
	}
	dockerfile = filepath.ToSlash(filepath.Clean(dockerfile))
	if dockerfile == ".." || strings.HasPrefix(dockerfile, "../") {
		return fmt.Errorf("Dockerfile must be inside the context")
	}
	ignoreName := ".dockerignore"
	if _, err := os.Stat(filepath.Join(root, dockerfile+".dockerignore")); err == nil {
		ignoreName = dockerfile + ".dockerignore"
	}
	patterns := []string{}
	if file, err := os.Open(filepath.Join(root, ignoreName)); err == nil {
		patterns, err = ignorefile.ReadAll(file)
		file.Close()
		if err != nil {
			return err
		}
	} else if !os.IsNotExist(err) {
		return err
	}
	matcher, err := patternmatcher.New(patterns)
	if err != nil {
		return err
	}
	writer := tar.NewWriter(output)
	err = filepath.WalkDir(root, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		relative, err := filepath.Rel(root, path)
		if err != nil || relative == "." {
			return err
		}
		relative = filepath.ToSlash(relative)
		excluded, err := matcher.MatchesOrParentMatches(relative)
		if err != nil {
			return err
		}
		if excluded && relative != dockerfile && relative != ignoreName {
			containsRequiredFile := strings.HasPrefix(dockerfile, relative+"/") || strings.HasPrefix(ignoreName, relative+"/")
			if entry.IsDir() && !matcher.Exclusions() && !containsRequiredFile {
				return filepath.SkipDir
			}
			return nil
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		link := ""
		if info.Mode()&os.ModeSymlink != 0 {
			link, err = os.Readlink(path)
			if err != nil {
				return err
			}
		}
		header, err := tar.FileInfoHeader(info, link)
		if err != nil {
			return err
		}
		header.Name = relative
		header.Mode = contextMode(header.Mode, runtime.GOOS)
		if err := writer.WriteHeader(header); err != nil {
			return err
		}
		if !info.Mode().IsRegular() {
			return nil
		}
		file, err := os.Open(path)
		if err != nil {
			return err
		}
		_, err = io.Copy(writer, file)
		file.Close()
		if err != nil {
			return fmt.Errorf("archiving %s: %w", relative, err)
		}
		return err
	})
	closeErr := writer.Close()
	if err != nil {
		return err
	}
	return closeErr
}

func quote(value string) string { return "'" + strings.ReplaceAll(value, "'", "'\"'\"'") + "'" }

func contextMode(mode int64, platform string) int64 {
	if platform == "windows" {
		// Match Moby's Windows context archive: remove group/world writes and add execute bits.
		return mode&0o755 | 0o111
	}
	return mode
}

func run(args []string) error {
	if len(args) < 1 {
		return fmt.Errorf("docker arguments required")
	}
	if args[0] == "--archive-context" {
		if len(args) != 3 {
			return fmt.Errorf("usage: --archive-context DIRECTORY DOCKERFILE")
		}
		return archiveContext(args[1], args[2], os.Stdout)
	}
	remoteArgs := append([]string{"docker"}, args...)
	var contextFile *os.File
	if args[0] == "build" {
		if len(args) < 2 {
			return fmt.Errorf("build context required")
		}
		root := args[len(args)-1]
		if root == "-" || strings.Contains(root, "://") {
			return fmt.Errorf("proxy build requires a local context directory")
		}

		var rootErr error
		root, rootErr = filepath.Abs(root)
		if rootErr != nil {
			return rootErr
		}
		dockerfile := "Dockerfile"
		for i := 1; i < len(args)-1; i++ {
			if args[i] == "-f" || args[i] == "--file" {
				i++
				if i >= len(args)-1 {
					return fmt.Errorf("missing Dockerfile argument")
				}
				dockerfile = args[i]
			} else if strings.HasPrefix(args[i], "--file=") {
				dockerfile = strings.TrimPrefix(args[i], "--file=")
			}
			if strings.HasPrefix(args[i], "--build-context") || strings.HasPrefix(args[i], "--secret") || strings.HasPrefix(args[i], "--ssh") {
				return fmt.Errorf("host-path build options require explicit transport support: %s", args[i])
			}
		}
		var err error
		contextFile, err = os.CreateTemp("", "qemu-docker-context-*.tar")
		if err != nil {
			return err
		}
		defer os.Remove(contextFile.Name())
		defer contextFile.Close()
		if err = archiveContext(root, dockerfile, contextFile); err != nil {
			return err
		}
		if info, statErr := contextFile.Stat(); statErr == nil {
			fmt.Fprintf(os.Stderr, "Filtered Docker context: %d bytes\n", info.Size())
		}
		if _, err = contextFile.Seek(0, 0); err != nil {
			return err
		}
		buildArgs := append([]string{}, args[1:len(args)-1]...)
		for i, value := range buildArgs {
			if (value == "-f" || value == "--file") && i+1 < len(buildArgs) {
				file := buildArgs[i+1]
				if filepath.IsAbs(file) {
					file, err = filepath.Rel(root, file)
					if err != nil {
						return err
					}
				}
				buildArgs[i+1] = filepath.ToSlash(file)
			}
			if strings.HasPrefix(value, "--file=") {
				file := strings.TrimPrefix(value, "--file=")
				if filepath.IsAbs(file) {
					file, err = filepath.Rel(root, file)
					if err != nil {
						return err
					}
				}
				buildArgs[i] = "--file=" + filepath.ToSlash(file)
			}
		}
		remoteArgs = append([]string{"docker", "buildx", "build", "--load"}, buildArgs...)
		remoteArgs = append(remoteArgs, "-")
	}
	port, key := os.Getenv("QEMU_DOCKER_SSH_PORT"), os.Getenv("QEMU_DOCKER_SSH_KEY")
	if port == "" || key == "" {
		return fmt.Errorf("QEMU Docker proxy environment missing; use run-testcontainers.sh")
	}
	host := os.Getenv("QEMU_DOCKER_SSH_HOST")
	if host == "" {
		host = "127.0.0.1"
	}
	command := make([]string, len(remoteArgs))
	for i, value := range remoteArgs {
		command[i] = quote(value)
	}
	ssh := exec.Command("ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-p", port, "-i", key, "root@"+host, strings.Join(command, " "))
	if os.Getenv("QEMU_DOCKER_PROXY_DEBUG") == "true" {
		_, keyErr := os.Stat(key)
		fmt.Fprintf(os.Stderr, "SSH executable=%s host=%s port=%s keyReadable=%t\n", ssh.Path, host, port, keyErr == nil)
	}
	ssh.Stdout, ssh.Stderr = os.Stdout, os.Stderr
	ssh.Stdin = os.Stdin
	if contextFile != nil {
		ssh.Stdin = contextFile
	}
	return ssh.Run()
}

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		if exit, ok := err.(*exec.ExitError); ok {
			os.Exit(exit.ExitCode())
		}
		os.Exit(1)
	}
}
