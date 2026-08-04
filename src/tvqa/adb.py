"""Thin subprocess wrapper around adb. No image or log parsing lives here."""
from __future__ import annotations

import socket
import subprocess
from pathlib import Path


class AdbError(RuntimeError):
    pass


class Adb:
    def __init__(self, serial: str | None = None):
        self.serial = serial

    def _base(self) -> list[str]:
        cmd = ["adb"]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd

    def _run(self, args: list[str], capture_bytes: bool = False):
        result = subprocess.run(
            args,
            capture_output=True,
            text=not capture_bytes,
        )
        if result.returncode != 0:
            raise AdbError(f"{' '.join(args)} failed: {result.stderr!r}")
        return result.stdout

    def devices(self) -> list[str]:
        out = self._run(["adb", "devices"])
        lines = out.strip().splitlines()[1:]
        return [line.split("\t")[0] for line in lines if line.strip().endswith("device")]

    def shell(self, command: str) -> str:
        return self._run(self._base() + ["shell", command])

    def keyevent(self, code: int | str) -> None:
        """code: numeric (23) or named (DPAD_CENTER) — input keyevent accepts both."""
        self._run(self._base() + ["shell", "input", "keyevent", str(code)])

    def screenshot(self, out_path: Path) -> Path:
        data = self._run(self._base() + ["exec-out", "screencap", "-p"], capture_bytes=True)
        out_path = Path(out_path)
        out_path.write_bytes(data)
        return out_path

    def logcat_clear(self) -> None:
        self._run(self._base() + ["logcat", "-c"])

    def wifi_enable(self) -> None:
        self._run(self._base() + ["shell", "svc", "wifi", "enable"])

    def wifi_disable(self) -> None:
        """On a physical device controlled over wireless adb, this kills the
        transport it runs over (wifi IS the control channel) — the command
        itself succeeds but every subsequent adb call to this serial hangs.
        Requires USB transport (separate "USB debugging" toggle, not "Wireless
        debugging") for physical devices. Emulators are unaffected.
        """
        self._run(self._base() + ["shell", "svc", "wifi", "disable"])


def resolve_serial(serial: str | None, fallback: str = "emulator-5554") -> str:
    """serial if given, else the sole attached adb device, else fallback.
    Lets project.yaml/callers skip hardcoding a device-specific serial —
    whichever single device is plugged in wins. Ambiguous (0 or 2+ attached)
    falls through to fallback rather than guessing.
    """
    if serial:
        return serial
    found = Adb().devices()
    return found[0] if len(found) == 1 else fallback


def lan_ip() -> str:
    """This machine's real LAN-facing IP, for proxy.host_ip on a physical
    device — NOT the "10.0.2.2" alias, which only resolves inside the
    emulator's QEMU NAT. UDP "connect" sends no packets; it just makes the OS
    pick the outbound interface/IP for a real route, same trick as
    `ipconfig getifaddr en0` without hardcoding an interface name.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()
