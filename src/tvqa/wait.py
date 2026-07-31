"""Server-side polling primitives. The agent says 'wait until home screen,
up to 30s' and gets ONE JSON line back — the polling loop never enters its
context.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from tvqa.adb import Adb
from tvqa.device import AgentDevice
from tvqa.states import StateRegistry


def poll_until(check_fn: Callable[[], bool], timeout_s: float, interval_s: float = 2.0) -> bool:
    start = time.monotonic()
    while True:
        if check_fn():
            return True
        if time.monotonic() - start >= timeout_s:
            return False
        time.sleep(interval_s)


def state_check_fn(
    registry: StateRegistry,
    name: str,
    *,
    adb: Adb,
    device: AgentDevice,
    work_dir: Path,
) -> Callable[[], bool]:
    """Return a zero-arg check for one state, capturing via device.snapshot (a11y)
    or adb.screenshot (ocr/phash) as the state's method requires. The adb/device
    wrappers are INJECTED by the caller, so the same instances (and, in tests, the
    same mocks) are reused everywhere — this factory never builds its own Adb/
    AgentDevice. Screenshot is reused across polls — overwritten each time, never
    accumulated.
    """
    method = registry.method_of(name)
    shot_path = Path(work_dir) / f"check-{name}.png"

    def check() -> bool:
        if method == "a11y":
            return registry.check(name, snapshot_text=device.snapshot()).matched
        adb.screenshot(shot_path)
        return registry.check(name, screenshot_path=shot_path).matched

    return check
