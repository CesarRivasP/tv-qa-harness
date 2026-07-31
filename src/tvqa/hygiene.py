"""Generalized preflight/cleanup: checks for leftover proxy settings and
wm size/density overrides from a prior test run. Mirrors the project-local
scripts/qa/preflight.sh and cleanup.sh pattern, minus the per-project bits.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field


@dataclass
class HygieneReport:
    clean: bool
    issues: list[str] = field(default_factory=list)


def _adb_get(serial: str, key: str) -> str:
    result = subprocess.run(
        ["adb", "-s", serial, "shell", "settings", "get", "global", key],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def check(serial: str) -> HygieneReport:
    issues: list[str] = []

    http_proxy = _adb_get(serial, "http_proxy")
    host = _adb_get(serial, "global_http_proxy_host")
    port = _adb_get(serial, "global_http_proxy_port")
    if http_proxy != "null" or host != "null" or (port != "null" and port != "0"):
        issues.append(f"proxy configured: http_proxy={http_proxy} host={host} port={port}")

    density = subprocess.run(
        ["adb", "-s", serial, "shell", "wm", "density"], capture_output=True, text=True
    ).stdout
    if "Override" in density:
        issues.append(f"density override present: {density.strip()}")

    size = subprocess.run(
        ["adb", "-s", serial, "shell", "wm", "size"], capture_output=True, text=True
    ).stdout
    if "Override" in size:
        issues.append(f"size override present: {size.strip()}")

    return HygieneReport(clean=len(issues) == 0, issues=issues)


def clean(serial: str) -> HygieneReport:
    for key in ("http_proxy", "global_http_proxy_host", "global_http_proxy_port"):
        subprocess.run(["adb", "-s", serial, "shell", "settings", "delete", "global", key], capture_output=True)
    subprocess.run(["adb", "-s", serial, "shell", "wm", "density", "reset"], capture_output=True)
    subprocess.run(["adb", "-s", serial, "shell", "wm", "size", "reset"], capture_output=True)
    return check(serial)
