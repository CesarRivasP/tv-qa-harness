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


def wait_for_line(
    pattern: str,
    timeout_s: float,
    serial: str | None = None,
    *,
    clear_buffer: bool = True,
    min_s: float = 0.0,
) -> LogWaitResult:
    """Block on `adb logcat`, return the FIRST matching line (or raise on timeout).

    *clear_buffer* (default True) runs `logcat -c` before tailing so stale ring-
    buffer lines from earlier attempts don't produce false positives.
    Set to False only when the event of interest may have already fired slightly
    before the wait begins.

    *min_s* (default 0) treats a match that arrives faster than this threshold as
    suspicious (likely a stale/background line) and raises LogWaitTimeout instead.
    This catches phantom passes when the buffer clear races with an injected fault.
    """
    regex = re.compile(pattern, re.IGNORECASE)
    base = ["adb"]
    if serial:
        base += ["-s", serial]

    if clear_buffer:
        subprocess.run(base + ["logcat", "-c"], capture_output=True, text=True)

    start = time.monotonic()
    proc = subprocess.Popen(base + ["logcat"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        for line in proc.stdout:
            elapsed = time.monotonic() - start
            if regex.search(line):
                if elapsed < min_s:
                    proc.terminate()
                    raise LogWaitTimeout(
                        f"pattern {pattern!r} matched too fast ({elapsed:.1f}s < {min_s}s min); "
                        "likely stale/background line"
                    )
                return LogWaitResult(matched=True, line=line.strip(), elapsed_s=elapsed)
            if elapsed > timeout_s:
                break
    finally:
        proc.terminate()

    raise LogWaitTimeout(f"pattern {pattern!r} not seen within {timeout_s}s")
