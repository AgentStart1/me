"""Own CLI signals until the exit decision and public diagnostics are complete."""
from enum import Enum, auto
from dataclasses import dataclass
import signal

from resource_ownership import Cancelled, signals
from test_cancellation import CancellationRequest, cancellation_context
from test_cleanup_diagnostics import CleanupReport, cleanup_report


@dataclass(frozen=True, slots=True)
class CliSuccess:
    status: int


@dataclass(frozen=True, slots=True)
class CliFailure:
    error: BaseException


@dataclass(frozen=True, slots=True)
class CliResult:
    status: int | None
    cleanup: CleanupReport
    error: BaseException | None = None


class CliPhase(Enum):
    NEW = auto()
    RUNNING = auto()
    FINALIZING = auto()
    CLOSED = auto()


class CliSignalScope:
    """Own synchronous execution, its immutable result and signal restoration."""

    def __init__(self):
        self.phase = CliPhase.NEW
        self._previous = {}
        self.cancellation = CancellationRequest()
        self._context = None
        self._outcome = None
        self._result = None
        self._execution_started = False

    @property
    def outcome(self):
        return self._outcome

    def __enter__(self):
        self.cancellation.require_main_thread()
        if self.phase is not CliPhase.NEW:
            raise RuntimeError('CLI signal scope cannot be reused')
        self.phase = CliPhase.RUNNING
        self._context = cancellation_context(self.cancellation)
        self._context.__enter__()
        try:
            for number in signals():
                # Publish rollback before installation can trigger a signal.
                self._previous[number] = signal.getsignal(number)
                signal.signal(number, self._handle_signal)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def _handle_signal(self, number, frame):
        self.cancellation.request(number)

    def execute(self, operation):
        """Run once, capture its outcome, then stop accepting cancellation.

        Signals never raise here. The operation and its resource owner share this
        request and respond only at explicit checkpoints before cleanup begins.
        """
        self.cancellation.require_main_thread()
        if self.phase is not CliPhase.RUNNING or self._execution_started:
            raise RuntimeError('CLI execution can only run once')
        self._execution_started = True
        try:
            self.cancellation.checkpoint()
            value = operation()
        except BaseException as error:
            self.cancellation.finish()
            outcome = CliFailure(error)
        else:
            self.cancellation.finish()
            outcome = CliSuccess(value)
        self._outcome = outcome
        self.phase = CliPhase.FINALIZING
        return outcome

    def result(self, owner):
        """Snapshot committed cleanup facts; output never reads mutable ownership."""
        self.cancellation.require_main_thread()
        if self.phase is not CliPhase.FINALIZING or self._outcome is None:
            raise RuntimeError('CLI execution has no final result')
        if self._result is not None:
            return self._result
        if isinstance(self._outcome, CliFailure):
            self._result = CliResult(exit_status(self._outcome.error, owner), cleanup_report(owner), self._outcome.error)
        else:
            self._result = CliResult(self._outcome.status, cleanup_report(owner))
        return self._result

    def __exit__(self, kind, error, traceback):
        self.cancellation.require_main_thread()
        self.cancellation.finish()
        self.phase = CliPhase.FINALIZING
        # Restore SIGINT last. If a caller handler fires during restoration,
        # finish the interrupted handoff instead of abandoning other handlers.
        for number, handler in reversed(tuple(self._previous.items())):
            while True:
                try:
                    signal.signal(number, handler)
                    break
                except (Cancelled, KeyboardInterrupt, SystemExit):
                    if signal.getsignal(number) is handler:
                        break
        self.phase = CliPhase.CLOSED
        if self._context is not None:
            self._context.__exit__(kind, error, traceback)
            self._context = None


def exit_status(error, owner):
    if isinstance(error, Cancelled):
        return error.status
    if isinstance(error, KeyboardInterrupt):
        return 130
    if isinstance(error, SystemExit):
        return error.code if isinstance(error.code, int) else (0 if error.code is None else 1)
    if owner.cleanup_failures or owner.cleanup_uncertain:
        return 1
    return None
