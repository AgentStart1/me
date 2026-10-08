package main

import (
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func TestBuildContextPosition(t *testing.T) {
	for _, args := range [][]string{
		{".", "-t", "image", "--no-cache"},
		{"-t", "image", ".", "--no-cache"},
		{"--tag=image", "--no-cache", "."},
		{"-timage", "--no-cache", "--", "."},
	} {
		root, file, options, err := parseBuild(args)
		cwd, _ := os.Getwd()
		if err != nil || root != cwd || file != "Dockerfile" || !reflect.DeepEqual(options, []string{"--tag=image", "--no-cache"}) {
			t.Fatalf("%v: root=%s file=%s options=%v err=%v", args, root, file, options, err)
		}
	}
}

func TestExplicitDockerfileAndIgnoreFromWorkingDirectory(t *testing.T) {
	root := t.TempDir()
	put(t, root, "docker/custom.Dockerfile", "FROM scratch")
	put(t, root, "docker/custom.Dockerfile.dockerignore", "secret.txt\n")
	put(t, root, ".dockerignore", "kept.txt\n")
	put(t, root, "kept.txt", "kept")
	put(t, root, "secret.txt", "secret")
	cwd, _ := os.Getwd()
	relative, err := filepath.Rel(cwd, filepath.Join(root, "docker/custom.Dockerfile"))
	if err != nil {
		t.Fatal(err)
	}
	for _, flag := range [][]string{{"-f", relative}, {"--file=" + relative}, {"-f" + relative}} {
		args := append([]string{root}, flag...)
		context, file, options, err := parseBuild(args)
		if err != nil {
			t.Fatal(err)
		}
		if file != "docker/custom.Dockerfile" || !reflect.DeepEqual(options, []string{"--file=docker/custom.Dockerfile"}) {
			t.Fatalf("file=%s options=%v", file, options)
		}
		entries := contents(t, context, file)
		if !entries[file] || !entries["kept.txt"] || entries["secret.txt"] {
			t.Fatal("wrong Dockerfile or ignore rules")
		}
	}
}

func TestRejectUntransportedOutputBeforeSSH(t *testing.T) {
	for _, args := range [][]string{
		{"build", ".", "--metadata-file=metadata.json"},
		{"build", ".", "-o", "type=local,dest=output"},
	} {
		if err := run(args); err == nil || !strings.Contains(err.Error(), "transport support") {
			t.Fatalf("%v: %v", args, err)
		}
	}
}

func TestRejectAmbiguousBuildArguments(t *testing.T) {
	for _, args := range [][]string{{".", "another"}, {"-t"}, {"--unknown", "."}, {".", "-f", "../Dockerfile"}} {
		if _, _, _, err := parseBuild(args); err == nil {
			t.Fatalf("accepted %v", args)
		}
	}
}
