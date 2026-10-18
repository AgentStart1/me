"""Windows launch gate: never execute user code before job assignment."""
from pathlib import Path
import json
import subprocess
import sys
import time


def main():
    gate = Path(sys.argv[1])
    while not gate.exists():
        time.sleep(.01)
    try:
        child = subprocess.Popen(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
    except OSError:
        return 127
    return child.wait()


if __name__ == "__main__":
    sys.exit(main())
