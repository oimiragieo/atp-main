import json  # noqa: I001 grouped intentionally for readability
import os  # noqa: I001
import subprocess  # noqa: I001
import sys  # noqa: I001
import time  # noqa: I001
from collections.abc import Sequence  # noqa: I001
from dataclasses import dataclass, asdict  # noqa: I001

_LOG_JSON = os.environ.get("TEST_JSON_LOG", "0") == "1"


@dataclass(slots=True)
class ToolRunRecord:
    cmd: list[str]
    cwd: str | None
    returncode: int
    duration_ms: int
    stdout_snip: str
    stderr_snip: str

    def emit(self) -> None:  # side-effect logging only in tests
        if _LOG_JSON:
            print(json.dumps({"tool_run": asdict(self)}))
        else:
            print(f"[tool-run] rc={self.returncode} ms={self.duration_ms} cmd={' '.join(self.cmd)}")


def run_tool(
    rel_path: str, *args: str, cwd: str | None = None, runner: str | None = None
) -> subprocess.CompletedProcess:
    """Run a tool script with an optional explicit runner.

    If runner is None, Python (sys.executable) is used. When runner is provided
    (e.g. 'node'), that binary is invoked instead and rel_path passed directly.
    """
    # Accept only simple arg tokens (no spaces) to avoid injection risk
    for a in args:
        if not a or any(c.isspace() for c in a):  # defensive
            raise ValueError("invalid argument token")
    # Choose invocation binary
    bin_exec = sys.executable if runner in (None, "", "python") else runner
    cmd: Sequence[str] = (bin_exec, rel_path, *args)
    start = time.time()
    proc = subprocess.run(  # noqa: S603 -- arguments are fully controlled test inputs
        cmd, cwd=cwd, capture_output=True, text=True, check=True
    )
    dur_ms = int((time.time() - start) * 1000)
    # Emit structured summary (first 200 chars each stream)
    rec = ToolRunRecord(
        cmd=list(cmd),
        cwd=cwd,
        returncode=proc.returncode,
        duration_ms=dur_ms,
        stdout_snip=proc.stdout[:200],
        stderr_snip=proc.stderr[:200],
    )
    rec.emit()
    return proc
