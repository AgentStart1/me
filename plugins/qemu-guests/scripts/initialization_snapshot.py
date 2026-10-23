"""Immutable project initialization input; records are detached JSON views."""
from dataclasses import dataclass
import json


@dataclass(frozen=True, slots=True, repr=False)
class InitializationSnapshot:
    requirements_bytes: bytes
    record_json: bytes
    guest_files: tuple[tuple[str, bytes], ...]
    guest_hooks_json: bytes

    def record(self):
        return json.loads(self.record_json)


def record_for(config):
    snapshot = config.get('initialization_snapshot')
    return snapshot.record() if snapshot is not None else config.get('runtime_requirements')
