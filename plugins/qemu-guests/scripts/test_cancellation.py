"""Single-consumer cancellation and worker outcomes for configured test runs."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from enum import Enum, auto
from queue import SimpleQueue
import subprocess
import threading

from resource_ownership import Cancelled


class CancellationPhase(Enum):
    RUNNING = auto()
    DRAINING = auto()
    FINISHED = auto()


class WorkerEventKind(Enum):
    REQUEST = auto()
    INTERRUPTED = auto()
    CLEANUP_FAILED = auto()


@dataclass(frozen=True, slots=True)
class WorkerEvent:
    kind: WorkerEventKind
    value: object


@dataclass(frozen=True, slots=True)
class CancellationState:
    phase: CancellationPhase
    accepted: BaseException | None = None


class WorkerDrainError(RuntimeError):
    """Resource-using workers have not all reported completion."""


def is_cancellation(error):
    return isinstance(error, Cancelled) or not isinstance(error, Exception)


class CancellationRequest:
    """Workers publish events; only the main thread commits state and failures.

    Each worker reads one immutable state snapshot at a checkpoint. It cannot
    create/replace the shared cancellation. Admission and completion accounting
    ensure worker reports precede the owner's final failure/lease decision.
    """

    def __init__(self):
        self._state = CancellationState(CancellationPhase.RUNNING)
        self._number = None
        self._events = SimpleQueue()
        self._failures = []
        self._shields = ContextVar('test_environment_cleanup_shield', default=0)
        self._worker_depth = ContextVar('test_environment_worker_depth', default=0)
        self._worker_lock = threading.Lock()
        self._admission_open = True
        self._active_workers = 0

    @property
    def phase(self):
        return self._state.phase

    @property
    def accepted(self):
        return self._state.accepted

    @property
    def cleanup_failures(self):
        return tuple(self._failures)

    @staticmethod
    def require_main_thread():
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError('Only the main thread may commit test execution state')

    def request(self, number):
        # SimpleQueue.put is reentrant on the supported CPython runtime. Signal
        # handlers do not acquire the worker lock or mutate committed state.
        self._events.put(WorkerEvent(WorkerEventKind.REQUEST, number))

    def _accept(self, error):
        if self.phase is not CancellationPhase.FINISHED and self.accepted is None:
            self._state = replace(self._state, accepted=error)

    def observe(self, error):
        if is_cancellation(error):
            if threading.current_thread() is threading.main_thread():
                self._accept(error)
            else:
                self._events.put(WorkerEvent(WorkerEventKind.INTERRUPTED, error))

    def report_cleanup(self, error):
        self._events.put(WorkerEvent(WorkerEventKind.CLEANUP_FAILED, error))

    def _collect_until(self, fence, accept_requests):
        while True:
            event = self._events.get()
            if event is fence:
                return
            if event.kind is WorkerEventKind.REQUEST:
                if accept_requests and self._number is None:
                    self._number = event.value
            elif event.kind is WorkerEventKind.INTERRUPTED:
                self._accept(event.value)
            elif event.kind is WorkerEventKind.CLEANUP_FAILED:
                if not any(item is event.value for item in self._failures):
                    self._failures.append(event.value)
                if is_cancellation(event.value):
                    self._accept(event.value)

    def collect(self):
        """Consume a finite queue prefix; only the main thread owns the ledger."""
        self.require_main_thread()
        fence = object()
        self._events.put(fence)
        self._collect_until(fence, self.phase is CancellationPhase.RUNNING)

    def checkpoint(self):
        if self._shields.get():
            return
        if threading.current_thread() is threading.main_thread():
            self.collect()
            if self.phase is not CancellationPhase.FINISHED and self.accepted is None and self._number is not None:
                self._accept(Cancelled(self._number))
        state = self._state
        if state.phase is not CancellationPhase.FINISHED and state.accepted is not None:
            raise state.accepted

    def begin_cleanup(self, error=None):
        self.require_main_thread()
        if self.phase is not CancellationPhase.RUNNING:
            raise RuntimeError('Execution cleanup can only begin once')
        # The fence closes request acceptance. A signal before/after this queue
        # insertion has an unambiguous order, without locking in the handler.
        fence = object()
        self._events.put(fence)
        with self._worker_lock:
            self._admission_open = False
        self._state = replace(self._state, phase=CancellationPhase.DRAINING)
        if error is not None:
            self.observe(error)
        self._collect_until(fence, accept_requests=True)
        if self.accepted is None and self._number is not None:
            self._accept(Cancelled(self._number))
        return self.accepted

    @contextmanager
    def worker(self):
        """Track one resource-using dispatch, including nested transport calls."""
        if threading.current_thread() is threading.main_thread() or self._worker_depth.get():
            yield
            return
        with self._worker_lock:
            if not self._admission_open:
                state = self._state
                if state.accepted is not None:
                    raise state.accepted
                raise RuntimeError('Test environment no longer accepts work')
            self._active_workers += 1
        marker = self._worker_depth.set(1)
        try:
            yield
        except BaseException as error:
            self.observe(error)
            raise
        finally:
            self._worker_depth.reset(marker)
            with self._worker_lock:
                self._active_workers -= 1

    def seal_workers(self):
        """Confirm quiescence and collect reports before any lease release."""
        self.require_main_thread()
        with self._worker_lock:
            self._admission_open = False
            quiescent = self._active_workers == 0
        self.collect()
        if not quiescent:
            raise WorkerDrainError('Owned workers have not finished; retain test ownership')

    def finish(self):
        self.require_main_thread()
        with self._worker_lock:
            self._admission_open = False
        self._state = replace(self._state, phase=CancellationPhase.FINISHED)

    @contextmanager
    def shield(self):
        marker = self._shields.set(self._shields.get() + 1)
        try:
            yield
        finally:
            self._shields.reset(marker)

    def wait(self, child, interval=.1, checkpoint=None):
        """Wait without changing the command's timeout or rerunning it."""
        while True:
            (self.checkpoint if checkpoint is None else checkpoint)()
            try:
                return child.wait(timeout=interval)
            except subprocess.TimeoutExpired:
                pass


_current = ContextVar('test_environment_cancellation', default=None)


def current_cancellation():
    return _current.get()


@contextmanager
def cancellation_context(request):
    marker = _current.set(request)
    try:
        yield
    finally:
        _current.reset(marker)
