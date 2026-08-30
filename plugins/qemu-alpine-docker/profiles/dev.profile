# Development profile for QEMU Alpine Docker VM.
# Provides balanced resources for interactive development.

VM_NAME=alpine-docker
VM_ACCELERATOR=auto
VM_MEMORY=4096
VM_CPUS=4
VM_DISK_SIZE=20G
SSH_PORT=2222
DOCKER_DAEMON_PORT=2375
PORT_FORWARD=8080:80,3000:3000,5000:5000
TESTCONTAINERS_PORT_START=20000
TESTCONTAINERS_PORT_END=20255
# Pure TCG may spend longer than Testcontainers defaults extracting large image layers.
TESTCONTAINERS_PULL_PAUSE_TIMEOUT=300
TESTCONTAINERS_PULL_TIMEOUT=1800
TESTCONTAINERS_RESOURCE_METRICS=true
TESTCONTAINERS_RESOURCE_METRICS_INTERVAL=1
ALPINE_BRANCH=v3.24
# Use auto to select the fastest HTTPS-capable mirror during first provisioning.
ALPINE_MIRROR_BASE=auto
# Optional comma-separated images to pull once during provisioning.
PRELOAD_IMAGES=
