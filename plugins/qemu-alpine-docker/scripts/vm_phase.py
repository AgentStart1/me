"""Immutable lifecycle snapshots and legal transitions, independent of OS/process IO."""
from dataclasses import dataclass, replace
from enum import Enum


class Phase(str, Enum):
    RESERVED = 'reserved'
    NETWORK_STARTING = 'network-starting'
    NETWORK_READY = 'network-ready'
    SPAWNING = 'spawning'
    LAUNCHED = 'launched'
    REGISTERED = 'registered'
    READY = 'ready'
    STOPPING = 'stopping'
    RECOVERY = 'recovery-required'


@dataclass(frozen=True)
class NoProcess:
    """The owner has not invoked process creation, or creation definitively failed."""


@dataclass(frozen=True)
class UnknownProcess:
    """Creation may have occurred, but no PID/identity has been published."""


@dataclass(frozen=True)
class LaunchedProcess:
    shell_pid: int

    def __post_init__(self):
        positive_pid(self.shell_pid)


@dataclass(frozen=True)
class NativeUnknownProcess(UnknownProcess):
    """Native creation may have occurred before its PID was published."""


@dataclass(frozen=True)
class NativeLaunchedProcess(LaunchedProcess):
    """The inherited PID slot carries a native PID, never an MSYS PID."""


@dataclass(frozen=True)
class OwnedProcess:
    shell_pid: int
    native_pid: int
    executable: str
    creation: str | int

    def __post_init__(self):
        positive_pid(self.shell_pid)
        positive_pid(self.native_pid)
        if not isinstance(self.executable, str) or not self.executable or type(self.creation) not in (str, int):
            raise ValueError('Invalid native process identity')

    @classmethod
    def from_record(cls, record):
        executable, creation = record['identity']
        return cls(record['shell_pid'], record['pid'], executable, creation)

    def record(self):
        return {'shell_pid': self.shell_pid, 'pid': self.native_pid, 'identity': [self.executable, self.creation]}


def positive_pid(value):
    if type(value) is not int or not 0 < value < 2**32:
        raise ValueError('Invalid process ID')


Process = NoProcess | UnknownProcess | LaunchedProcess | OwnedProcess

TRANSITIONS = {
    Phase.RESERVED: {Phase.NETWORK_STARTING, Phase.SPAWNING, Phase.LAUNCHED, Phase.STOPPING},
    Phase.NETWORK_STARTING: {Phase.NETWORK_READY, Phase.STOPPING},
    Phase.NETWORK_READY: {Phase.SPAWNING, Phase.STOPPING},
    Phase.SPAWNING: {Phase.NETWORK_READY, Phase.LAUNCHED, Phase.STOPPING},
    Phase.LAUNCHED: {Phase.REGISTERED, Phase.STOPPING},
    Phase.REGISTERED: {Phase.READY, Phase.STOPPING},
    Phase.READY: {Phase.STOPPING},
    Phase.STOPPING: {Phase.RESERVED, Phase.STOPPING},
    Phase.RECOVERY: {Phase.STOPPING},
}


@dataclass(frozen=True)
class Snapshot:
    generation: str
    phase: Phase
    process: Process

    def __post_init__(self):
        if not isinstance(self.generation, str) or not self.generation:
            raise ValueError('Missing reservation generation')
        allowed = {
            Phase.RESERVED: (NoProcess,), Phase.NETWORK_STARTING: (NoProcess,),
            Phase.NETWORK_READY: (NoProcess,), Phase.SPAWNING: (UnknownProcess,),
            Phase.LAUNCHED: (LaunchedProcess,), Phase.REGISTERED: (OwnedProcess,),
            Phase.READY: (OwnedProcess,), Phase.STOPPING: (NoProcess, UnknownProcess, LaunchedProcess, OwnedProcess),
            Phase.RECOVERY: (NoProcess, UnknownProcess, LaunchedProcess, OwnedProcess),
        }
        if not isinstance(self.phase, Phase) or not isinstance(self.process, allowed[self.phase]):
            raise ValueError('Process evidence does not match lifecycle phase')

    def transition(self, phase, process=None):
        if phase != Phase.RECOVERY and phase not in TRANSITIONS[self.phase]:
            raise ValueError(f'Invalid lifecycle transition: {self.phase.value} -> {phase.value}')
        updated = replace(self, phase=phase, process=self.process if process is None else process)
        if phase not in (Phase.RESERVED, Phase.NETWORK_READY):
            if isinstance(self.process, OwnedProcess) and updated.process != self.process:
                raise ValueError('Cannot replace an owned native process identity')
            if isinstance(self.process, LaunchedProcess) and (
                    not isinstance(updated.process, (LaunchedProcess, OwnedProcess)) or
                    updated.process.shell_pid != self.process.shell_pid):
                raise ValueError('Cannot discard or replace the launched PID')
            if isinstance(self.process, UnknownProcess) and isinstance(updated.process, NoProcess):
                raise ValueError('Cannot treat an uncertain launch as absent')
        return updated

    def data(self):
        process = self.process
        if isinstance(process, OwnedProcess):
            evidence = {'kind': 'owned', 'record': process.record()}
        elif isinstance(process, NativeLaunchedProcess):
            evidence = {'kind': 'native-launched', 'pid': process.shell_pid}
        elif isinstance(process, LaunchedProcess):
            evidence = {'kind': 'launched', 'shell_pid': process.shell_pid}
        elif isinstance(process, NativeUnknownProcess):
            evidence = {'kind': 'native-unknown'}
        else:
            evidence = {'kind': 'none' if isinstance(process, NoProcess) else 'unknown'}
        return {'generation': self.generation, 'phase': self.phase.value, 'process': evidence}

    @classmethod
    def from_data(cls, data):
        value = data['process']
        kind = value['kind']
        if kind == 'owned':
            evidence = OwnedProcess.from_record(value['record'])
        elif kind == 'native-launched':
            evidence = NativeLaunchedProcess(value['pid'])
        elif kind == 'native-unknown':
            evidence = NativeUnknownProcess()
        elif kind == 'launched':
            evidence = LaunchedProcess(value['shell_pid'])
        elif kind == 'none':
            evidence = NoProcess()
        elif kind == 'unknown':
            evidence = UnknownProcess()
        else:
            raise ValueError('Unknown lifecycle process evidence')
        return cls(data['generation'], Phase(data['phase']), evidence)
