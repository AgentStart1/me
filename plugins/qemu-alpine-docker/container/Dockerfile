# syntax=docker/dockerfile:1
FROM debian:bookworm-slim
# An optional public CA bundle supports proxy-managed build environments.
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then \
      printf 'Acquire::https::CaInfo "/run/secrets/proxy_ca";\n' > /etc/apt/apt.conf.d/99-build-ca; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends \
      bash ca-certificates curl openssh-client procps python3 qemu-system-x86 \
      qemu-utils tar xorriso && \
    rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/99-build-ca
RUN useradd --create-home --uid 1000 developer && \
    install -d -o developer -g developer /var/lib/qemu-alpine /workspace
COPY --chown=developer:developer scripts /opt/qemu-alpine-docker/scripts
COPY --chown=developer:developer profiles /opt/qemu-alpine-docker/profiles
COPY --chown=developer:developer templates /opt/qemu-alpine-docker/templates
RUN find /opt/qemu-alpine-docker -type f \( -name '*.sh' -o -name '*.profile' -o -name '*.tpl' \) \
    -exec sed -i 's/\r$//' {} +
ENV QEMU_ALPINE_BASE_DIR=/var/lib/qemu-alpine
USER developer
WORKDIR /workspace
CMD ["sleep", "infinity"]
