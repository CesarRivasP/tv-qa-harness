# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-07-31

### Added

- **17 EpicTV E2E flows** (`projects/epic-app/flows/`) — 10 smoke (S1–S10) + 7 per-issue (tc255–tc275)
- **`shell` step in runner** (`tvqa/runner.py`) — sends raw `adb shell input keyevent` batches for D-pad navigation
- **Env-var expansion in `type` steps** (`tvqa/runner.py`) — `os.path.expandvars()` supports `$TVQA_USERNAME` / `$TVQA_PASSWORD`
- **`AGENTS.md`** — strict token-budget rules: whitelist/blacklist of commands, PNG read policy, calibration protocol
- **`.env.example`** — documents required environment variables without committing secrets
- **`projects/epic-app/README.md`** — coverage matrix, calibration guide, AVD limitations

### Calibrated (device-verified on emulator-5554)

- **Sidebar navigation pattern** — `LEFT×10` → `UP×10` → `DOWN×N` reliably navigates the left vertical nav bar
- **Auto-login with `Recordarme`** — `open_app` lands directly on `profile_select` or `home_screen_rail`
- **Virtual D-pad keyboard** — search input uses focus-based letter grid; typed `"rick"` letter-by-letter
- **Language-dependent states** — profile `cesar` (EN) vs `familia` (ES); `states.yaml` calibrated for EN
- **S1, S2, S3, S6, S7, S8, S10 passing** — device-run verified, no manual adb screencap loops

### Known Issues / TODO

- **VOD playback 403 on emulator** — ExoPlayer `HttpDataSource$InvalidResponseCodeException` prevents S4, S5, S9 from completing; likely proxy/CDN or development-build token issue
- **`settings_submenu` state** — needs OCR calibration (submenus open as overlays)
- **Per-issue flows** (tc255–tc275) — require mitmproxy addons (`epic_stall_test.py`, `auth_expired_user_test.py`) not yet wired into `tvqa` project path

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

[0.2.0]: https://github.com/CesarRivasP/tv-qa-harness/releases/tag/v0.2.0
[0.1.0]: https://github.com/CesarRivasP/tv-qa-harness/releases/tag/v0.1.0
