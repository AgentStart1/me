server:
    interface: {{DNS_LISTEN_ADDRESS}}
    port: {{LOCAL_DNS_PORT}}
    access-control: {{LOCAL_DNS_NETWORK}} allow
    access-control: {{DOCKER_DNS_NETWORK}} allow
    do-ip4: yes
    do-ip6: no
    do-udp: yes
    do-tcp: yes
    module-config: "iterator"

forward-zone:
    name: "."
    forward-addr: {{QEMU_DNS_ADDRESS}}@{{QEMU_DNS_PORT}}
    forward-tcp-upstream: yes
