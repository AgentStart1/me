package main

import (
	"archive/tar"
	"bytes"
	"io"
	"os"
	"path/filepath"
	"testing"
)

func put(t *testing.T, root, name, content string) {
	t.Helper()
	path := filepath.Join(root, name)
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0600); err != nil {
		t.Fatal(err)
	}
}

func contents(t *testing.T, root, dockerfile string) map[string]bool {
	t.Helper()
	var buffer bytes.Buffer
	if err := archiveContext(root, dockerfile, &buffer); err != nil {
		t.Fatal(err)
	}
	result := map[string]bool{}
	reader := tar.NewReader(&buffer)
	for {
		header, err := reader.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		result[header.Name] = true
	}
	return result
}

func TestDockerIgnoreExceptions(t *testing.T) {
	root := t.TempDir()
	put(t, root, "Dockerfile", "FROM scratch")
	put(t, root, ".dockerignore", "# comment\n**/build/**\n**/.gradle\ndeploy\n!deploy/build/**\n*.env\nDockerfile\n.dockerignore\n")
	put(t, root, "deploy/build/cli.tar", "distribution")
	put(t, root, "deploy/private.env", "secret")
	put(t, root, "cloud/cli/build/distributions/cli.tar", "excluded")
	put(t, root, "bgscripts/.gradle/executionHistory/executionHistory.lock", "excluded")
	entries := contents(t, root, "Dockerfile")
	for _, name := range []string{"Dockerfile", ".dockerignore", "deploy/build/cli.tar"} {
		if !entries[name] {
			t.Errorf("missing %s", name)
		}
	}
	for _, name := range []string{"deploy/private.env", "cloud/cli/build/distributions/cli.tar", "bgscripts/.gradle/executionHistory/executionHistory.lock"} {
		if entries[name] {
			t.Errorf("excluded file transmitted: %s", name)
		}
	}
}

func TestDockerfileSpecificIgnore(t *testing.T) {
	root := t.TempDir()
	put(t, root, "docker/custom.Dockerfile", "FROM scratch")
	put(t, root, ".dockerignore", "kept.txt\n")
	put(t, root, "docker/custom.Dockerfile.dockerignore", "secret.txt\n")
	put(t, root, "kept.txt", "included")
	put(t, root, "secret.txt", "excluded")
	entries := contents(t, root, "docker/custom.Dockerfile")
	if !entries["kept.txt"] || entries["secret.txt"] {
		t.Fatal("specific ignore did not override root ignore")
	}
}

func TestRejectOutsideDockerfile(t *testing.T) {
	if err := archiveContext(t.TempDir(), "../Dockerfile", io.Discard); err == nil {
		t.Fatal("outside Dockerfile accepted")
	}
}

func TestContextPermissions(t *testing.T) {
	if contextMode(0o666, "windows") != 0o755 || contextMode(0o444, "windows") != 0o555 {
		t.Fatal("Windows context permissions do not match Docker")
	}
	if contextMode(0o640, "linux") != 0o640 {
		t.Fatal("Unix context permissions changed")
	}
}

func TestDockerfileInExcludedDirectory(t *testing.T) {
	root := t.TempDir()
	put(t, root, "docker/custom.Dockerfile", "FROM scratch")
	put(t, root, "docker/custom.Dockerfile.dockerignore", "docker\n")
	put(t, root, "docker/private.env", "excluded")
	entries := contents(t, root, "docker/custom.Dockerfile")
	if !entries["docker/custom.Dockerfile"] || !entries["docker/custom.Dockerfile.dockerignore"] || entries["docker/private.env"] {
		t.Fatal("required Docker inputs inside an excluded directory were not retained safely")
	}
}
