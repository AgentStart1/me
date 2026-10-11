# Persist Docker's publish pool; the startup wrapper restores broad outbound ports.
net.ipv4.ip_local_port_range = {{TESTCONTAINERS_PORT_START}} {{TESTCONTAINERS_PORT_END}}
