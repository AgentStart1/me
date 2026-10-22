"""One execution owner for host resources and an optional guest test lease."""
from contextlib import ExitStack
from enum import Enum, auto
import json
import os
from pathlib import Path
import uuid

from process_identity import identity, write_record
from resource_ownership import defer_cancellation
from test_cancellation import CancellationRequest, WorkerDrainError, current_cancellation


class CleanupUncertain(RuntimeError):
    """Owned work cannot be confirmed stopped; retain any acquired reservation."""


class EnvironmentCleanupError(RuntimeError):
    """Cleanup failures accompanying cancellation, in observation order."""

    def __init__(self, failures):
        self.failures = tuple(failures)
        super().__init__(f'Test environment reported {len(self.failures)} cleanup failure(s)')


class OwnerState(Enum):
    NEW = auto()
    ACTIVE = auto()
    RETAINED = auto()
    RELEASED = auto()


class TestEnvironmentOwner:
    def __init__(self, home=None, cancellation=None):
        self.path = None
        self._requested_home = home
        self.token = uuid.uuid4().hex
        self.state = OwnerState.NEW
        self._resources = ExitStack()
        request = current_cancellation() if cancellation is None else cancellation
        self.cancellation = CancellationRequest() if request is None else request
        self._cooperative = request is not None
        self._cleanup_failures = []

    @property
    def cleanup_failures(self):
        return tuple(self._cleanup_failures)

    @property
    def cleanup_uncertain(self):
        return self.state is OwnerState.RETAINED

    @property
    def lease_retained(self):
        return self.path is not None and self.cleanup_uncertain

    def _observe(self, error, cleanup=False):
        self.cancellation.observe(error)
        if cleanup and not any(item is error for item in self._cleanup_failures):
            self._cleanup_failures.append(error)

    def __enter__(self):
        self.cancellation.require_main_thread()
        if self.state is not OwnerState.NEW:
            raise RuntimeError('Test environment owner cannot be reused')
        try:
            with defer_cancellation():
                self.state = OwnerState.ACTIVE
                if self._requested_home is not None:
                    self.acquire_lease(self._requested_home)
        except BaseException as error:
            if self._cooperative:
                self.__exit__(type(error), error, error.__traceback__)
            raise
        return self

    def acquire_lease(self, home):
        """Attach a guest reservation before acquiring guest-test resources."""
        self._require_active()
        if self.path is not None:
            raise RuntimeError('Test environment already owns a guest lease')
        path = Path(home) / 'test-environment.lock'
        with defer_cancellation():
            path.mkdir()  # Never adopt or steal another owner's reservation.
            self.path = path
            self.state = OwnerState.RETAINED  # Publication failure must leave the reservation intact.
            try:
                write_record(self.path / 'owner.json', {'pid': os.getpid(), 'identity': identity(os.getpid()),
                             'token': self.token, 'phase': 'active'})
            except BaseException as error:
                self._observe(error, cleanup=True)
                raise
            self.state = OwnerState.ACTIVE

    def retain(self):
        self.cancellation.require_main_thread()
        if self.state in {OwnerState.NEW, OwnerState.RELEASED}:
            raise RuntimeError('Test environment owner is not active')
        if self.state is OwnerState.RETAINED:
            return
        self.state = OwnerState.RETAINED  # Do this before I/O: failed publication must never unlock.
        if self.path is None:
            return  # Local/Docker execution has cleanup ownership without a guest reservation.
        with defer_cancellation():
            path = self.path / 'owner.json'
            record = json.loads(path.read_text())
            if record['token'] != self.token:
                raise RuntimeError('Test lease ownership changed; refusing to overwrite it')
            write_record(path, {**record, 'phase': 'cleanup-uncertain'})

    def cleanup(self, function, *args, **kwargs):
        self.cancellation.require_main_thread()
        if self.state in {OwnerState.NEW, OwnerState.RELEASED}:
            raise RuntimeError('Test environment owner is not active')
        # A stop and its ownership outcome form one handoff. In particular, a
        # second signal must not interrupt failure bookkeeping before retention.
        with defer_cancellation():
            try:
                return function(*args, **kwargs)
            except BaseException as error:
                self._observe(error, cleanup=True)
                try:
                    self.retain()
                except BaseException as publication_error:
                    self._observe(publication_error, cleanup=True)
                    raise
                raise
            finally:
                self._collect_worker_failures()

    def _collect_worker_failures(self):
        if not self._cooperative:
            return
        self.cancellation.collect()
        for error in self.cancellation.cleanup_failures:
            self._observe(error, cleanup=True)
        if self.cancellation.cleanup_failures and self.state is OwnerState.ACTIVE:
            try:
                self.retain()
            except BaseException as error:
                self._observe(error, cleanup=True)
                raise

    def _finish_workers(self):
        if not self._cooperative:
            return
        try:
            self.cancellation.seal_workers()
        except WorkerDrainError as error:
            failure = CleanupUncertain('Owned workers did not finish; retain the test lease')
            self._observe(failure, cleanup=True)
            try:
                self.retain()
            except BaseException as publication_error:
                self._observe(publication_error, cleanup=True)
                raise
            raise failure from error
        finally:
            self._collect_worker_failures()

    def callback(self, function, *args, **kwargs):
        self._require_active()
        self._resources.callback(self.cleanup, function, *args, **kwargs)

    def enter_context(self, manager):
        self._require_active()
        with defer_cancellation():
            value = manager.__enter__()
            self._resources.push(lambda *error: self.cleanup(manager.__exit__, *error))
        return value

    def _require_active(self):
        self.cancellation.require_main_thread()
        if self.state is not OwnerState.ACTIVE:
            raise RuntimeError('Cannot acquire resources outside an active test environment')

    def checkpoint(self):
        self.cancellation.require_main_thread()
        self._collect_worker_failures()
        self.cancellation.checkpoint()

    def wait(self, child):
        self.cancellation.require_main_thread()
        return self.cancellation.wait(child, checkpoint=self.checkpoint) if self._cooperative else child.wait()

    def __exit__(self, kind, error, traceback):
        """Drain owned resources, then propagate the first cancellation unchanged.

        Cleanup failures remain attached as an aggregate cause. A clean cancel
        releases the lease; uncertainty retains it regardless of suppression.
        """
        self.cancellation.require_main_thread()
        final_error = None
        suppressed = False
        if self._cooperative:
            # Freeze cancellation before callbacks. Repeated signals during the
            # drain only record requests and cannot alter this execution result.
            cancellation = self.cancellation.begin_cleanup(error)
            if cancellation is not None and error is None:
                kind, error, traceback = type(cancellation), cancellation, cancellation.__traceback__
        try:
            # Protect the whole drain as well as individual stops: signals
            # between ExitStack callbacks must not abandon a popped resource.
            with defer_cancellation():
                if error is not None:
                    self._observe(error, cleanup=isinstance(error, CleanupUncertain))
                try:
                    suppressed = self._exit_resources(kind, error, traceback)
                except BaseException as cleanup_error:
                    self._observe(cleanup_error, cleanup=True)
                    final_error = cleanup_error
                    if self.state is OwnerState.ACTIVE:
                        try:
                            self.retain()
                        except BaseException as publication_error:
                            self._observe(publication_error, cleanup=True)
                            final_error = publication_error
        except BaseException as deferred_error:
            # Handled signals arrive only after cleanup outcomes are committed.
            self._observe(deferred_error)
            if final_error is None:
                final_error = deferred_error
        if self.cancellation.accepted is None:
            if final_error is not None:
                raise final_error
            return suppressed
        cancellation = self.cancellation.accepted
        failures = [item for item in self._cleanup_failures if item is not cancellation]
        # A transport may already have attached its child-level aggregate.
        cause = cancellation.__cause__
        if cause is not None and not any(item is cause for item in failures):
            failures.insert(0, cause)
        if failures:
            raise cancellation from EnvironmentCleanupError(failures)
        raise cancellation

    def _exit_resources(self, kind, error, traceback):
        try:
            if isinstance(error, CleanupUncertain):
                try:
                    self.retain()
                except BaseException as publication_error:
                    self._observe(publication_error, cleanup=True)
                    raise
        finally:
            # Even failure to publish retention cannot abandon other owned resources.
            try:
                suppressed = self._resources.__exit__(kind, error, traceback)
            finally:
                self._finish_workers()
        if self.state is OwnerState.RETAINED and (suppressed or error is None):
            raise CleanupUncertain('Test environment cleanup remains unconfirmed; lease retained')
        # Release is a positive commit after the complete drain, never a finally
        # action based solely on a possibly stale ACTIVE state.
        if self.state is OwnerState.ACTIVE:
            if self.path is not None:
                path = self.path / 'owner.json'
                record = json.loads(path.read_text())
                if record['token'] != self.token or record.get('phase') != 'active':
                    self.state = OwnerState.RETAINED
                    raise RuntimeError('Test lease ownership changed; refusing release')
                path.unlink()
                self.path.rmdir()
            self.state = OwnerState.RELEASED
        return suppressed
