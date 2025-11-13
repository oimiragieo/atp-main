from __future__ import annotations

import os
import subprocess  # noqa: S404 - controlled commands built from known runners
import sys


def run_tool(path: str, cwd: str | None = None, runner: str | None = None) -> subprocess.CompletedProcess[str]:
    argv: list[str]
    if runner == "node" or (runner is None and path.endswith(".js")):
        argv = ["node", path]
    else:
        argv = [sys.executable, path]
    # Known runners only, caller provides controlled path within repo
    return subprocess.run(argv, cwd=cwd or os.getcwd(), capture_output=True, text=True)  # noqa: S603
