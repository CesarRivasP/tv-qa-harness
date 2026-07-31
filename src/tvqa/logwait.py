"""Block on `adb logcat`, return the FIRST matching line (or raise on
timeout) instead of ever dumping the full log into the caller's context.
"""
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass


class LogWaitTimeout(TimeoutError):
    pass


@dataclass
class LogWaitResult:
    matched: bool
    line: str
    elapsed_s: float


def wait_for_line(pattern: str, timeout_s: float, serial: str | None = None) -> LogWaitResult:
    regex = re.compile(pattern, re.IGNORECASE)
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += ["logcat"]

    start = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        for line in proc.stdout:
            if regex.search(line):
                return LogWaitResult(matched=True, line=line.strip(), elapsed_s=time.monotonic() - start)
            if time.monotonic() - start > timeout_s:
                break
    finally:
        proc.terminate()

    raise LogWaitTimeout(f"pattern {pattern!r} not seen within {timeout_s}s")
