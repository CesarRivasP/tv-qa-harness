# tv-qa-harness

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Node 22.12+](https://img.shields.io/badge/node-22.12+-green.svg)](https://nodejs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Text-first QA driver for React Native TV apps (Android TV).**  
> Verifies screen state via accessibility snapshots, perceptual-hash matching, and OCR — **without burning vision tokens on raw screenshots**.

---

## Why this exists

During live E2E sessions against Android TV emulators, agents driving via `adb screencap` → `Read PNG` loops consumed **~165K tokens in 5 minutes** — a 5-hour subscription budget gone in one session. Most of those tokens were spent re-reading screens that hadn't meaningfully changed.

**tvqa** solves this by pushing verification **out of the LLM context and into local scripts**:

- **Accessibility snapshots** (`agent-device snapshot -i`) return compact text like `@e2 [button] "Sign In"` — resolution-independent and ~40 tokens
- **Perceptual hashes** match known screen regions locally
- **OCR** reads dynamic text without sending images to the agent
- **Declarative flows** execute entirely server-side; the agent gets **one JSON line per flow**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Agent (LLM)                                                │
│  → tvqa run flow.yaml  →  ONE JSON line back               │
│  → tvqa state wait     →  ONE JSON line back               │
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   tvqa CLI         │
                    │   (click)          │
                    └─────────┬──────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────▼────┐          ┌────▼────┐          ┌────▼────┐
   │  adb    │          │ agent-  │          │ verify  │
   │  wrapper│          │ device  │          │ (local) │
   │         │          │ wrapper │          │         │
   │• shell  │          │• open   │          │• a11y   │
   │• keyevt │          │• snap   │          │• phash  │
   │• screenshot│      │• press  │          │• ocr    │
   │• logcat │          │• screenshot│        │         │
   └─────────┘          └─────────┘          └─────────┘
        │                     │                     │
   ┌────▼─────────────────────▼─────────────────────▼────┐
   │  states.yaml  ←  flow.yaml  ←  runner.py           │
   │  (declarative screen definitions + e2e journeys)     │
   └─────────────────────────────────────────────────────┘
```

### Five layers

1. **Interaction** — `agent-device` CLI (open/snapshot/press) + `adb` fallback for system ops
2. **Verification** — Three tiers: `a11y` (preferred), `phash`, `ocr` — all local
3. **Declarative** — `states.yaml` (what screens look like) + `flows/*.yaml` (e2e journeys)
4. **Runner** — `tvqa run flow.yaml` executes flows server-side, returns one JSON summary
5. **Proxy/Hygiene** — `mitmdump` lifecycle with 3-key proxy cleanup + preflight checks

---

## Requirements

- **Python** 3.11+
- **Node.js** 22.12+ (for `agent-device` CLI)
- **tesseract** (system binary for OCR fallback)
- **mitmdump** (for network fault injection flows)
- **adb** (Android SDK platform tools)

---

## Installation

### 1. Clone and install Python package

```bash
git clone <repo-url>
cd tv-qa-harness
pip install -e ".[dev]"
```

### 2. Install agent-device (Callstack)

```bash
npm install -g agent-device@latest
```

### 3. Verify system dependencies

```bash
./scripts/check_tesseract.sh        # brew install tesseract
./scripts/check_agent_device.sh     # verifies Node version + agent-device doctor
```

### 4. Verify setup

```bash
tvqa --help
pytest -v                           # 38 tests should pass
```

---

## Quickstart

### List devices

```bash
tvqa devices
# emulator-5554
```

### Check a screen state

```bash
tvqa state check \
  --states-file projects/epic-app/states.yaml \
  --state login_form
# {"state": "login_form", "matched": true, "detail": "a11y expected_text='Inicia sesión'"}
```

### Wait for a state (server-side polling)

```bash
tvqa state wait \
  --states-file projects/epic-app/states.yaml \
  --state home_screen_rail \
  --timeout 30
# {"state": "home_screen_rail", "matched": true, "timeout_s": 30.0}
```

### Block until logcat pattern matches

```bash
tvqa log-wait "self-heal.*exhausted" --timeout 60
# {"matched": true, "line": "...self-heal on network return (exhausted)...", "elapsed_s": 12.34}
```

### Run a complete E2E flow (one round trip!)

```bash
tvqa run projects/epic-app/flows/login.yaml \
  --project projects/epic-app
# {"flow": "login", "passed": true, "steps": 4, "failed_step": null, "detail": "ok", "evidence": null, "duration_s": 8.42}
```

---

## Project Configuration

A `tvqa` project is a directory with:

```
my-project/
  project.yaml          # app metadata + proxy config
  states.yaml           # screen state definitions
  flows/
    login.yaml          # e2e flow definitions
    network_fault.yaml
  artifacts/            # auto-created: failure screenshots
```

### project.yaml

```yaml
package: com.example.app
app_name: MyApp
serial_hint: emulator-5554
expected_resolution: "1920x1080"
proxy:
  host_ip: "10.0.2.2"    # emulator alias for host
  port: 8080
  addon: my_stall_test.py
```

### states.yaml

Three verification methods:

```yaml
states:
  login_form:
    method: a11y                    # preferred: resolution-independent
    expected_text: "Sign In"

  home_screen:
    method: phash                   # fast, for static layouts
    box: [0, 380, 150, 420]
    expected_hash: "8f8f8f8f8f8f8f8f"
    max_distance: 8

  error_modal:
    method: ocr                     # fallback for poor a11y trees
    box: [700, 430, 1220, 490]
    expected_substring: "Error de red"
```

### flows/*.yaml

```yaml
name: login
steps:
  - open_app: MyApp
  - wait_state: login_form
    timeout: 20
  - keyevent: DPAD_CENTER
  - wait_log: "auth.*success"
    timeout: 30
  - assert_state: home_screen
```

**Supported step types:**

| Step | Effect |
|------|--------|
| `open_app: NAME` | `agent-device open NAME --platform android` |
| `keyevent: CODE` | `adb shell input keyevent` (numeric or `DPAD_*`) |
| `press: "@eN"` | `agent-device press @eN --settle` |
| `sleep: N` | Fixed wait (avoid when possible) |
| `wait_state: NAME` + `timeout` | Poll until state matches |
| `wait_log: PATTERN` + `timeout` | Block until logcat matches |
| `assert_state: NAME` | Single check; fails flow if not matched |
| `proxy_start: {addon, env}` | Launch mitmdump + set device proxy |
| `proxy_stop: {}` | Kill mitmdump + clear all 3 proxy keys |

---

## Token-Budget Rules for Agents

When an LLM agent drives this CLI, follow these rules to minimize token consumption:

1. **Never `Read` a PNG** unless `tvqa run`/`state check` returned `passed: false` / `matched: false` AND the `detail`/`evidence` fields don't explain the failure.
2. **Prefer `tvqa run <flow>`** (one round trip per flow) over step-by-step command sequences.
3. **Evidence paths only** — screenshots on failure are saved to `artifacts/`; the JSON carries only the path.
4. **Orchestration in YAML** — flows execute server-side; the agent only sends the command and receives the result.

---

## Hygiene (Preflight / Cleanup)

Before/after test sessions:

```bash
tvqa hygiene check              # detect leftover proxy/wm overrides
tvqa hygiene clean              # reset proxy keys + wm size/density
```

The runner automatically calls `proxy.stop()` in a `finally` block — but manual hygiene is recommended for long-lived emulator sessions.

---

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

- `MAJOR.MINOR.PATCH`
- **MAJOR**: breaking CLI or API changes
- **MINOR**: new features, new step types, new verification methods
- **PATCH**: bug fixes, documentation updates

Current version: **0.1.0** (MVP — all core features implemented)

### Git tags

```bash
git tag -a v0.1.0 -m "MVP: 5-layer architecture, 14 tasks, 38 tests passing"
git push origin v0.1.0
```

---

## Running Tests

```bash
pytest -v                    # all 38 tests
pytest tests/test_runner.py -v   # specific module
pytest -k "proxy or hygiene"     # keyword filter
```

No real device required for the unit suite — everything is mocked via `unittest.mock`.

---

## Roadmap

- [ ] Live a11y validation against EpicTV (Task 13 spike)
- [ ] Auto-recovery flow step for AVD network corruption
- [ ] Focus-assertion steps (`assert_focus: "@eN"`) if a11y exposes DPAD focus
- [ ] Flow authoring: record agent-device sessions → `flow.yaml`
- [ ] Maestro YAML export for CI integration

---

## License

MIT

---

> Built to stop burning tokens on screenshots. One JSON line per flow. Local verification only. 🎯
