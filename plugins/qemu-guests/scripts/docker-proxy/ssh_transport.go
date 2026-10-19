package main

import (
	"fmt"
	"io"
	"net"
	"os"
	"time"

	"golang.org/x/crypto/ssh"
)

// Keep Windows command IO inside Go's SSH transport. System OpenSSH started
// from an SSH login can stall on inherited stdin, even with an anonymous pipe.
// Session ownership closes the transport after the foreground command finishes.
func nativeSSHRunner(host, port, key string) (remoteRunner, func() error, error) {
	data, err := os.ReadFile(key)
	if os.Getenv("QEMU_DOCKER_PROXY_DEBUG") == "true" {
		fmt.Fprintf(os.Stderr, "SSH transport=go host=%s port=%s keyReadable=%t\n", host, port, err == nil)
	}
	if err != nil {
		return nil, nil, err
	}
	signer, err := ssh.ParsePrivateKey(data)
	if err != nil {
		return nil, nil, err
	}
	address := net.JoinHostPort(host, port)
	connection, err := net.DialTimeout("tcp", address, 10*time.Second)
	if err != nil {
		return nil, nil, err
	}
	connection.SetDeadline(time.Now().Add(10 * time.Second))
	config := &ssh.ClientConfig{User: "root", Auth: []ssh.AuthMethod{ssh.PublicKeys(signer)},
		// Match the existing system client's explicit StrictHostKeyChecking=no
		// policy for this provisioned private backend connection.
		HostKeyCallback: ssh.InsecureIgnoreHostKey()}
	transport, channels, requests, err := ssh.NewClientConn(connection, address, config)
	if err != nil {
		connection.Close()
		return nil, nil, err
	}
	connection.SetDeadline(time.Time{})
	client := ssh.NewClient(transport, channels, requests)
	run := func(command string, input io.Reader, output io.Writer) error {
		session, err := client.NewSession()
		if err != nil {
			return err
		}
		defer session.Close()
		session.Stdin, session.Stdout, session.Stderr = input, output, os.Stderr
		return session.Run(command)
	}
	return run, client.Close, nil
}
