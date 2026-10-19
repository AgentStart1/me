# /// script
# requires-python = ">=3.10"
# dependencies = ["testcontainers==4.15.0"]
# ///
"""Opt-in acceptance check against an already running isolated Alpine guest."""
import argparse
import os
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import docker
from testcontainers.core.container import DockerContainer
from testcontainers.core.labels import SESSION_ID


def counters(container, name):
    result = container.exec_run(['cat', '/sys/fs/cgroup/' + name])
    assert result.exit_code == 0, result
    return {key: int(value) for key, value in
            (line.split() for line in result.output.decode().splitlines())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool-start', type=int, required=True)
    parser.add_argument('--pool-end', type=int, required=True)
    args = parser.parse_args()
    if not os.environ.get('DOCKER_HOST', '').startswith('tcp://127.0.0.1:'):
        parser.error('Run through run-testcontainers.sh against an isolated loopback guest')
    if os.environ.get('TESTCONTAINERS_RYUK_DISABLED', '').lower() in ('true', '1'):
        parser.error('Ryuk must remain enabled')

    client = docker.from_env(timeout=120)
    container_ids = []
    try:
        info = client.info()
        assert info['CgroupVersion'] == '2', info.get('CgroupVersion')
        assert info['MemoryLimit'], 'Docker has no memory-limit support'
        workload = DockerContainer('busybox:1.37').with_exposed_ports(8080).with_command([
            'sh', '-c', 'mkdir -p /www; echo isolated-guest-ok >/www/index.html; '
            'exec httpd -f -p 8080 -h /www'
        ]).with_kwargs(mem_limit='64m', memswap_limit='64m', cpu_period=100000,
                      cpu_quota=50000)
        with workload:
            container = workload.get_wrapped_container()
            container_ids.append(container.id)
            port = int(workload.get_exposed_port(8080))
            assert args.pool_start <= port <= args.pool_end, port
            assert workload.get_container_host_ip() == '127.0.0.1'
            opener = build_opener(ProxyHandler({}))
            deadline = time.monotonic() + 60
            while True:
                try:
                    with opener.open(f'http://127.0.0.1:{port}', timeout=2) as response:
                        assert response.read().strip() == b'isolated-guest-ok'
                    break
                except (URLError, TimeoutError):
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.2)
            container.reload()
            limits = container.attrs['HostConfig']
            assert limits['Memory'] == 64 * 1024 * 1024
            assert limits['CpuQuota'] == 50000 and limits['CpuPeriod'] == 100000
            for path, expected in [('memory.max', b'67108864'), ('cpu.max', b'50000 100000')]:
                result = container.exec_run(['cat', '/sys/fs/cgroup/' + path])
                assert result.exit_code == 0 and result.output.strip() == expected, result
            throttled = counters(container, 'cpu.stat')['nr_throttled']
            container.exec_run(['timeout', '2', 'sh', '-c', 'while :; do :; done'])
            assert counters(container, 'cpu.stat')['nr_throttled'] > throttled
            # A separate single-process container makes the OOM victim unambiguous.
            pressure = DockerContainer('alpine:3.24').with_command([
                'dd', 'if=/dev/zero', 'of=/dev/shm/pressure', 'bs=1M', 'count=96'
            ]).with_kwargs(mem_limit='64m', memswap_limit='64m', shm_size='128m')
            with pressure:
                constrained = pressure.get_wrapped_container()
                container_ids.append(constrained.id)
                result = constrained.wait(timeout=60)
                constrained.reload()
                assert result['StatusCode'] == 137, result
                assert constrained.attrs['State']['OOMKilled'], constrained.attrs['State']
            assert client.containers.list(filters={'name': f'testcontainers-ryuk-{SESSION_ID}'}), 'Ryuk is absent'
            print('PASS: real Testcontainers HTTP forwarding, cgroup v2 CPU throttling and OOM enforcement; Ryuk enabled')
        for container_id in container_ids:
            try:
                client.containers.get(container_id)
            except docker.errors.NotFound:
                pass
            else:
                raise AssertionError('Testcontainers workload was not removed')
        print('PASS: Testcontainers removed its workload')
    finally:
        client.close()


if __name__ == '__main__':
    main()
