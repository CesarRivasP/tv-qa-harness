"""Wraps the mitmdump lifecycle: launch with a project-supplied addon script
and env vars, point the device's global http_proxy at it, and on stop kill
the process AND clear all three proxy settings keys. Deleting only
`http_proxy` leaves a dead proxy configured -> ECONNREFUSED on every request
until the other two keys are cleared too; this class always clears all three.
"""
from __future__ import annotations

import os
import subprocess


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
