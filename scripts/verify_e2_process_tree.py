"""Exercise the E2 OCR subprocess budget inside the Linux backend image.

The script uses only the standard library and installed application runtime
packages, so an isolated Compose network does not need PyPI or pytest.
"""

from __future__ import annotations

import os
import signal
import sys
import tempfile
import time
from pathlib import Path

from app.jobs.worker import communicate_bounded, spawn_child
from housing_engine import EngineError


def stopped(pid: int) -> bool:
    stat = Path(f"/proc/{pid}/stat")
    return not stat.exists() or stat.read_text().split()[2] == "Z"


def verify_case(directory: Path, orphan_leader: bool) -> None:
    pid_file = directory / ("orphan.pid" if orphan_leader else "live.pid")
    program = (
        "import pathlib,subprocess,sys,time;"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)']);"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid));"
        + ("" if orphan_leader else "time.sleep(20)")
    )
    parent = spawn_child([sys.executable, "-c", program])
    grandchild_pid: int | None = None
    try:
        for _ in range(100):
            if pid_file.exists():
                break
            time.sleep(0.02)
        if not pid_file.exists():
            raise AssertionError("OCR parent did not spawn a grandchild")
        grandchild_pid = int(pid_file.read_text())
        if orphan_leader:
            for _ in range(50):
                if parent.poll() is not None:
                    break
                time.sleep(0.02)
            if parent.poll() is None:
                raise AssertionError("OCR leader did not exit before its grandchild")

        try:
            communicate_bounded(parent, b"", 0.25, lambda: True)
        except EngineError as error:
            if error.code != "OCR_TIMEOUT":
                raise AssertionError(f"unexpected OCR failure: {error.code}") from error
        else:
            raise AssertionError("OCR parent exceeded its budget without timeout")
        if parent.poll() is None:
            raise AssertionError("OCR parent survived the timeout")

        for _ in range(50):
            if stopped(grandchild_pid):
                break
            time.sleep(0.02)
        else:
            raise AssertionError("OCR grandchild survived the process-group kill")
    finally:
        try:
            os.killpg(parent.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if grandchild_pid is not None and not stopped(grandchild_pid):
            os.kill(grandchild_pid, signal.SIGKILL)
        parent.communicate(timeout=2)


def main() -> None:
    if not sys.platform.startswith("linux"):
        raise RuntimeError("This process-group check requires Linux /proc")

    with tempfile.TemporaryDirectory(prefix="zhkh-e2-tree-") as directory:
        verify_case(Path(directory), orphan_leader=False)
        verify_case(Path(directory), orphan_leader=True)

    print("E2 OCR process-group timeout killed live and orphaned grandchildren: OK")


if __name__ == "__main__":
    main()
