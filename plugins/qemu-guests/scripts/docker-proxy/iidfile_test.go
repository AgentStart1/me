package main

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestIIDFileTransfer(t *testing.T) {
	for _, failure := range []string{"", "build", "retrieve", "invalid", "missing-parent"} {
		t.Run(failure, func(t *testing.T) {
			local := filepath.Join(t.TempDir(), "image id's.txt")
			if failure == "missing-parent" {
				local = filepath.Join(local, "image.id")
			} else if err := os.WriteFile(local, []byte("previous"), 0600); err != nil {
				t.Fatal(err)
			}
			id := "sha256:" + strings.Repeat("a", 64)
			cleaned, built := false, false
			runner := func(command string, input io.Reader, output io.Writer) error {
				switch {
				case strings.HasPrefix(command, "mktemp"):
					if input != nil {
						t.Fatal("setup consumed context input")
					}
					fmt.Fprintln(output, "/tmp/qemu-docker-iid.test123")
				case strings.HasPrefix(command, "'docker'"):
					built = true
					data, err := io.ReadAll(input)
					if err != nil || string(data) != "context" {
						t.Fatal("context not streamed to build")
					}
					if strings.Contains(command, local) || !strings.Contains(command, "'--iidfile=/tmp/qemu-docker-iid.test123/image.id' '-'") {
						t.Fatalf("wrong remote path: %s", command)
					}
					if failure == "build" {
						return fmt.Errorf("build failed")
					}
				case strings.HasPrefix(command, "cat"):
					if failure == "build" {
						t.Fatal("retrieved ID after build failure")
					}
					if failure == "retrieve" {
						return fmt.Errorf("transfer failed")
					}
					if failure == "invalid" {
						fmt.Fprint(output, "broken")
					} else {
						fmt.Fprint(output, id)
					}
				case strings.HasPrefix(command, "rm"):
					cleaned = true
				default:
					t.Fatalf("unexpected command %s", command)
				}
				return nil
			}
			err := runWithIIDFile([]string{"docker", "buildx", "build", "--load", "--iidfile=" + local, "-"}, strings.NewReader("context"), runner)
			if !built || !cleaned {
				t.Fatal("build or cleanup missing")
			}
			if failure == "" {
				data, readErr := os.ReadFile(local)
				if err != nil || readErr != nil || string(data) != id {
					t.Fatalf("ID transfer failed: %v %v %q", err, readErr, data)
				}
			} else {
				if err == nil {
					t.Fatal("failure reported success")
				}
				if failure != "missing-parent" {
					data, _ := os.ReadFile(local)
					if string(data) != "previous" {
						t.Fatal("failure overwrote host file")
					}
				}
			}
		})
	}
}

func TestIIDFileFlagForms(t *testing.T) {
	for _, args := range [][]string{{"--iidfile", "image.id", "."}, {".", "--iidfile=image.id"}} {
		_, _, options, err := parseBuild(args)
		if err != nil || len(options) != 1 || options[0] != "--iidfile=image.id" {
			t.Fatalf("%v: %v %v", args, options, err)
		}
	}
}
