"""Wraps the mitmdump lifecycle: launch with a project-supplied addon script
and env vars, point the device's global http_proxy at it, and on stop kill
the process AND clear all three proxy settings keys. Deleting only
`http_proxy` leaves a dead proxy configured -> ECONNREFUSED on every request
until the other two keys are cleared too; this class always clears all three.
"""
from __future__ import annotations

import os
import subprocess


# mode presets → (addon_alias, default_env)
MODES: dict[str, tuple[str, dict[str, str]]] = {
    "token403": ("epic_stall", {"EPIC_MODE": "token403", "EPIC_EXPIRE_AFTER_S": "45"}),
    "blackhole": (
        "epic_stall",
        {"EPIC_MODE": "blackhole", "EPIC_BLACKHOLE_AFTER_S": "45", "EPIC_BLACKHOLE_DURATION_S": "40"},
    ),
    "origin403": ("epic_stall", {"EPIC_MODE": "origin403", "EPIC_EXPIRE_AFTER_S": "30"}),
    "vodswap": (
        "epic_stall",
        {"EPIC_MODE": "vodswap", "EPIC_TARGET_PROXY": "proxy2", "EPIC_TARGET_SPEED_FAIL": "502"},
    ),
    "auth_expired": ("auth_expired", {}),
    "auth_revoke": ("auth_revoke", {}),
}


def resolve_mode(mode: str, addons: dict[str, str], env: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    """Resolve a proxy mode name to an (addon_path, env_dict) pair.

    *mode* must exist in MODES. *addons* is the registry from project.yaml.
    Optional *env* overrides the preset defaults (e.g. changing EPIC_EXPIRE_AFTER_S).
    """
    if mode not in MODES:
        raise ValueError(f"Unknown proxy mode {mode!r}. Known: {list(MODES)}")
    alias, defaults = MODES[mode]
    if alias not in addons:
        raise ValueError(
            f"Proxy mode {mode!r} needs addon alias {alias!r}, "
            f"but it is missing from project.yaml proxy.addons"
        )
    addon_path = addons[alias]
    final_env = {**defaults, **(env or {})}
    return addon_path, final_env


class ProxyHarness:
    def __init__(self, serial: str, host_ip: str, port: int = 8080):
        self.serial = serial
        self.host_ip = host_ip
        self.port = port
        self._proc: subprocess.Popen | None = None

    def _adb(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["adb", "-s", self.serial, *args], capture_output=True, text=True)

    def start(self, addon_path: str, env: dict[str, str]) -> None:
        full_env = {**os.environ, **env}
        self._proc = subprocess.Popen(
            ["mitmdump", "-s", addon_path, "-p", str(self.port)],
            env=full_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._adb("shell", "settings", "put", "global", "http_proxy", f"{self.host_ip}:{self.port}")

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            self._proc = None
        for key in ("http_proxy", "global_http_proxy_host", "global_http_proxy_port"):
            self._adb("shell", "settings", "delete", "global", key)
