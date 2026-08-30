# Keep Docker's automatically published ports inside the host-forwarded range.
net.ipv4.ip_local_port_range = {{TESTCONTAINERS_PORT_START}} {{TESTCONTAINERS_PORT_END}}
