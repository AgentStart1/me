#!/bin/ash
set -eu

printf 'nameserver %s\n' '{{LOCAL_DNS_ADDRESS}}' > /etc/resolv.conf
