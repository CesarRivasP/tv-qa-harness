# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-31

### Added

- **Project scaffold** — `pyproject.toml`, package structure, pytest setup
- **ADB wrapper** (`tvqa/adb.py`) — shell, keyevent, screenshot, devices, logcat
- **Agent-device wrapper** (`tvqa/device.py`) — open, snapshot -i, press, screenshot
- **Verification layer** (`tvqa/verify.py`) — perceptual-hash region matching + OCR with tesseract
- **OCR fixture** — generated test image with text for `region_contains_text` validation
- **State registry** (`tvqa/states.py`) — declarative YAML config with three methods: a11y, phash, ocr
- **Blocking log-wait** (`tvqa/logwait.py`) — `adb logcat` tail with regex, returns first match or timeout
- **State polling** (`tvqa/wait.py`) — server-side `poll_until` + `state_check_fn` factory
- **CLI entry point** (`tvqa/cli.py`) — `devices`, `tap`, `snapshot`, `state check/which/wait`, `log-wait`, `hygiene check/clean`
- **mitmproxy lifecycle** (`tvqa/proxy.py`) — start/stop with 3-key proxy cleanup (http_proxy, global_http_proxy_host, global_http_proxy_port)
- **Hygiene checks** (`tvqa/hygiene.py`) — detect/clear leftover proxy settings and wm size/density overrides
- **Flow runner** (`tvqa/runner.py`) — `tvqa run flow.yaml` executes complete e2e flows server-side, returns one JSON summary
- **EpicTV dogfood config** — `project.yaml`, `states.yaml`, `flows/login.yaml`, `flows/network_fault_recovery.yaml`
- **Token-budget rules** — documented in README and architecture; images never enter LLM context by default
- **Facts registry** (`docs/plans/_facts.yml`) — shared constants for mechanical synchronization
- **38 passing tests** — full unit test coverage via `unittest.mock`

### Design Decisions

- **CLI over MCP** — avoids ~1.5-3K tokens of permanent schema context per turn
- **agent-device over raw adb** — for interaction layer (accessibility snapshots are token-cheap)
- **5-layer architecture** — interaction, verification, declarative, runner, proxy/hygiene
- **Evidence to disk** — failure screenshots saved to `artifacts/`; JSON carries only path

[0.1.0]: https://github.com/<user>/tv-qa-harness/releases/tag/v0.1.0
