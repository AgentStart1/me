"""Shared cancellation boundary for resource creation, handoff and rollback."""
from contextlib import contextmanager
import signal


class Cancelled(Exception):
    def __init__(self, number):
        self.status = 128 + number


def signals():
    return [signal.SIGINT, signal.SIGTERM] + ([signal.SIGBREAK] if hasattr(signal, 'SIGBREAK') else [])


@contextmanager
def defer_cancellation():
    """Finish a bounded ownership handoff before delivering handled signals.

    Enter the owner's cleanup scope before this boundary. Assign created handles
    or roll back definitive failures inside it. Nested boundaries pass pending
    signals to their outer handler; existing handler/exit semantics are preserved.
    Network readiness must remain outside the boundary.
    """
    pending = []
    previous = {number: signal.signal(number, lambda n, _f: pending.append(n)) for number in signals()}
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
        if pending:
            number = pending[0]
            handler = previous[number]
            if callable(handler):
                handler(number, None)
            elif handler != signal.SIG_IGN:
                raise Cancelled(number)
