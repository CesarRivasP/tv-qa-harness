# tv-qa-harness MVP Implementation Plan

> **For agentic workers:** the specialized `superpowers:subagent-driven-development` /
> `superpowers:executing-plans` skills are not installed in this environment. Execute this plan
> task-by-task in the current session (or via ordinary `Agent` subagent calls), checking off each
> `- [ ]` box as you go, and pausing for human review between tasks per the usual commit discipline.

**Goal:** A standalone CLI tool that drives Android TV (RN-based) apps and returns compact,
verified **text** results to an LLM coding agent — never raw screenshots by default — so
device-driven E2E sessions stop burning the bulk of their token budget on image reads. Success is
measured in **tokens per verified step**: an entire e2e flow should cost the agent one round trip
(~60 tokens of output), not one round trip per step.

**Architecture:** A Python CLI (`tvqa`) with five layers:

1. **Interaction layer** — [agent-device](https://github.com/callstack/agent-device) (Callstack,
   npm global CLI, Node 22.12+) drives the app: `open`, `snapshot -i`, `press @ref`, screenshots.
   Android TV is a first-class target for it (ADB + snapshot helper). A thin `adb` subprocess
   wrapper stays for **system** operations agent-device doesn't expose as primitives: `settings
   put/get` (proxy keys), `wm size/density`, `logcat -c`, and fallback screenshots.
2. **Verification layer** — three tiers, all running **locally** (images never reach the LLM):
   `a11y` (substring/role match against the agent-device accessibility snapshot — resolution-
   independent, the preferred tier), `phash` (perceptual-hash region matching), `ocr` (tesseract
   on a cropped region, for screens with poor accessibility trees: video players, native modals,
   splash screens).
3. **Declarative layer** — per-project `states.yaml` ("what a known screen looks like") and
   `flows/*.yaml` ("what a known e2e journey looks like": actions, waits, assertions, proxy
   fault injection).
4. **Runner** — `tvqa run flow.yaml` executes a whole flow locally (keyevents, agent-device
   presses, state waits, log waits, mitmproxy start/stop) and prints **one** JSON summary line.
   This is the centerpiece: ~50 agent round trips collapse into 1.
5. **Proxy/hygiene layer** — generalizes the mitmproxy-harness lifecycle (start/stop, the
   3-proxy-key cleanup gotcha, `wm size`/`density` resets) already hand-rolled per-project today.

**Token-budget rules (the point of the whole design):**

1. Images **never** enter the LLM context by default. All verification runs locally; the agent
   receives a verdict, not a picture.
2. Every command prints ONE compact JSON line. No banners, no tables, no log dumps.
3. Evidence (screenshots on failure) is written to disk; the JSON carries only the **path**. The
   agent reads that PNG only when a step failed and `detail` doesn't explain why.
4. Orchestration lives in `flow.yaml`, executed server-side by `tvqa run` — one agent round trip
   per flow, not per step.

**Tech Stack:** Python 3.11+, `click` (CLI), `Pillow` + `imagehash` (region hashing),
`pytesseract` (OCR, requires system `tesseract` binary), `PyYAML` (config), `pytest`
(tests use `unittest.mock` + pytest's built-in `monkeypatch`; no real device required for the
unit suite). Node 22.12+ with
`agent-device` installed globally (`npm install -g agent-device@latest`) for the interaction
layer.

> **Facts registry:** Shared infrastructure constants (serial, resolution, proxy host/port,
> Node version, OCR languages, app identifiers, version) live in `_facts.yml` in this directory.
> Hardcoded values below are sourced from that registry; edit the registry and run `sync` to
> propagate changes mechanically.

---

## Context: why this exists

During a live E2E run against epic-app (Android TV emulator), the agent drove the emulator with
raw `adb` and verified each screen via `adb exec-out screencap` piped into a `Read` of the PNG.
Over ~110 such round trips in a single session this consumed the majority of a multi-hour token
budget in a few minutes of wall-clock time — **a 5-hour subscription allowance gone in ~5
minutes**. Each image read costs on the order of 1–2K+ tokens regardless of whether the screen
changed in any meaningful way. The fix is to push "did the screen change to what I expect"
verification **out of the LLM and into a script**: an accessibility-snapshot match, a perceptual
hash of a known region, or OCR for dynamic text can answer "is this the login screen /
channel-unavailable screen / home screen" in well under a second and return one JSON line. The
agent only ever pulls an actual image when verification fails inexplicably — a rare path.

A secondary, smaller win: `logcat` tails and mitmproxy diagnostic logs were repeatedly dumped
into the conversation as multi-hundred-line `tail`/`rg` outputs. A blocking `log-wait` primitive
that returns only the matched line (or "timeout, no match") removes that noise too.

### Why agent-device and not raw adb for interaction

Raw adb interaction is what the failed session used; this MVP deliberately experiments with
**agent-device as the interaction/inspection layer** instead:

- `snapshot -i` returns the accessibility tree as compact text (`@e2 [button] "Sign In"`) —
  token-cheap and resolution-independent, unlike pixel-crop OCR which breaks when the AVD
  resolution/density baseline changes.
- `press @ref` is more robust than blind DPAD keyevent sequences **when** the snapshot exposes
  what's needed — this is the open question Task 13 validates on real hardware (see its
  decision criteria). DPAD keyevents via `adb.py` remain a supported flow step regardless.
- It ships its own MCP server (`agent-device mcp`), removing "write an MCP wrapper" from our
  backlog.

What agent-device does **not** replace in this harness: local phash/OCR verification (fallback
for poor a11y trees), blocking `log-wait`, the mitmproxy lifecycle, and device hygiene — those
stay, and are the parts that make flows *verifiable*, not just *driveable*.

## File Structure

```
tv-qa-harness/
  pyproject.toml
  README.md
  src/tvqa/
    __init__.py
    cli.py            # click CLI, subcommand wiring — Task 9, Task 12
    adb.py             # subprocess wrapper: devices/shell/keyevent/screenshot/logcat — Task 2
    device.py           # subprocess wrapper around the agent-device CLI — Task 3
    verify.py            # region-hash + OCR matcher — Task 4, Task 5
    states.py             # states.yaml loader + match orchestration (a11y/phash/ocr) — Task 6
    logwait.py             # blocking logcat-tail-and-match — Task 7
    wait.py                 # poll_until + state check-fn factory — Task 8
    proxy.py                 # mitmdump lifecycle wrapper — Task 10
    hygiene.py                # preflight/cleanup, generalized — Task 11
    runner.py                  # flow.yaml executor — Task 12
  projects/
    epic-app/
      states.yaml            # dogfood config for epic-app — Task 13
      project.yaml
      flows/
        login.yaml
        network_fault_recovery.yaml
  tests/
    fixtures/
      channel_unavailable.png    # generated by make_text_fixture.py (Task 5)
    test_scaffold.py
    test_adb.py
    test_device.py
    test_verify.py
    test_states.py
    test_logwait.py
    test_wait.py
    test_proxy.py
    test_hygiene.py
    test_cli.py
    test_runner.py
  scripts/
    check_tesseract.sh
    check_agent_device.sh
```

One file, one responsibility: `adb.py`/`device.py` never parse images or snapshots,
`verify.py` never shells out, `states.py` only orchestrates matching, `runner.py` only sequences
steps — this keeps each module small enough to hold in context and edit confidently.

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/tvqa/__init__.py`
- Create: `README.md`
- Create: `scripts/check_tesseract.sh`
- Test: `tests/test_scaffold.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scaffold.py
import tvqa


def test_package_importable():
    assert hasattr(tvqa, "__version__")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scaffold.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tvqa'`

- [ ] **Step 3: Write minimal implementation**

```toml
# pyproject.toml
[project]
name = "tvqa"
version = "0.1.0"
description = "Text-first QA harness for driving RN TV apps without burning vision tokens on screenshots"
requires-python = ">=3.11"
dependencies = [
    "click>=8.1",
    "Pillow>=10.0",
    "imagehash>=4.3",
    "pytesseract>=0.3.10",
    "PyYAML>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
tvqa = "tvqa.cli:main"

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

```python
# src/tvqa/__init__.py
__version__ = "0.1.0"
```

````markdown
# README.md

# tv-qa-harness

Text-first QA driver for React Native TV apps (Android TV today). Verifies screen state via
accessibility snapshots (agent-device), perceptual-hash region matching, and OCR instead of
returning raw screenshots to an LLM agent, runs declarative e2e flows locally, and wraps the
mitmproxy network-fault-injection lifecycle used for E2E regression testing.

## Install

    pip install -e ".[dev]"
    npm install -g agent-device@latest    # interaction layer, needs Node 22.12+
    ./scripts/check_tesseract.sh          # verifies the system tesseract binary is present
    ./scripts/check_agent_device.sh       # verifies node version + agent-device doctor

## Quickstart

    tvqa devices
    tvqa state check --states-file projects/epic-app/states.yaml --state home_screen_rail
    tvqa state which --states-file projects/epic-app/states.yaml
    tvqa log-wait "self-heal.*exhausted" --timeout 60
    tvqa run projects/epic-app/flows/login.yaml --project projects/epic-app

## Token-budget rules for agents driving this CLI

- Never `Read` a PNG unless a `tvqa run`/`state check` returned `passed: false` /
  `matched: false` AND the `detail`/`evidence` fields don't explain the failure.
- Prefer `tvqa run <flow>` (one round trip per flow) over step-by-step command sequences.
- `tvqa snapshot` is for humans calibrating states.yaml, not for routine agent verification.
````

```bash
#!/usr/bin/env bash
# scripts/check_tesseract.sh — verify the OCR fallback tier is operational.
set -euo pipefail

if ! command -v tesseract >/dev/null; then
  echo "tesseract not found. Install: brew install tesseract (macOS) / apt install tesseract-ocr (Debian)" >&2
  exit 1
fi
tesseract --version | head -1
# spa+eng is the default OCR lang pair (see verify.ocr_text_of_region / _facts.yml: infra.ocr_languages); warn if spa missing.
if ! tesseract --list-langs 2>&1 | grep -qx spa; then
  echo "warning: 'spa' language data absent; Spanish-screen OCR will be weak (install tesseract-lang / tesseract-ocr-spa)" >&2
fi
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pip install -e . && chmod +x scripts/check_tesseract.sh && pytest tests/test_scaffold.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git init
git add pyproject.toml src/tvqa/__init__.py README.md scripts/check_tesseract.sh tests/test_scaffold.py
git commit -m "chore: scaffold tvqa package"
```

---

## Task 2: ADB wrapper

**Files:**
- Create: `src/tvqa/adb.py`
- Test: `tests/test_adb.py`

`adb` stays for **system** operations (settings/wm/logcat/fallback screenshots) and DPAD
keyevents — agent-device doesn't expose those as primitives.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_adb.py
from unittest.mock import patch, MagicMock
from tvqa.adb import Adb


def test_devices_parses_serials():
    # → _facts.yml: infra.default_serial
    fake_output = "List of devices attached\nemulator-5554\tdevice\n\n"
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout=fake_output, returncode=0)
        adb = Adb()
        assert adb.devices() == ["emulator-5554"]


def test_shell_passes_serial_flag():
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout="ok\n", returncode=0)
        adb = Adb(serial="emulator-5554")  # → _facts.yml: infra.default_serial
        adb.shell("echo hi")
        args = run.call_args[0][0]
        assert args[:4] == ["adb", "-s", "emulator-5554", "shell"]


def test_tap_sends_keyevent():
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout="", returncode=0)
        adb = Adb(serial="emulator-5554")  # → _facts.yml: infra.default_serial
        adb.keyevent(23)
        args = run.call_args[0][0]
        assert args == ["adb", "-s", "emulator-5554", "shell", "input", "keyevent", "23"]


def test_screenshot_writes_png(tmp_path):
    png_bytes = b"\x89PNG\r\n\x1a\nrest-of-fake-png"
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout=png_bytes, returncode=0)
        adb = Adb(serial="emulator-5554")  # → _facts.yml: infra.default_serial
        out = tmp_path / "shot.png"
        adb.screenshot(out)
        assert out.read_bytes() == png_bytes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_adb.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tvqa.adb'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tvqa/adb.py
"""Thin subprocess wrapper around adb. No image or log parsing lives here."""
from __future__ import annotations

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_adb.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tvqa/adb.py tests/test_adb.py
git commit -m "feat: add adb subprocess wrapper"
```

---

## Task 3: agent-device wrapper

**Files:**
- Create: `src/tvqa/device.py`
- Create: `scripts/check_agent_device.sh`
- Test: `tests/test_device.py`

The interaction layer of the experiment: thin subprocess wrapper over the `agent-device` CLI,
same shape as `adb.py`. Returns snapshot **text**, never images.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_device.py
from unittest.mock import patch, MagicMock
from tvqa.device import AgentDevice


def test_open_app_invokes_agent_device_open():
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout="", returncode=0)
        dev = AgentDevice(platform="android")
        dev.open_app("EpicTV")  # → _facts.yml: dogfood.app_name
        args = run.call_args[0][0]
        assert args == ["agent-device", "open", "EpicTV", "--platform", "android"]


def test_snapshot_returns_text():
    snapshot_text = '@e1 [heading] "Settings"\n@e2 [button] "Sign In"\n'
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout=snapshot_text, returncode=0)
        dev = AgentDevice()
        assert dev.snapshot() == snapshot_text
        args = run.call_args[0][0]
        assert args == ["agent-device", "snapshot", "-i"]


def test_press_passes_ref_with_settle():
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout="", returncode=0)
        dev = AgentDevice()
        dev.press("@e2")
        args = run.call_args[0][0]
        assert args == ["agent-device", "press", "@e2", "--settle"]


def test_screenshot_goes_to_disk_not_stdout(tmp_path):
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout="", returncode=0)
        dev = AgentDevice()
        out = tmp_path / "evidence.png"
        dev.screenshot(out)
        args = run.call_args[0][0]
        assert args == ["agent-device", "screenshot", str(out)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_device.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tvqa.device'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tvqa/device.py
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
```

```bash
#!/usr/bin/env bash
# scripts/check_agent_device.sh — verify the interaction layer is operational.
set -euo pipefail

node_ver=$(node --version | sed 's/^v//')
node_major=${node_ver%%.*}
node_minor=$(echo "$node_ver" | cut -d. -f2)
if [ "$node_major" -lt 22 ] || { [ "$node_major" -eq 22 ] && [ "$node_minor" -lt 12 ]; }; then
  echo "Node >= 22.12 required, found v$node_ver" >&2
  exit 1
fi
if ! command -v agent-device >/dev/null; then
  echo "agent-device not found. Install: npm install -g agent-device@latest" >&2
  exit 1
fi
agent-device doctor
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_device.py -v && chmod +x scripts/check_agent_device.sh`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tvqa/device.py tests/test_device.py scripts/check_agent_device.sh
git commit -m "feat: add agent-device interaction wrapper"
```

---

## Task 4: Region perceptual-hash verification

**Files:**
- Create: `src/tvqa/verify.py`
- Test: `tests/test_verify.py`

(The phash tests build their own solid-color images in `tmp_path` — no committed image fixture; the OCR fixture arrives in Task 5.)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verify.py
from PIL import Image
from tvqa.verify import region_matches, phash_of_region


def _make_image(path, color):
    img = Image.new("RGB", (200, 100), color=color)
    img.save(path)
    return path


def test_phash_of_region_is_stable_for_same_image(tmp_path):
    img_path = _make_image(tmp_path / "a.png", (255, 0, 0))
    h1 = phash_of_region(img_path, box=(0, 0, 200, 100))
    h2 = phash_of_region(img_path, box=(0, 0, 200, 100))
    assert h1 == h2


def test_region_matches_true_for_identical_color(tmp_path):
    reference = _make_image(tmp_path / "ref.png", (10, 20, 30))
    candidate = _make_image(tmp_path / "cand.png", (10, 20, 30))
    ref_hash = phash_of_region(reference, box=(0, 0, 200, 100))
    assert region_matches(candidate, box=(0, 0, 200, 100), expected_hash=ref_hash, max_distance=5)


def test_region_matches_false_for_very_different_color(tmp_path):
    reference = _make_image(tmp_path / "ref.png", (10, 20, 30))
    candidate = _make_image(tmp_path / "cand.png", (250, 240, 230))
    ref_hash = phash_of_region(reference, box=(0, 0, 200, 100))
    assert not region_matches(candidate, box=(0, 0, 200, 100), expected_hash=ref_hash, max_distance=5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_verify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tvqa.verify'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tvqa/verify.py
"""Screen-state verification: perceptual-hash region matching (fast path) and
OCR text matching (fallback for dynamic text). Never returns raw image bytes
to the caller — only a hash, a distance, or extracted text.
"""
from __future__ import annotations

from pathlib import Path

import imagehash
import pytesseract
from PIL import Image

Box = tuple[int, int, int, int]  # left, top, right, bottom


def _load_region(image_path: Path, box: Box) -> Image.Image:
    img = Image.open(image_path)
    return img.crop(box)


def phash_of_region(image_path: Path, box: Box) -> str:
    region = _load_region(image_path, box)
    return str(imagehash.phash(region))


def region_matches(image_path: Path, box: Box, expected_hash: str, max_distance: int = 8) -> bool:
    region = _load_region(image_path, box)
    candidate_hash = imagehash.phash(region)
    expected = imagehash.hex_to_hash(expected_hash)
    return (candidate_hash - expected) <= max_distance


def ocr_text_of_region(image_path: Path, box: Box, lang: str = "spa+eng") -> str:
    # Default lang pair lives in _facts.yml: infra.ocr_languages
    region = _load_region(image_path, box)
    return pytesseract.image_to_string(region, lang=lang).strip()


def region_contains_text(image_path: Path, box: Box, expected_substring: str, lang: str = "spa+eng") -> bool:
    # Default lang pair lives in _facts.yml: infra.ocr_languages
    text = ocr_text_of_region(image_path, box, lang=lang)
    return expected_substring.lower() in text.lower()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_verify.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tvqa/verify.py tests/test_verify.py
git commit -m "feat: add region phash + OCR verification primitives"
```

---

## Task 5: OCR fallback wiring (real-text fixture test)

**Files:**
- Create: `tests/fixtures/make_text_fixture.py` (fixture generator, run once, output committed)
- Modify: `tests/test_verify.py`

- [ ] **Step 1: Generate a real text fixture**

```python
# tests/fixtures/make_text_fixture.py
"""Run once to (re)generate tests/fixtures/channel_unavailable.png.
Not part of the test suite itself — a fixture generator.
"""
from PIL import Image, ImageDraw

img = Image.new("RGB", (400, 120), color=(0, 0, 0))
draw = ImageDraw.Draw(img)
draw.text((20, 40), "Channel unavailable", fill=(255, 255, 255))
img.save("tests/fixtures/channel_unavailable.png")
```

Run: `python tests/fixtures/make_text_fixture.py`
Expected: creates `tests/fixtures/channel_unavailable.png`

- [ ] **Step 2: Write the failing test**

```python
# append to tests/test_verify.py
from pathlib import Path
from tvqa.verify import region_contains_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_region_contains_text_finds_expected_string():
    fixture = FIXTURES / "channel_unavailable.png"
    assert region_contains_text(fixture, box=(0, 0, 400, 120), expected_substring="unavailable")


def test_region_contains_text_false_for_missing_string():
    fixture = FIXTURES / "channel_unavailable.png"
    assert not region_contains_text(fixture, box=(0, 0, 400, 120), expected_substring="Iniciar sesión")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_verify.py -v -k contains_text`
Expected: FAIL with `FileNotFoundError` (fixture not generated yet) — run Step 1's script first,
then re-run; if `tesseract` binary is missing you'll see
`pytesseract.pytesseract.TesseractNotFoundError` — install it (`brew install tesseract` on
macOS) before continuing.

- [ ] **Step 4: Run test to verify it passes**

Run: `python tests/fixtures/make_text_fixture.py && pytest tests/test_verify.py -v -k contains_text`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/make_text_fixture.py tests/fixtures/channel_unavailable.png tests/test_verify.py
git commit -m "test: add OCR fixture + coverage for region_contains_text"
```

---

## Task 6: Declarative state registry (a11y / phash / ocr)

**Files:**
- Create: `src/tvqa/states.py`
- Test: `tests/test_states.py`

Three verification methods. `a11y` is the preferred tier (resolution-independent, cheapest);
`phash`/`ocr` take a screenshot path; `a11y` takes the snapshot **text** from
`AgentDevice.snapshot()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_states.py
from pathlib import Path
import yaml
from tvqa.states import StateRegistry, StateResult


def test_load_states_from_yaml(tmp_path):
    config = {
        "states": {
            "channel_unavailable": {
                "method": "ocr",
                "box": [0, 0, 400, 120],
                "expected_substring": "unavailable",
            },
            "home_screen": {
                "method": "phash",
                "box": [0, 380, 150, 420],
                "expected_hash": "8f8f8f8f8f8f8f8f",
                "max_distance": 8,
            },
            "login_form": {
                "method": "a11y",
                "expected_text": "Inicia sesión",
            },
        }
    }
    config_path = tmp_path / "states.yaml"
    config_path.write_text(yaml.safe_dump(config))
    registry = StateRegistry.load(config_path)
    assert set(registry.names()) == {"channel_unavailable", "home_screen", "login_form"}
    assert registry.method_of("login_form") == "a11y"


def test_check_returns_ocr_match(tmp_path):
    fixtures = Path(__file__).parent / "fixtures"
    config = {
        "states": {
            "channel_unavailable": {
                "method": "ocr",
                "box": [0, 0, 400, 120],
                "expected_substring": "unavailable",
            }
        }
    }
    config_path = tmp_path / "states.yaml"
    config_path.write_text(yaml.safe_dump(config))
    registry = StateRegistry.load(config_path)

    result = registry.check("channel_unavailable", screenshot_path=fixtures / "channel_unavailable.png")
    assert isinstance(result, StateResult)
    assert result.matched is True
    assert result.state == "channel_unavailable"


def test_check_a11y_matches_snapshot_text(tmp_path):
    config = {
        "states": {
            "login_form": {"method": "a11y", "expected_text": "Inicia sesión"},
        }
    }
    config_path = tmp_path / "states.yaml"
    config_path.write_text(yaml.safe_dump(config))
    registry = StateRegistry.load(config_path)

    snapshot = '@e1 [heading] "Bienvenido"\n@e2 [button] "Inicia sesión"\n'
    result = registry.check("login_form", snapshot_text=snapshot)
    assert result.matched is True

    result = registry.check("login_form", snapshot_text='@e1 [heading] "Home"\n')
    assert result.matched is False


def test_check_a11y_without_snapshot_raises(tmp_path):
    config_path = tmp_path / "states.yaml"
    config_path.write_text(yaml.safe_dump({"states": {"s": {"method": "a11y", "expected_text": "x"}}}))
    registry = StateRegistry.load(config_path)
    try:
        registry.check("s")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_check_unknown_state_raises(tmp_path):
    config_path = tmp_path / "states.yaml"
    config_path.write_text(yaml.safe_dump({"states": {}}))
    registry = StateRegistry.load(config_path)
    try:
        registry.check("nope", screenshot_path=Path("irrelevant.png"))
        assert False, "expected KeyError"
    except KeyError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_states.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tvqa.states'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tvqa/states.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_states.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tvqa/states.py tests/test_states.py
git commit -m "feat: add declarative state registry with a11y/phash/ocr methods"
```

---

## Task 7: Blocking log-wait

**Files:**
- Create: `src/tvqa/logwait.py`
- Test: `tests/test_logwait.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_logwait.py
import subprocess
import time
from unittest.mock import patch, MagicMock

from tvqa.logwait import wait_for_line, LogWaitTimeout


def _fake_popen_lines(lines, delay=0.01):
    proc = MagicMock()
    def _iter():
        for line in lines:
            time.sleep(delay)
            yield line
    proc.stdout = _iter()
    proc.poll.return_value = None
    proc.terminate = MagicMock()
    return proc


def test_wait_for_line_returns_matching_line():
    lines = [
        "some noise\n",
        "self-heal on network return (exhausted)\n",
        "more noise\n",
    ]
    with patch("subprocess.Popen", return_value=_fake_popen_lines(lines)):
        result = wait_for_line(pattern=r"self-heal.*exhausted", timeout_s=2, serial="emulator-5554")
    assert "self-heal" in result.line
    assert result.matched is True


def test_wait_for_line_times_out_with_no_match():
    lines = ["irrelevant\n"] * 3
    with patch("subprocess.Popen", return_value=_fake_popen_lines(lines, delay=0.01)):
        try:
            wait_for_line(pattern=r"never-appears", timeout_s=0.05, serial="emulator-5554")
            assert False, "expected LogWaitTimeout"
        except LogWaitTimeout:
            pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_logwait.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tvqa.logwait'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tvqa/logwait.py
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


def wait_for_line(pattern: str, timeout_s: float, serial: str | None = None) -> LogWaitResult:
    regex = re.compile(pattern, re.IGNORECASE)
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += ["logcat"]

    start = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        for line in proc.stdout:
            if regex.search(line):
                return LogWaitResult(matched=True, line=line.strip(), elapsed_s=time.monotonic() - start)
            if time.monotonic() - start > timeout_s:
                break
    finally:
        proc.terminate()

    raise LogWaitTimeout(f"pattern {pattern!r} not seen within {timeout_s}s")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_logwait.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tvqa/logwait.py tests/test_logwait.py
git commit -m "feat: add blocking log-wait primitive"
```

---

## Task 8: State polling (wait) + check-fn factory

**Files:**
- Create: `src/tvqa/wait.py`
- Test: `tests/test_wait.py`

The primitive that kills the "screenshot → not loaded yet → wait → another screenshot" loop:
polling happens **server-side** inside the CLI, never in the agent's context. `state_check_fn`
picks the right capture per state method (snapshot for a11y, screenshot for ocr/phash) so
callers don't branch on method.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wait.py
from pathlib import Path
import yaml
from unittest.mock import MagicMock

from tvqa.wait import poll_until, state_check_fn
from tvqa.states import StateRegistry


def test_poll_until_true_on_third_attempt():
    calls = {"n": 0}

    def check():
        calls["n"] += 1
        return calls["n"] >= 3

    assert poll_until(check, timeout_s=2, interval_s=0.01) is True
    assert calls["n"] == 3


def test_poll_until_false_on_timeout():
    assert poll_until(lambda: False, timeout_s=0.05, interval_s=0.01) is False


def test_state_check_fn_uses_snapshot_for_a11y(tmp_path):
    config_path = tmp_path / "states.yaml"
    config_path.write_text(yaml.safe_dump({
        "states": {"login": {"method": "a11y", "expected_text": "Sign In"}}
    }))
    registry = StateRegistry.load(config_path)

    device = MagicMock()
    device.snapshot.return_value = '@e2 [button] "Sign In"'
    adb = MagicMock()
    check = state_check_fn(registry, "login", adb=adb, device=device, work_dir=tmp_path)
    assert check() is True
    device.snapshot.assert_called_once()
    adb.screenshot.assert_not_called()


def test_state_check_fn_uses_screenshot_for_ocr(tmp_path):
    config_path = tmp_path / "states.yaml"
    config_path.write_text(yaml.safe_dump({
        "states": {
            "chan": {"method": "ocr", "box": [0, 0, 400, 120], "expected_substring": "unavailable"}
        }
    }))
    registry = StateRegistry.load(config_path)
    fixtures = Path(__file__).parent / "fixtures"

    adb = MagicMock()
    adb.screenshot.side_effect = lambda p: Path(p).write_bytes(
        (fixtures / "channel_unavailable.png").read_bytes()
    )
    device = MagicMock()
    check = state_check_fn(registry, "chan", adb=adb, device=device, work_dir=tmp_path)
    assert check() is True
    adb.screenshot.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_wait.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tvqa.wait'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tvqa/wait.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_wait.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tvqa/wait.py tests/test_wait.py
git commit -m "feat: add server-side state polling primitives"
```

---

## Task 9: CLI wiring

**Files:**
- Create: `src/tvqa/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
from click.testing import CliRunner
from tvqa.cli import main


def test_devices_command_invokes_adb(monkeypatch):
    from tvqa import adb as adb_module

    class FakeAdb:
        def __init__(self, serial=None):
            pass

        def devices(self):
            return ["emulator-5554"]

    monkeypatch.setattr(adb_module, "Adb", FakeAdb)
    runner = CliRunner()
    result = runner.invoke(main, ["devices"])
    assert result.exit_code == 0
    assert "emulator-5554" in result.output


def test_state_check_prints_json(monkeypatch, tmp_path):
    from tvqa import cli as cli_module

    class FakeAdb:
        def __init__(self, serial=None):
            pass

        def screenshot(self, out_path):
            out_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
            return out_path

    class FakeRegistry:
        @classmethod
        def load(cls, path):
            return cls()

        def method_of(self, name):
            return "ocr"

        def check(self, name, screenshot_path=None, snapshot_text=None):
            from tvqa.states import StateResult
            return StateResult(state=name, matched=True, detail="fake match")

    monkeypatch.setattr(cli_module, "Adb", FakeAdb)
    monkeypatch.setattr(cli_module, "StateRegistry", FakeRegistry)

    states_yaml = tmp_path / "states.yaml"
    states_yaml.write_text("states: {}\n")

    runner = CliRunner()
    result = runner.invoke(
        main, ["state", "check", "--states-file", str(states_yaml), "--state", "home_screen"]
    )
    assert result.exit_code == 0
    assert '"matched": true' in result.output


def test_state_wait_prints_json(monkeypatch, tmp_path):
    from tvqa import cli as cli_module

    class FakeRegistry:
        @classmethod
        def load(cls, path):
            return cls()

    monkeypatch.setattr(cli_module, "StateRegistry", FakeRegistry)
    monkeypatch.setattr(cli_module, "state_check_fn", lambda *a, **k: lambda: True)

    states_yaml = tmp_path / "states.yaml"
    states_yaml.write_text("states: {}\n")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["state", "wait", "--states-file", str(states_yaml), "--state", "home", "--timeout", "5"],
    )
    assert result.exit_code == 0
    assert '"matched": true' in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tvqa.cli'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tvqa/cli.py
"""tvqa CLI entry point. Every subcommand prints compact JSON or a one-line
result — never a raw image, never a log dump — so an LLM agent driving this
tool spends minimal tokens per verification step. `tvqa run` (Task 12) is the
preferred entry point for e2e; these commands are the single-step primitives.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import click

from tvqa.adb import Adb
from tvqa.device import AgentDevice
from tvqa.states import StateRegistry
from tvqa.logwait import wait_for_line, LogWaitTimeout
from tvqa.wait import poll_until, state_check_fn


@click.group()
def main():
    """Text-first QA driver for RN TV apps."""


@main.command()
def devices():
    """List attached adb devices."""
    for serial in Adb().devices():
        click.echo(serial)


@main.command()
@click.option("--serial", default=None)
@click.argument("code")
def tap(serial, code):
    """Send a single keyevent (23 or DPAD_CENTER)."""
    Adb(serial=serial).keyevent(code)
    click.echo(json.dumps({"ok": True, "keyevent": code}))


@main.command()
def snapshot():
    """Print the current accessibility snapshot. For calibrating states.yaml by
    hand — NOT for routine agent verification (use `state check` instead)."""
    click.echo(AgentDevice().snapshot())


def _check_one(registry, state_name, serial, tmp) -> "StateResult":
    method = registry.method_of(state_name)
    if method == "a11y":
        return registry.check(state_name, snapshot_text=AgentDevice().snapshot())
    shot_path = Path(tmp) / "shot.png"
    Adb(serial=serial).screenshot(shot_path)
    return registry.check(state_name, screenshot_path=shot_path)


@main.group()
def state():
    """Screen-state verification commands."""


@state.command("check")
@click.option("--states-file", required=True, type=click.Path(exists=True))
@click.option("--state", "state_name", required=True)
@click.option("--serial", default=None)
def state_check(states_file, state_name, serial):
    """Capture once and check against ONE named state. Prints JSON."""
    registry = StateRegistry.load(Path(states_file))
    with tempfile.TemporaryDirectory() as tmp:
        result = _check_one(registry, state_name, serial, tmp)
    click.echo(
        json.dumps({"state": result.state, "matched": result.matched, "detail": result.detail})
    )


@state.command("which")
@click.option("--states-file", required=True, type=click.Path(exists=True))
@click.option("--serial", default=None)
def state_which(states_file, serial):
    """Answer 'which known screen am I on?' — one snapshot + one screenshot max,
    reused across all states. Prints JSON with the list of matched state names.
    """
    registry = StateRegistry.load(Path(states_file))
    methods = {registry.method_of(n) for n in registry.names()}
    snapshot_text = AgentDevice().snapshot() if "a11y" in methods else None
    with tempfile.TemporaryDirectory() as tmp:
        shot_path = None
        if methods & {"ocr", "phash"}:
            shot_path = Path(tmp) / "shot.png"
            Adb(serial=serial).screenshot(shot_path)
        results = registry.check_all(screenshot_path=shot_path, snapshot_text=snapshot_text)
    matched = [r.state for r in results if r.matched]
    click.echo(json.dumps({"matched": matched}))


@state.command("wait")
@click.option("--states-file", required=True, type=click.Path(exists=True))
@click.option("--state", "state_name", required=True)
@click.option("--timeout", "timeout_s", default=30.0, type=float)
@click.option("--serial", default=None)
def state_wait(states_file, state_name, timeout_s, serial):
    """Block (server-side) until STATE matches; print ONE JSON line."""
    registry = StateRegistry.load(Path(states_file))
    with tempfile.TemporaryDirectory() as tmp:
        check = state_check_fn(
            registry, state_name,
            adb=Adb(serial=serial), device=AgentDevice(), work_dir=Path(tmp),
        )
        matched = poll_until(check, timeout_s=timeout_s)
    click.echo(json.dumps({"state": state_name, "matched": matched, "timeout_s": timeout_s}))


@main.command("log-wait")
@click.argument("pattern")
@click.option("--timeout", "timeout_s", default=30.0, type=float)
@click.option("--serial", default=None)
def log_wait(pattern, timeout_s, serial):
    """Block until PATTERN appears in logcat; print the matched line as JSON."""
    try:
        result = wait_for_line(pattern, timeout_s, serial=serial)
        click.echo(json.dumps({"matched": True, "line": result.line, "elapsed_s": result.elapsed_s}))
    except LogWaitTimeout:
        click.echo(json.dumps({"matched": False, "line": None, "timeout_s": timeout_s}))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tvqa/cli.py tests/test_cli.py
git commit -m "feat: wire CLI (devices, tap, snapshot, state check/which/wait, log-wait)"
```

---

## Task 10: mitmproxy lifecycle wrapper

**Files:**
- Create: `src/tvqa/proxy.py`
- Test: `tests/test_proxy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_proxy.py
from unittest.mock import patch, MagicMock
from tvqa.proxy import ProxyHarness


def test_start_launches_mitmdump_and_sets_device_proxy():
    with patch("subprocess.Popen") as popen, patch("subprocess.run") as run:
        popen.return_value = MagicMock(pid=1234)
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # → _facts.yml: infra.default_serial / proxy_host_ip / proxy_port
        harness = ProxyHarness(serial="emulator-5554", host_ip="10.0.2.2", port=8080)
        harness.start(addon_path="epic_stall_test.py", env={"EPIC_MODE": "origin403"})

        popen_cmd = popen.call_args[0][0]
        assert popen_cmd[:2] == ["mitmdump", "-s"]
        assert "epic_stall_test.py" in popen_cmd

        set_proxy_call = [c for c in run.call_args_list if "http_proxy" in " ".join(c[0][0])][0]
        assert "10.0.2.2:8080" in " ".join(set_proxy_call[0][0])


def test_stop_clears_all_three_proxy_keys_and_kills_process():
    with patch("subprocess.Popen") as popen, patch("subprocess.run") as run:
        popen.return_value = MagicMock(pid=1234)
        run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # → _facts.yml: infra.default_serial / proxy_host_ip / proxy_port
        harness = ProxyHarness(serial="emulator-5554", host_ip="10.0.2.2", port=8080)
        harness.start(addon_path="epic_stall_test.py", env={"EPIC_MODE": "origin403"})
        harness.stop()

        deleted_keys = set()
        for call in run.call_args_list:
            args = " ".join(call[0][0])
            if "settings delete global" in args:
                deleted_keys.add(args.split()[-1])
        assert deleted_keys == {"http_proxy", "global_http_proxy_host", "global_http_proxy_port"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_proxy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tvqa.proxy'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tvqa/proxy.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_proxy.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tvqa/proxy.py tests/test_proxy.py
git commit -m "feat: add mitmproxy lifecycle wrapper with 3-key cleanup"
```

---

## Task 11: Hygiene check/clean

**Files:**
- Create: `src/tvqa/hygiene.py`
- Modify: `src/tvqa/cli.py` (wire `tvqa hygiene check/clean`)
- Test: `tests/test_hygiene.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hygiene.py
from unittest.mock import patch, MagicMock
from tvqa.hygiene import check, HygieneReport


def _run_side_effect(args, **kwargs):
    joined = " ".join(args)
    if "settings get global http_proxy" in joined:
        return MagicMock(stdout="null\n", returncode=0)
    if "settings get global global_http_proxy_host" in joined:
        return MagicMock(stdout="null\n", returncode=0)
    if "settings get global global_http_proxy_port" in joined:
        return MagicMock(stdout="null\n", returncode=0)
    if "wm density" in joined:
        return MagicMock(stdout="Physical density: 320\n", returncode=0)
    if "wm size" in joined:
        # → _facts.yml: infra.default_resolution
        return MagicMock(stdout="Physical size: 1920x1080\n", returncode=0)
    return MagicMock(stdout="", returncode=0)


def test_check_reports_clean_when_no_overrides():
    with patch("subprocess.run", side_effect=_run_side_effect):
        report = check(serial="emulator-5554")  # → _facts.yml: infra.default_serial
    assert isinstance(report, HygieneReport)
    assert report.clean is True
    assert report.issues == []


def test_check_flags_proxy_left_configured():
    def side_effect(args, **kwargs):
        joined = " ".join(args)
        if "settings get global http_proxy" in joined:
            # → _facts.yml: proxy_host_ip / proxy_port
            return MagicMock(stdout="10.0.2.2:8080\n", returncode=0)
        return _run_side_effect(args, **kwargs)

    with patch("subprocess.run", side_effect=side_effect):
        report = check(serial="emulator-5554")  # → _facts.yml: infra.default_serial
    assert report.clean is False
    assert any("proxy" in issue for issue in report.issues)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hygiene.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tvqa.hygiene'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tvqa/hygiene.py
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
```

Wire it into the CLI so the module isn't dead — an agent runs `tvqa hygiene check` in
preflight and `tvqa hygiene clean` on teardown, each returning one JSON line:

```python
# append to src/tvqa/cli.py
from tvqa import hygiene as _hygiene


def _resolve_serial(serial):
    if serial:
        return serial
    found = Adb().devices()
    if not found:
        raise click.ClickException("no adb devices attached")
    return found[0]


@main.group()
def hygiene():
    """Device-state hygiene: detect/clear leftover proxy + wm overrides."""


@hygiene.command("check")
@click.option("--serial", default=None)
def hygiene_check(serial):
    """Report leftover proxy/wm overrides from a prior run. Prints JSON; exits 1 if dirty."""
    report = _hygiene.check(_resolve_serial(serial))
    click.echo(json.dumps({"clean": report.clean, "issues": report.issues}))
    if not report.clean:
        raise SystemExit(1)


@hygiene.command("clean")
@click.option("--serial", default=None)
def hygiene_clean(serial):
    """Reset proxy keys + wm size/density, then re-check. Prints JSON."""
    report = _hygiene.clean(_resolve_serial(serial))
    click.echo(json.dumps({"clean": report.clean, "issues": report.issues}))
```

Add a CLI test to `tests/test_hygiene.py`:

```python
# append to tests/test_hygiene.py
def test_cli_hygiene_check_prints_json(monkeypatch):
    from click.testing import CliRunner
    from tvqa import cli as cli_module
    from tvqa.cli import main

    monkeypatch.setattr(cli_module._hygiene, "check",
                        lambda serial: HygieneReport(clean=True, issues=[]))
    monkeypatch.setattr(cli_module, "_resolve_serial", lambda s: "emulator-5554")

    result = CliRunner().invoke(main, ["hygiene", "check", "--serial", "emulator-5554"])
    assert result.exit_code == 0
    assert '"clean": true' in result.output
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_hygiene.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tvqa/hygiene.py src/tvqa/cli.py tests/test_hygiene.py
git commit -m "feat: add generalized hygiene check/clean + tvqa hygiene CLI"
```

---

## Task 12: Flow runner (`tvqa run`)

**Files:**
- Create: `src/tvqa/runner.py`
- Modify: `src/tvqa/cli.py`
- Test: `tests/test_runner.py`

The centerpiece. One agent round trip executes an entire e2e flow locally: actions (adb
keyevents, agent-device presses), server-side waits (state, log), assertions, and proxy fault
injection — returning ONE JSON summary line. On failure, a screenshot is saved to the
project's `artifacts/` dir and the JSON carries only its **path** (token-budget rule 3).

Supported steps:

| step | effect |
|---|---|
| `open_app: NAME` | `agent-device open NAME --platform android` |
| `keyevent: CODE` | adb keyevent (numeric or `DPAD_*` name) |
| `press: "@eN"` | agent-device press on a snapshot ref |
| `sleep: N` | fixed wait (avoid; prefer `wait_state`/`wait_log`) |
| `wait_state: NAME` + `timeout` | poll until state matches (default timeout 30s) |
| `wait_log: PATTERN` + `timeout` | block until logcat line matches |
| `assert_state: NAME` | single check; fails the flow if not matched |
| `proxy_start: {addon, env}` | launch mitmdump + set device proxy |
| `proxy_stop: {}` | kill mitmdump + clear all 3 proxy keys |

- [ ] **Step 1: Write the failing test**

```python
# tests/test_runner.py
import json
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from tvqa.runner import run_flow, FlowResult


def _write_flow(tmp_path, flow):
    path = tmp_path / "flow.yaml"
    path.write_text(yaml.safe_dump(flow))
    return path


def _project(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "states.yaml").write_text(yaml.safe_dump({
        "states": {"home": {"method": "a11y", "expected_text": "Home"}}
    }))
    return proj


def test_run_flow_passes_and_returns_summary(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "login",
        "steps": [
            {"keyevent": "DPAD_CENTER"},
            {"wait_state": "home", "timeout": 5},
            {"assert_state": "home"},
        ],
    })
    with patch("tvqa.runner.Adb"), patch("tvqa.runner.AgentDevice") as dev_cls, \
         patch("tvqa.runner.ProxyHarness"):
        # state_check_fn receives ctx.device (tvqa.runner.AgentDevice) by injection now,
        # so one runner-namespace mock covers the a11y snapshot for wait_state/assert_state.
        dev_cls.return_value.snapshot.return_value = '@e1 [heading] "Home"'
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert isinstance(result, FlowResult)
    assert result.passed is True
    assert result.steps_total == 3
    assert result.failed_step is None
    assert result.evidence is None


def test_run_flow_fails_saves_evidence_path_and_stops(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "login",
        "steps": [
            {"assert_state": "home"},
            {"keyevent": "DPAD_CENTER"},  # must NOT execute after the failure
        ],
    })
    with patch("tvqa.runner.Adb") as adb_cls, patch("tvqa.runner.AgentDevice") as dev_cls, \
         patch("tvqa.runner.ProxyHarness"):
        dev_cls.return_value.snapshot.return_value = '@e1 [heading] "Login"'  # no "Home"
        adb_cls.return_value.screenshot.side_effect = lambda p: Path(p).write_bytes(b"\x89PNG")
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is False
    assert result.failed_step == 0
    assert "home" in result.detail
    assert result.evidence is not None and result.evidence.endswith(".png")
    assert Path(result.evidence).exists()
    adb_cls.return_value.keyevent.assert_not_called()


def test_run_flow_backend_error_returns_json_not_raise(tmp_path):
    # A crashing adb/agent-device call must be absorbed into a FlowResult, never
    # propagate a traceback out of run_flow (token-budget rule 2).
    flow_path = _write_flow(tmp_path, {
        "name": "boom",
        "steps": [{"keyevent": "DPAD_CENTER"}],
    })
    with patch("tvqa.runner.Adb") as adb_cls, patch("tvqa.runner.AgentDevice"), \
         patch("tvqa.runner.ProxyHarness"):
        adb_cls.return_value.keyevent.side_effect = RuntimeError("adb died")
        adb_cls.return_value.screenshot.side_effect = RuntimeError("no device")  # evidence fails too
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is False
    assert result.failed_step == 0
    assert "adb died" in result.detail
    assert result.evidence is None


def test_run_flow_proxy_steps_start_and_stop(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "fault",
        "steps": [
            {"proxy_start": {"addon": "stall.py", "env": {"EPIC_MODE": "origin403"}}},
            {"proxy_stop": {}},
        ],
    })
    with patch("tvqa.runner.Adb"), patch("tvqa.runner.AgentDevice"), \
         patch("tvqa.runner.ProxyHarness") as proxy_cls:
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is True
    proxy_cls.return_value.start.assert_called_once()
    proxy_cls.return_value.stop.assert_called_once()


def test_cli_run_prints_one_json_line(tmp_path):
    from click.testing import CliRunner
    from tvqa.cli import main

    flow_path = _write_flow(tmp_path, {"name": "f", "steps": [{"sleep": 0.01}]})
    runner = CliRunner()
    result = runner.invoke(main, ["run", str(flow_path), "--project", str(_project(tmp_path))])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload["passed"] is True
    assert payload["flow"] == "f"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tvqa.runner'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tvqa/runner.py
"""Declarative e2e flow runner. Executes flow.yaml steps locally — actions,
server-side waits, assertions, proxy fault injection — and returns ONE compact
summary. The whole point: an LLM agent spends ~60 tokens on an entire flow
instead of one round trip per step. On failure it saves a screenshot to
<project>/artifacts/ and reports only the PATH.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from tvqa.adb import Adb
from tvqa.device import AgentDevice
from tvqa.logwait import wait_for_line, LogWaitTimeout
from tvqa.proxy import ProxyHarness
from tvqa.states import StateRegistry
from tvqa.wait import poll_until, state_check_fn


class StepFailed(RuntimeError):
    pass


@dataclass
class FlowResult:
    flow: str
    passed: bool
    steps_total: int
    failed_step: int | None
    detail: str
    evidence: str | None
    duration_s: float


class _Ctx:
    def __init__(self, project_dir: Path, serial: str | None):
        self.project_dir = project_dir
        self.serial = serial
        self.registry = StateRegistry.load(project_dir / "states.yaml")
        # project.yaml is optional; when present it supplies proxy host/port and a
        # serial hint so those aren't hardcoded here.
        project_yaml = project_dir / "project.yaml"
        cfg = yaml.safe_load(project_yaml.read_text()) if project_yaml.exists() else {}
        cfg = cfg or {}
        proxy_cfg = cfg.get("proxy", {})
        self.adb = Adb(serial=serial)
        self.device = AgentDevice(platform="android")
        self.proxy = ProxyHarness(
            serial=serial or cfg.get("serial_hint", "emulator-5554"),
            host_ip=proxy_cfg.get("host_ip", "10.0.2.2"),
            port=proxy_cfg.get("port", 8080),
        )
        self.work_dir = project_dir / "artifacts"
        self.work_dir.mkdir(exist_ok=True)


def _exec_step(step: dict, ctx: _Ctx) -> None:
    if "open_app" in step:
        ctx.device.open_app(step["open_app"])
    elif "keyevent" in step:
        ctx.adb.keyevent(step["keyevent"])
    elif "press" in step:
        ctx.device.press(step["press"])
    elif "sleep" in step:
        time.sleep(float(step["sleep"]))
    elif "wait_state" in step:
        name = step["wait_state"]
        timeout = float(step.get("timeout", 30))
        check = state_check_fn(ctx.registry, name, adb=ctx.adb, device=ctx.device, work_dir=ctx.work_dir)
        if not poll_until(check, timeout_s=timeout):
            raise StepFailed(f"state {name!r} not seen within {timeout}s")
    elif "wait_log" in step:
        try:
            wait_for_line(step["wait_log"], float(step.get("timeout", 30)), serial=ctx.serial)
        except LogWaitTimeout as e:
            raise StepFailed(str(e))
    elif "assert_state" in step:
        name = step["assert_state"]
        check = state_check_fn(ctx.registry, name, adb=ctx.adb, device=ctx.device, work_dir=ctx.work_dir)
        if not check():
            raise StepFailed(f"assert_state {name!r} did not match")
    elif "proxy_start" in step:
        spec = step["proxy_start"]
        ctx.proxy.start(addon_path=spec["addon"], env=spec.get("env", {}))
    elif "proxy_stop" in step:
        ctx.proxy.stop()
    else:
        raise StepFailed(f"unknown step: {step!r}")


def run_flow(flow_path: Path, project_dir: Path, serial: str | None = None) -> FlowResult:
    flow_path, project_dir = Path(flow_path), Path(project_dir)
    flow = yaml.safe_load(flow_path.read_text())
    name = flow.get("name", flow_path.stem)
    steps = flow["steps"]
    ctx = _Ctx(project_dir, serial)

    start = time.monotonic()
    failed_step, detail, evidence = None, "ok", None
    try:
        for i, step in enumerate(steps):
            try:
                _exec_step(step, ctx)
            except StepFailed as e:
                failed_step, detail = i, str(e)
                raise
            except Exception as e:  # backend error (adb/agent-device/mitmdump)
                failed_step, detail = i, f"{type(e).__name__}: {e}"
                raise
    except Exception:
        # BOTH a StepFailed assertion AND an unexpected backend error land here, so a
        # crashing adb/agent-device/mitmdump call still returns ONE JSON line (token-budget
        # rule 2) instead of dumping a traceback into the agent's context.
        shot = ctx.work_dir / f"{name}-step{failed_step}.png"
        try:
            ctx.adb.screenshot(shot)
            evidence = str(shot)
        except Exception:
            evidence = None
    finally:
        # Never leave a dead proxy configured, even on failure (see proxy.py docstring).
        if ctx.proxy._proc is not None:
            ctx.proxy.stop()

    return FlowResult(
        flow=name,
        passed=failed_step is None,
        steps_total=len(steps),
        failed_step=failed_step,
        detail=detail,
        evidence=evidence,
        duration_s=round(time.monotonic() - start, 2),
    )
```

```python
# append to src/tvqa/cli.py
from tvqa.runner import run_flow


@main.command("run")
@click.argument("flow_file", type=click.Path(exists=True))
@click.option("--project", "project_dir", required=True, type=click.Path(exists=True))
@click.option("--serial", default=None)
def run(flow_file, project_dir, serial):
    """Execute a flow.yaml locally; print ONE JSON summary line. The preferred
    entry point for e2e — one agent round trip per flow, not per step."""
    result = run_flow(Path(flow_file), project_dir=Path(project_dir), serial=serial)
    click.echo(json.dumps({
        "flow": result.flow,
        "passed": result.passed,
        "steps": result.steps_total,
        "failed_step": result.failed_step,
        "detail": result.detail,
        "evidence": result.evidence,
        "duration_s": result.duration_s,
    }))
    if not result.passed:
        raise SystemExit(1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_runner.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/tvqa/runner.py src/tvqa/cli.py tests/test_runner.py
git commit -m "feat: add declarative flow runner (tvqa run)"
```

---

## Task 13: Dogfood config for epic-app + live a11y validation

**Files:**
- Create: `projects/epic-app/states.yaml`
- Create: `projects/epic-app/project.yaml`
- Create: `projects/epic-app/flows/login.yaml`
- Create: `projects/epic-app/flows/network_fault_recovery.yaml`

This task doubles as the **agent-device-on-Android-TV validation spike**. Decision criteria:

1. Run `tvqa snapshot` with epic-app on the login screen. If the output contains usable labels
   / testIDs for the screens we care about → those states use `method: a11y` (preferred).
2. If the snapshot is empty/noisy for a screen (video player, native modal, splash) → that
   state falls back to `method: ocr` (or `phash` for static art).
3. Note whether the snapshot exposes **which element has DPAD focus**. If yes, future flows
   can assert focus; if no, navigation stays DPAD-keyevent-based (already supported).

Either outcome is a success: the harness supports both, and the YAML records the decision.

- [ ] **Step 1: Write the project config**

```yaml
# projects/epic-app/project.yaml
# Values sourced from _facts.yml (dogfood / infra namespaces).
package: com.epictv           # → dogfood.package
app_name: EpicTV             # → dogfood.app_name
serial_hint: emulator-5554   # → infra.default_serial
expected_resolution: "1920x1080"  # → infra.default_resolution
proxy:
  host_ip: "10.0.2.2"      # → infra.proxy_host_ip
  port: 8080                 # → infra.proxy_port
  addon: epic_stall_test.py
```

```yaml
# projects/epic-app/states.yaml
# Method choice per state is decided by the live validation in this task:
#   a11y  — preferred; matches against the agent-device accessibility snapshot.
#           Resolution-independent: no re-calibration if the AVD changes density/size.
#   ocr   — fallback for screens with poor a11y trees. Boxes are
#           (left, top, right, bottom) in physical pixels at expected_resolution.
states:
  login_form:
    method: a11y                    # or ocr [630, 260, 1290, 320] if snapshot is poor
    expected_text: "Inicia sesión"

  home_screen_rail:
    method: a11y
    expected_text: "Home"

  channel_unavailable:
    method: ocr                     # likely a poor-a11y screen; validate live
    box: [700, 420, 1220, 480]
    expected_substring: "unavailable"

  network_error_modal:
    method: ocr
    box: [700, 430, 1220, 490]
    expected_substring: "Error de red"
```

```yaml
# projects/epic-app/flows/login.yaml
name: login
steps:
  - open_app: EpicTV   # → _facts.yml: dogfood.app_name
  - wait_state: login_form
    timeout: 20
  # Navigation to credentials + submit is DPAD-based unless the a11y validation
  # showed stable refs — adjust after running Task 13's live check.
  - keyevent: DPAD_CENTER
  - wait_log: "auth.*success"
    timeout: 30
  - assert_state: home_screen_rail
```

```yaml
# projects/epic-app/flows/network_fault_recovery.yaml
# The money flow: inject an origin-403 fault via mitmproxy, watch the app
# surface the error, restore the network, verify self-heal — in ONE command.
name: network_fault_recovery
steps:
  - open_app: EpicTV   # → _facts.yml: dogfood.app_name
  - wait_state: home_screen_rail
    timeout: 20
  - proxy_start:
      addon: epic_stall_test.py
      env: { EPIC_MODE: origin403 }
  - keyevent: DPAD_CENTER
  - wait_state: network_error_modal
    timeout: 30
  - proxy_stop: {}
  - wait_log: "self-heal.*exhausted"
    timeout: 60
  - assert_state: home_screen_rail
```

- [ ] **Step 2: Live validation (manual, against the running emulator)**

Run, with epic-app on the login screen:

    tvqa snapshot                                  # is "Inicia sesión" in the a11y tree?
    tvqa state check --states-file projects/epic-app/states.yaml --state login_form
    tvqa run projects/epic-app/flows/login.yaml --project projects/epic-app

Expected:
- If `tvqa snapshot` shows the login labels, `state check` returns
  `{"state": "login_form", "matched": true, ...}` via the a11y method — no screenshot, no OCR,
  ~40 tokens of output.
- `tvqa run` prints `{"flow": "login", "passed": true, "steps": 4, ...}`.
- Record the a11y-vs-ocr decision per state as a comment in states.yaml. If a screen's snapshot
  is unusable, switch that state to `ocr` and calibrate its box from ONE full screenshot read
  off in Preview/GIMP (the only intentional image read of the whole process).

- [ ] **Step 3: Commit**

```bash
git add projects/epic-app/
git commit -m "feat: add epic-app dogfood states + login and fault-recovery flows"
```

---

## Task 14: Push to GitHub

**Files:** none (repo-level operation)

- [ ] **Step 1: Create `.gitignore`**

```
# .gitignore
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
.venv/
projects/*/artifacts/
```

- [ ] **Step 2: Commit and create the GitHub repo**

```bash
git add .gitignore
git commit -m "chore: add .gitignore"
gh repo create tv-qa-harness --private --source=. --remote=origin
git push -u origin main
```

Expected: repo visible at `https://github.com/<your-username>/tv-qa-harness`.

---

## Self-Review

**1. Spec coverage.** Token economy is now the explicit design center: token-budget rules are in
the header and README; the flow runner (Task 12) collapses a flow to one round trip; `state
wait`/`which` (Task 8–9) kill the screenshot-polling loop; evidence goes to disk as paths
(Task 12). The agent-device experiment the user asked for is the interaction layer (Task 3,
Task 13's live validation), with adb retained for system ops and DPAD navigation. Verification
(Task 4–6), log-wait (Task 7), proxy lifecycle incl. the 3-key cleanup gotcha (Task 10, plus
the runner's finally-block safety net), hygiene (Task 11), dogfood config + flows (Task 13),
publishing (Task 14).

**2. Placeholder scan.** No TBD/TODO markers; every step has runnable code and an expected
result. Task 13's live validation is intentionally manual (it *is* the spike) with explicit
decision criteria, and both outcomes are handled by existing code paths.

**3. Type consistency.** `StateResult` (Task 6) is reused by `cli.py` and `wait.py`.
`Adb.screenshot(out_path) -> Path` (Task 2) and `AgentDevice.screenshot(out_path) -> Path`
(Task 3) share a shape; `state_check_fn` (Task 8) is the single factory used by both
`cli.py state wait` and `runner.py`, and it takes the `adb`/`device` wrappers by **injection**
(never building its own) so one instance — and, under test, one mock namespace — is reused per
call. `ProxyHarness.start/stop` (Task 10) is what the runner's `proxy_start`/`proxy_stop` steps
call, and the runner guarantees cleanup in `finally`.

**4. Known open risk.** agent-device's model is `press @ref`; Android TV navigation is
DPAD-focus-based. If Task 13 shows the a11y snapshot doesn't expose focus or labels are too
poor, flows stay DPAD-keyevent-based and states stay ocr/phash — no plan changes needed, the
YAML absorbs the decision. `press` steps would then go unused until a project with good a11y
appears.

## Future Work (explicitly out of scope for this plan)

- Auto-recovery for the AVD network-corruption failure mode hit during the 2026-07-30 epic-app
  session (`adb reboot` + re-`adb reverse` + relaunch when `network_error_modal` matches
  repeatedly) — as a flow step (`recover_avd`) once the manual recovery steps are proven
  reliable across more than one incident.
- Focus-assertion steps (`assert_focus: "@eN"`) if Task 13 shows the a11y snapshot exposes DPAD
  focus reliably.
- Flow authoring aids: record a manual agent-device session (its `.ad` replay scripts) and
  translate it into a `flow.yaml`; or export `flow.yaml` to strict Maestro YAML for CI.
- `tvqa` as MCP server — likely unnecessary: agents call the CLI, and agent-device already
  ships `agent-device mcp` for its own tools.
- `tvqa proxy start/stop` standalone CLI subcommands (currently exercised via flow steps).

---

## Execution

Two ways to proceed:

**1. Inline in this session** — I implement Task 1 through Task 14 in order, running each
test/commit step for real, pausing after each task for your review.

**2. Delegate per-task to `Agent` subagents** — I dispatch a general-purpose subagent per task
with the exact task text as its prompt, review its diff before moving to the next task.

Which do you want?
