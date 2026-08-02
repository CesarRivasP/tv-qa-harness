"""Generalized preflight/cleanup: checks for leftover proxy settings,
active Private DNS (DoT breaks name resolution on the AVD), and wm
size/density overrides from a prior test run. Mirrors the project-local
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

    # Private DNS (DNS-over-TLS): on this AVD the QEMU resolver only serves
    # plaintext DNS on :53, so opportunistic DoT (:853) fails the handshake and
    # doesn't fall back cleanly -> `resolv: Validation failed` -> name resolution
    # dies -> the app can't reach its backend. `null` is the opportunistic
    # default and is NOT safe; the mode must be exactly "off".
    private_dns = _adb_get(serial, "private_dns_mode")
    if private_dns != "off":
        issues.append(f"private DNS active: private_dns_mode={private_dns} (must be 'off')")

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
    # Force Private DNS off (DoT breaks name resolution on the AVD).
    subprocess.run(["adb", "-s", serial, "shell", "settings", "put", "global", "private_dns_mode", "off"], capture_output=True)
    subprocess.run(["adb", "-s", serial, "shell", "wm", "density", "reset"], capture_output=True)
    subprocess.run(["adb", "-s", serial, "shell", "wm", "size", "reset"], capture_output=True)
    return check(serial)
