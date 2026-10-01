# QEMU Docker inside an ordinary Linux container

Build from the plugin root:

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

Run the development tools, test process, and MCP server in this same outer container/network namespace. Docker's loopback API is at `127.0.0.1:2375` there, and dynamically published guest ports are forwarded to `127.0.0.1:20000–20255` there. A host-side `docker -p` mapping does not make a service bound to the container's loopback reachable. The default design keeps the unauthenticated API local; it does not widen it to `0.0.0.0`.

Use this image as a base for your own JDK, build tools, or Codex environment, and install uv there for the MCP status panel. `run-testcontainers.sh -- <command>` uses guest Docker and keeps Ryuk enabled. The default metrics mode is `auto`: Windows collects PowerShell metrics, Linux runs the command without that collector. VM disk caching, Testcontainers networking, and the status panel work independently of that collector.

Stop the VM before stopping the outer container:

```bash
docker exec qemu-dev bash /opt/qemu-alpine-docker/scripts/stop-vm.sh
docker stop qemu-dev
```

Keep the named volume to reuse the qcow2 disk and image cache. The volume must be writable by UID 1000; initialize ownership separately for pre-existing bind mounts. Concurrent containers must not share a running VM's state directory.

In proxy-managed environments, pass the build CA via `--secret id=proxy_ca,src=<CA bundle>` and mount a runtime CA read-only for curl when needed. Guest package installation and guest Docker image pulls also require their own working egress and CA/proxy configuration; outer Docker proxy variables are not automatically guest configuration. Do not disable TLS verification.
