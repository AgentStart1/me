# QEMU Docker inside an ordinary Linux container

Build from the plugin root:

The image normalizes shell scripts, profiles, and templates to LF so Windows Git checkouts with CRLF also work inside Linux containers.

```bash
docker build -f container/Dockerfile -t qemu-alpine-dev .
```

Start a non-root container with persistent VM storage. This uses TCG when KVM is unavailable. Neither a host Docker socket nor privileged mode is required.

```bash
docker run -d --init --name qemu-dev \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --mount source=qemu-alpine-state,target=/var/lib/qemu-alpine \
  qemu-alpine-dev
```

For KVM on an x86-64 Linux host, use this alternative start command. The host must support virtualization and expose `/dev/kvm`. Nested virtualization must also be enabled if the Docker host itself is a VM.

```bash
docker run -d --init --name qemu-dev \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --device=/dev/kvm --group-add="$(stat -c '%g' /dev/kvm)" \
  --mount source=qemu-alpine-state,target=/var/lib/qemu-alpine \
  qemu-alpine-dev
```

`VM_ACCELERATOR=auto` probes whether QEMU can actually initialize KVM, then falls back to TCG. To require KVM, copy the development profile, set `VM_ACCELERATOR=kvm`, and pass that profile to the scripts. Explicit KVM fails with an actionable error if unavailable; it does not silently emulate. The guest architecture is x86-64; other host architectures can use TCG, not x86-64 KVM.

Provision once, then start the VM:

```bash
docker exec qemu-dev bash /opt/qemu-alpine-docker/scripts/setup.sh
docker exec qemu-dev bash /opt/qemu-alpine-docker/scripts/create-vm.sh
docker exec qemu-dev bash /opt/qemu-alpine-docker/scripts/start-vm.sh
docker exec qemu-dev bash /opt/qemu-alpine-docker/scripts/run-docker.sh -- ps -a
docker exec qemu-dev python3 /opt/qemu-alpine-docker/scripts/status.py
```

Run the development tools, test process, and MCP server in this same outer container/network namespace. `setup.sh` installs verified upstream gvproxy v0.9.0. QEMU and gvproxy share this namespace; Alpine and Docker use gvproxy DNS. Docker's loopback API is at `127.0.0.1:2375` there, and dynamically published guest ports are forwarded to `127.0.0.1:20000–20255` there. A host-side `docker -p` mapping does not make a service bound to the container's loopback reachable. The default design keeps the unauthenticated API local; it does not widen it to `0.0.0.0`.

Use this image as a base for your own JDK, build tools, or Codex environment, and install uv there for the MCP status panel. Before the first test run, compile the Linux Docker CLI proxy inside the outer container, after the VM has started:

```bash
docker exec qemu-dev bash /opt/qemu-alpine-docker/scripts/build-docker-proxy.sh
docker exec qemu-dev bash /opt/qemu-alpine-docker/scripts/run-testcontainers.sh -- <test command>
```

Replace `<test command>` with a command available inside the outer container, with the project accessible there. The build script uses Go in the Alpine guest and downloads a Linux amd64/arm64 `docker` executable for the outer container's architecture; the outer container needs no Go installation. Rebuild after proxy source updates. The default helper path is `~/.local/share/me/docker-proxy/docker` under the container user's home; persist that directory or rebuild after replacing the outer container. It is separate from the VM state volume. Use the same `QEMU_DOCKER_PROXY_DIR` override for compilation and test execution.

`run-testcontainers.sh` puts this proxy on PATH and supplies the guest SSH settings. Docker builds filter the local context using Docker ignore rules and stream it over SSH to the guest. Linux source permission bits are preserved, so scripts must already have their required execute bits. Host-path bind mounts and `docker cp` are not translated; use build contexts or named volumes for guest containers.

The wrapper uses guest Docker and keeps Ryuk enabled. The default metrics mode is `auto`: Linux runs without the Windows PowerShell collector and does not produce its summary or update its report. VM disk caching, Testcontainers networking, and the status panel work independently of that collector.

Stop the VM before stopping the outer container:

```bash
docker exec qemu-dev bash /opt/qemu-alpine-docker/scripts/stop-vm.sh
docker stop qemu-dev
```

Keep the named volume to reuse the qcow2 disk and image cache. The volume must be writable by UID 1000; initialize ownership separately for pre-existing bind mounts. Concurrent containers must not share a running VM's state directory.

In proxy-managed environments, pass the build CA via `--secret id=proxy_ca,src=<CA bundle>` and mount a runtime CA read-only for curl when needed. Guest package installation and guest Docker image pulls also require their own working egress and CA/proxy configuration; outer Docker proxy variables are not automatically guest configuration. Do not disable TLS verification.
