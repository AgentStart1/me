"""Own a gvproxy process without confusing native and MSYS process IDs."""
import argparse
from contextlib import closing
import http.client
import json
import os
from pathlib import Path
import socket
import signal
import sys
import secrets
from process_identity import identity, terminate, write_record, owns_listeners
from resource_ownership import defer_cancellation
import subprocess
import time
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        raise ValueError("Loopback services API redirects are not followed")


LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def read_mappings(stream):
    mappings = []
    hosts = set()
    for line in stream.read().splitlines():
        host, guest = line.split(":")
        if not all(value.isascii() and value.isdecimal() and 1 <= int(value) <= 65535
                   for value in (host, guest)):
            raise ValueError("Forward ports must be integers from 1 to 65535")
        host, guest = int(host), int(guest)
        if host in hosts:
            raise ValueError(f"Duplicate forward host port {host}")
        hosts.add(host)
        mappings.append((host, guest))
    return mappings


def listener_budget(count):
    """Ensure the child can hold listeners with room for transport and connections."""
    if os.name == "nt":
        return
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    required = count + 256
    if hard != resource.RLIM_INFINITY and hard < required:
        raise RuntimeError(f"gvproxy needs at least {required} file descriptors; hard limit is {hard}. "
                           "Raise the host/container nofile limit or select a smaller publish pool.")
    if soft != resource.RLIM_INFINITY and soft < required:
        resource.setrlimit(resource.RLIMIT_NOFILE, (required, hard))


def register_mappings(api, mappings):
    # Reuse one HTTP connection instead of launching one curl process per port.
    # No connection retries: any failed bind/request aborts the owned launch.
    deadline = time.monotonic() + 30 + len(mappings) / 50
    with closing(http.client.HTTPConnection("127.0.0.1", api, timeout=5)) as connection:
        for host, guest in mappings:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("gvproxy forwarding registration exceeded its size-aware startup budget")
            connection.timeout = min(5, remaining)
            if connection.sock is not None:
                connection.sock.settimeout(connection.timeout)
            payload = json.dumps({"local": f"127.0.0.1:{host}",
                                  "remote": f"192.168.127.2:{guest}", "protocol": "tcp"})
            connection.request("POST", "/services/forwarder/expose", payload,
                               {"Content-Type": "application/json"})
            response = connection.getresponse()
            response.read()
            if time.monotonic() > deadline:
                raise TimeoutError("gvproxy forwarding registration exceeded its size-aware startup budget")
            if response.status != 200:
                raise RuntimeError(f"gvproxy failed to register TCP {host}:{guest} (HTTP {response.status})")


def remove_owned_state(state, record):
    if state.exists() and json.loads(state.read_text()) == record:
        state.unlink()



def stop(state):
    if not state.exists():
        return
    record = json.loads(state.read_text())
    if record.get("pending"):
        raise RuntimeError("Incomplete gvproxy launch reservation; inspect before recovery")
    current = identity(record["pid"])
    if current is not None and current != record["identity"]:
        raise RuntimeError("gvproxy PID identity changed; refusing to signal another process")
    if current:
        terminate(record)
    remove_owned_state(state, record)


def start(args):
    mappings = read_mappings(sys.stdin) if args.configure else []
    listener_budget(len(mappings))
    state = Path(args.state)
    if state.exists():
        raise RuntimeError("Existing gvproxy ownership state; run stop-vm.sh before restarting")
    # Exclusive reservation prevents two controllers with different ports from
    # overwriting the same ownership record. Incomplete forced-kill reservations
    # require inspection; they must never be silently treated as stopped.
    pending = {"pending": True, "controller_pid": os.getpid(), "token": secrets.token_hex(16)}
    reserved = False
    proc = None
    record = None
    try:
        with defer_cancellation():
            reservation = state.open("x")
            try:
                with reservation:
                    json.dump(pending, reservation)
            except BaseException:
                # Exclusively created here; no process can exist yet.
                state.unlink()
                raise
            reserved = True
        # Probe sockets before starting; gvproxy still owns the real bind.
        with socket.socket() as transport, socket.socket() as api:
            if os.name != "nt":
                # Match Go's Linux TIME_WAIT reuse without weakening Windows'
                # exclusive bind behavior during coordinated restarts.
                for listener in (transport, api):
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            transport.bind(("127.0.0.1", args.transport))
            api.bind(("127.0.0.1", args.api))
        # The cleanup scope already exists. Defer cancellation through handle
        # assignment, including log close, before allowing any signal to unwind.
        with defer_cancellation():
            with open(args.log, "ab") as log:
                proc = subprocess.Popen([args.binary, "-ssh-port", "-1", "-listen-qemu", f"tcp://127.0.0.1:{args.transport}",
                                         "-services", f"tcp://127.0.0.1:{args.api}"],
                                        stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                        start_new_session=os.name != "nt")
        record = {"pid": proc.pid, "identity": identity(proc.pid), "token": pending["token"],
                  "api": args.api, "transport": args.transport}
        if not record["identity"] or record["identity"][0] != os.path.normcase(os.path.realpath(args.binary)):
            raise RuntimeError("Unexpected gvproxy process identity")
        write_record(state, record)
        deadline = time.monotonic() + 10
        while proc.poll() is None:
            try:
                with LOCAL_HTTP.open(f"http://127.0.0.1:{args.api}/services/forwarder/all", timeout=1) as response:
                    json.load(response)
                # A successful services API alone does not prove transport bind.
                # Connecting would consume upstream's one QEMU accept, so inspect
                # bind exclusivity instead; QEMU establishes the actual connection.
                if owns_listeners(proc.pid, [args.transport, args.api]) and proc.poll() is None:
                    break
            except (OSError, ValueError):
                pass
            if time.monotonic() > deadline:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("gvproxy exited before readiness; inspect gvproxy.log")
        if time.monotonic() > deadline:
            raise RuntimeError("gvproxy failed readiness; inspect gvproxy.log")
        register_mappings(args.api, mappings)
        if proc.poll() is not None:
            raise RuntimeError("gvproxy exited during forwarding registration")
    except BaseException:
        with defer_cancellation():
            if proc is not None:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=10)
            # A failed kill/join must retain pending or published evidence.
            if reserved:
                if record is not None:
                    remove_owned_state(state, record)
                remove_owned_state(state, pending)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "check"])
    parser.add_argument("--state", required=True)
    parser.add_argument("--binary")
    parser.add_argument("--log")
    parser.add_argument("--transport", type=int)
    parser.add_argument("--api", type=int)
    parser.add_argument("--configure", action="store_true", help="Register stdin host:guest mappings during owned launch")
    args = parser.parse_args()
    # SIGTERM must run the same cleanup as exceptions and keyboard interrupts.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, lambda *_: sys.exit(128 + signal.SIGBREAK))
    guard = Path(args.state + ".control.lock")
    guard_owned = False
    try:
        with defer_cancellation():
            guard.mkdir()  # Serialize record comparison/removal, including standalone calls.
            guard_owned = True
        dispatch(args)
    finally:
        if guard_owned:
            with defer_cancellation():
                guard.rmdir()


def dispatch(args):
    if args.action == "start":
        start(args)
    elif args.action == "stop":
        stop(Path(args.state))
    else:
        record = json.loads(Path(args.state).read_text())
        if identity(record["pid"]) != record["identity"]:
            raise RuntimeError("gvproxy is unavailable; coordinate stop-vm.sh/start-vm.sh recovery")
        if args.transport and record.get("transport", args.transport) != args.transport:
            raise RuntimeError("Running gvproxy transport differs from this profile")
        if args.api:
            if record.get("api", args.api) != args.api:
                raise RuntimeError("Running gvproxy API differs from this profile")
            with LOCAL_HTTP.open(f"http://127.0.0.1:{args.api}/services/forwarder/all", timeout=5) as response:
                rules = json.load(response)
            actual = {(r["local"], r["remote"], r["protocol"]) for r in rules}
            for host, guest in read_mappings(sys.stdin):
                if (f"127.0.0.1:{host}", f"192.168.127.2:{guest}", "tcp") not in actual:
                    raise RuntimeError("Running gvproxy forwards differ from this profile")


if __name__ == "__main__":
    main()
