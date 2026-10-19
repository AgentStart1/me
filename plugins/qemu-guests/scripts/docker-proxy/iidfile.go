package main

import (
	"bytes"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

type remoteRunner func(command string, stdin io.Reader, stdout io.Writer) error

func remoteCommand(args []string) string {
	quoted := make([]string, len(args))
	for i, value := range args {
		quoted[i] = quote(value)
	}
	return strings.Join(quoted, " ")
}

// Use a private guest directory so concurrent builds cannot share an ID file.
func runWithIIDFile(args []string, input io.Reader, run remoteRunner) error {
	var local string
	filtered := make([]string, 0, len(args))
	for _, arg := range args {
		if strings.HasPrefix(arg, "--iidfile=") {
			local = strings.TrimPrefix(arg, "--iidfile=")
			if local == "" {
				return fmt.Errorf("--iidfile requires a host file path")
			}
		} else {
			filtered = append(filtered, arg)
		}
	}
	if local == "" {
		return run(remoteCommand(args), input, os.Stdout)
	}
	var directory bytes.Buffer
	if err := run("mktemp -d /tmp/qemu-docker-iid.XXXXXXXXXX", nil, &directory); err != nil {
		return fmt.Errorf("create guest ID directory: %w", err)
	}
	guest := strings.TrimSpace(directory.String())
	if !regexp.MustCompile(`^/tmp/qemu-docker-iid\.[A-Za-z0-9]+$`).MatchString(guest) {
		return fmt.Errorf("invalid guest ID directory")
	}
	defer func() {
		if err := run("rm -rf -- "+quote(guest), nil, io.Discard); err != nil {
			fmt.Fprintln(os.Stderr, "Warning: guest ID cleanup failed:", err)
		}
	}()
	guestFile := guest + "/image.id"
	// Append the option before the stdin context argument.
	filtered = append(filtered[:len(filtered)-1], "--iidfile="+guestFile, filtered[len(filtered)-1])
	if err := run(remoteCommand(filtered), input, os.Stdout); err != nil {
		return err
	}
	var content bytes.Buffer
	if err := run("cat -- "+quote(guestFile), nil, &content); err != nil {
		return fmt.Errorf("retrieve image ID: %w", err)
	}
	if !regexp.MustCompile(`^sha256:[a-f0-9]{64}\n?$`).Match(content.Bytes()) {
		return fmt.Errorf("guest returned an invalid image ID")
	}
	staged, err := os.CreateTemp(filepath.Dir(local), ".qemu-docker-iid-*")
	if err != nil {
		return fmt.Errorf("create host ID file: %w", err)
	}
	defer os.Remove(staged.Name())
	_, writeErr := staged.Write(content.Bytes())
	closeErr := staged.Close()
	if writeErr != nil {
		return fmt.Errorf("write host ID file: %w", writeErr)
	}
	if closeErr != nil {
		return closeErr
	}
	if err := os.Rename(staged.Name(), local); err != nil {
		return fmt.Errorf("save host ID file: %w", err)
	}
	return nil
}
