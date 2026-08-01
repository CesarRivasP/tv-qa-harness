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
    base = ["adb"]
    if serial:
        base += ["-s", serial]

    # Only match lines produced AFTER this call. Plain `adb logcat` first replays the
    # entire ring buffer, so a stale backlog line (e.g. a `playerFailed` from an earlier
    # attempt, or ever-present `ReactNativeJS` spam) matches instantly -> false positive.
    # Clear the buffer first so the tail reflects only real, post-injection events.
    # (Buffer clear is the same primitive the suite's manual procedure uses: `logcat -c`.)
    subprocess.run(base + ["logcat", "-c"], capture_output=True, text=True)

    start = time.monotonic()
    proc = subprocess.Popen(base + ["logcat"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        for line in proc.stdout:
            if regex.search(line):
                return LogWaitResult(matched=True, line=line.strip(), elapsed_s=time.monotonic() - start)
            if time.monotonic() - start > timeout_s:
                break
    finally:
        proc.terminate()

    raise LogWaitTimeout(f"pattern {pattern!r} not seen within {timeout_s}s")
