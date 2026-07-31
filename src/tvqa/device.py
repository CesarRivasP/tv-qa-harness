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
    def __init__(self, platform: str = "android"):
        self.platform = platform

    def _run(self, args: list[str]) -> str:
        result = subprocess.run(["agent-device", *args], capture_output=True, text=True)
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
