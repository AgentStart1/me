#!/bin/sh
set -eu
head -n 1 /proc/stat
printf '\n---\n'
sleep 0.25
head -n 1 /proc/stat
printf '\n---\n'
grep -E '^(MemTotal|MemAvailable):' /proc/meminfo
