package main

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/x509"
	"encoding/pem"
	"io"
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"

	"golang.org/x/crypto/ssh"
)

func TestNativeSSHBinaryInputEOFExitAndOpenStdin(t *testing.T) {
	_, private, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	der, err := x509.MarshalPKCS8PrivateKey(private)
	if err != nil {
		t.Fatal(err)
	}
	key := filepath.Join(t.TempDir(), "key")
	if err := os.WriteFile(key, pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: der}), 0600); err != nil {
		t.Fatal(err)
	}
	signer, err := ssh.NewSignerFromKey(private)
	if err != nil {
		t.Fatal(err)
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	done := make(chan struct{})
	go func() {
		defer close(done)
		connection, err := listener.Accept()
		if err != nil {
			return
		}
		defer connection.Close()
		connection.SetDeadline(time.Now().Add(10 * time.Second))
		config := &ssh.ServerConfig{NoClientAuth: true}
		config.AddHostKey(signer)
		server, channels, requests, err := ssh.NewServerConn(connection, config)
		if err != nil {
			return
		}
		defer server.Close()
		go ssh.DiscardRequests(requests)
		for channel := range channels {
			stream, requests, err := channel.Accept()
			if err != nil {
				return
			}
			go func() {
				defer stream.Close()
				for request := range requests {
					var exec struct{ Command string }
					if request.Type != "exec" || ssh.Unmarshal(request.Payload, &exec) != nil {
						request.Reply(false, nil)
						continue
					}
					request.Reply(true, nil)
					if exec.Command != "noinput" {
						data, _ := io.ReadAll(stream)
						stream.Write(data)
					}
					status := uint32(0)
					if exec.Command == "fail" {
						status = 9
					}
					stream.SendRequest("exit-status", false, ssh.Marshal(struct{ Status uint32 }{status}))
					return
				}
			}()
		}
	}()
	host, port, _ := net.SplitHostPort(listener.Addr().String())
	run, closeClient, err := nativeSSHRunner(host, port, key)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { closeClient(); <-done }()
	input := bytes.Repeat([]byte{0, 1, 10, 13, 255}, 20000)
	var output bytes.Buffer
	if err := run("echo", bytes.NewReader(input), &output); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(output.Bytes(), input) {
		t.Fatal("binary input changed or EOF was lost")
	}
	if err := run("echo", nil, io.Discard); err != nil {
		t.Fatal(err)
	}
	if err := run("fail", nil, io.Discard); err == nil {
		t.Fatal("lost remote exit failure")
	} else if status, ok := err.(interface{ ExitStatus() int }); !ok || status.ExitStatus() != 9 {
		t.Fatalf("lost remote exit status: %v", err)
	}
	reader, writer := io.Pipe()
	defer reader.Close()
	defer writer.Close()
	finished := make(chan error, 1)
	go func() { finished <- run("noinput", reader, io.Discard) }()
	select {
	case err := <-finished:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("command waited for unused stdin")
	}
}
