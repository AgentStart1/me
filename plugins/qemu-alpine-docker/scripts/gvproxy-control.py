"""Own a gvproxy process without confusing native and MSYS process IDs."""
import argparse
import json
import os
from pathlib import Path
import socket
import signal
import sys
import secrets
from process_identity import identity, terminate, write_record, owns_listeners
import subprocess
import time
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        raise ValueError("Loopback services API redirects are not followed")


LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


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
    state = Path(args.state)
    if state.exists():
        raise RuntimeError("Existing gvproxy ownership state; run stop-vm.sh before restarting")
    # Exclusive reservation prevents two controllers with different ports from
    # overwriting the same ownership record. Incomplete forced-kill reservations
    # require inspection; they must never be silently treated as stopped.
    pending = {"pending": True, "controller_pid": os.getpid(), "token": secrets.token_hex(16)}
    with state.open("x") as reservation:
        json.dump(pending, reservation)
    try:
        launch(args, state, pending)
    except BaseException:
        remove_owned_state(state, pending)
        raise


def launch(args, state, pending):
    # Probe all configured sockets before starting; gvproxy still owns the real bind.
    with socket.socket() as transport, socket.socket() as api:
        if os.name != "nt":
            # Go's Linux listeners reuse TIME_WAIT sockets during coordinated restarts.
            # Match that policy without weakening Windows' exclusive bind behavior.
            for listener in (transport, api):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        transport.bind(("127.0.0.1", args.transport))
        api.bind(("127.0.0.1", args.api))
    with open(args.log, "ab") as log:
        proc = subprocess.Popen([args.binary, "-ssh-port", "-1", "-listen-qemu", f"tcp://127.0.0.1:{args.transport}",
                                 "-services", f"tcp://127.0.0.1:{args.api}"],
                                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                start_new_session=os.name != "nt")
    try:
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
                    return
            except (OSError, ValueError):
                pass
            if time.monotonic() > deadline:
                break
            time.sleep(0.1)
        raise RuntimeError("gvproxy exited or failed readiness; inspect gvproxy.log")
    except BaseException:
        proc.kill()
        proc.wait()
        if "record" in locals():
            remove_owned_state(state, record)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "check"])
    parser.add_argument("--state", required=True)
    parser.add_argument("--binary")
    parser.add_argument("--log")
    parser.add_argument("--transport", type=int)
    parser.add_argument("--api", type=int)
    args = parser.parse_args()
    # SIGTERM must run the same cleanup as exceptions and keyboard interrupts.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    guard = Path(args.state + ".control.lock")
    guard.mkdir()  # Serialize record comparison/removal, including standalone calls.
    try:
        dispatch(args)
    finally:
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
            for line in sys.stdin.read().splitlines():
                host, guest = line.split(":")
                if (f"127.0.0.1:{host}", f"192.168.127.2:{guest}", "tcp") not in actual:
                    raise RuntimeError("Running gvproxy forwards differ from this profile")


if __name__ == "__main__":
    main()
