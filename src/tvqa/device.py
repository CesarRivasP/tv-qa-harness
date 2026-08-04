"""Thin subprocess wrapper around the agent-device CLI (Callstack). This is the
interaction layer: open apps, read accessibility snapshots as TEXT, press refs.
Screenshots always go to disk — this module never returns image bytes.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class AgentDeviceError(RuntimeError):
    pass


class AgentDevice:
    def __init__(self, platform: str = "android", device: str | None = None,
                 session: str | None = None):
        self.platform = platform
        # device: agent-device target name-or-udid (e.g. a physical serial). When
        # None, agent-device auto-picks / follows the bound session — fine for a
        # single emulator, but a physical device MUST be named or agent-device
        # falls back to the stale default-session binding (usually emulator-5554).
        self.device = device
        # session: agent-device sessions are cwd-keyed and the "default" one is
        # often pre-bound to an emulator. A dedicated named session bound to our
        # --device sidesteps that collision across runs and working directories.
        self.session = session

    def _run(self, args: list[str]) -> str:
        cmd = ["agent-device", *args]
        if self.session:
            cmd += ["--session", self.session]
        if self.device:
            cmd += ["--device", self.device]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise AgentDeviceError(f"agent-device {' '.join(args)} failed: {result.stderr!r}")
        return result.stdout

    def open_app(self, name: str) -> None:
        self._run(["open", name, "--platform", self.platform])

    def snapshot(self, interactive_only: bool = True) -> str:
        """Accessibility tree as compact text. interactive_only (-i) keeps it token-cheap."""
        args = ["snapshot"]
        if interactive_only:
            args.append("-i")
        return self._run(args)

    def press(self, ref: str) -> str:
        """Press an element by snapshot ref (@eN). Returns the post-settle diff text."""
        return self._run(["press", ref, "--settle"])

    def screenshot(self, out_path: Path) -> Path:
        out_path = Path(out_path)
        self._run(["screenshot", str(out_path)])
        return out_path

    def close(self) -> None:
        self._run(["close"])

    def dismiss_rn_overlay(self) -> str:
        """Dismiss a React Native dev warning/error (LogBox) overlay if present.
        No-op-safe: agent-device verifies it's gone, doesn't error if there was
        none to begin with. More reliable than guessing a keyevent for LogBox,
        which doesn't always close on DPAD_CENTER.
        """
        return self._run(["react-native", "dismiss-overlay"])
