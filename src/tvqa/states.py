"""Declarative per-project screen states loaded from states.yaml. Three methods:
- a11y:  substring match against an agent-device accessibility snapshot (text).
         Resolution-independent — the preferred tier.
- phash: perceptual hash of a screenshot region (fast, brittle to layout changes).
- ocr:   tesseract substring match on a screenshot region (for poor a11y trees).
Adding a new detectable screen means editing YAML, not code.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from tvqa.verify import region_contains_text, region_matches


@dataclass
class StateResult:
    state: str
    matched: bool
    detail: str


class StateRegistry:
    def __init__(self, states: dict):
        self._states = states

    @classmethod
    def load(cls, config_path: Path) -> "StateRegistry":
        data = yaml.safe_load(Path(config_path).read_text())
        return cls(data.get("states", {}))

    def names(self) -> list[str]:
        return list(self._states.keys())

    def method_of(self, name: str) -> str:
        if name not in self._states:
            raise KeyError(f"unknown state: {name!r}. known: {self.names()}")
        return self._states[name]["method"]

    def check(
        self,
        name: str,
        screenshot_path: Path | None = None,
        snapshot_text: str | None = None,
    ) -> StateResult:
        if name not in self._states:
            raise KeyError(f"unknown state: {name!r}. known: {self.names()}")
        spec = self._states[name]
        method = spec["method"]

        if method == "a11y":
            if snapshot_text is None:
                raise ValueError(f"state {name!r} (method a11y) requires snapshot_text")
            matched = spec["expected_text"].lower() in snapshot_text.lower()
            detail = f"a11y expected_text={spec['expected_text']!r}"
        elif method == "ocr":
            if screenshot_path is None:
                raise ValueError(f"state {name!r} (method ocr) requires screenshot_path")
            box = tuple(spec["box"])
            matched = region_contains_text(screenshot_path, box, spec["expected_substring"])
            detail = f"ocr substring={spec['expected_substring']!r}"
        elif method == "phash":
            if screenshot_path is None:
                raise ValueError(f"state {name!r} (method phash) requires screenshot_path")
            box = tuple(spec["box"])
            matched = region_matches(
                screenshot_path,
                box,
                expected_hash=spec["expected_hash"],
                max_distance=spec.get("max_distance", 8),
            )
            detail = f"phash expected={spec['expected_hash']} max_distance={spec.get('max_distance', 8)}"
        else:
            raise ValueError(f"unknown method {method!r} for state {name!r}")

        return StateResult(state=name, matched=matched, detail=detail)

    def check_all(
        self,
        screenshot_path: Path | None = None,
        snapshot_text: str | None = None,
    ) -> list[StateResult]:
        return [
            self.check(name, screenshot_path=screenshot_path, snapshot_text=snapshot_text)
            for name in self.names()
        ]
