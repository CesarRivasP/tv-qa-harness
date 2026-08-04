# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.3] - 2026-08-04

### Added

- **`resolve_serial()` / `lan_ip()`** (`tvqa/adb.py`) — autodetect the adb
  serial (sole attached device wins) and this machine's live LAN IP instead
  of hardcoding them in `project.yaml`. Switching between emulator and
  physical device needs zero file edits now; `serial_hint` is only consulted
  when 0 or 2+ devices are attached (ambiguous).
- **agent-device targeting by NAME+session** (`tvqa/device.py`, `runner.py`)
  — avoids the stale default-session binding that silently drove the wrong
  device. `TVQA_DEVICE_NAME` / `TVQA_DEVICE_SESSION` env vars let you pin a
  physical target without touching `project.yaml`.
- **`assert_no_log` step** — inverse of `wait_log`: passes only if a
  forbidden pattern never appears within the window. No-loop regression
  oracle for EpicTV #269 (self-heal must not fire repeatedly post-exhaustion).
- **`dismiss_rn_overlay` step** — closes the RN dev LogBox overlay, which
  doesn't reliably close on `DPAD_CENTER` and blocks a11y interaction.
- **17 new/recalibrated EpicTV flows** against a physical Chromecast (device
  runs 2026-08-02/03): sidebar navigation via label-press instead of blind
  D-pad counting (flaky on cold boot), `wait_log`/`assert_no_log` oracles
  replacing blind `sleep`, and a documented first-`<Video>`-mount warmup bug
  worked around with a throwaway priming play.

### Fixed

- **`reset` step force-stop** — `am force-stop` needs the app PACKAGE, not
  the display NAME; passing the name silently no-op'd (no real cold boot).
- **`project.yaml` no longer hardcodes a device-specific serial/IP** — the
  physical-device values from calibration sessions were leaking into the
  committed default, which would have broken emulator/CI runs. Replaced with
  autodetection (see Added).

## [0.3.2] - 2026-08-04

### Added

- **`Adb.wifi_enable()` / `Adb.wifi_disable()`** (`tvqa/adb.py`) — real
  connectivity-loss toggle via `svc wifi enable/disable`. Existing mitmproxy
  failure modes (`origin403`, `token403`, etc.) fail at the proxy/CDN layer
  and never trip `NetInfo.isInternetReachable` on-device, so any recovery
  path gated on that check (e.g. EpicTV's #269 self-heal-on-reconnect) was
  going unexercised by the harness. This is the only way to trigger a
  genuine offline→online edge.
  - On a physical device driven over wireless adb, `wifi_disable()` kills its
    own control channel (wifi IS the transport) — requires USB transport
    (separate "USB debugging" toggle) for physical devices. No-op concern on
    emulators, which don't use wireless adb.

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

## [0.3.1] - 2026-08-02

### Added

- **`nav` step** — state-gated navigation: presses a key and polls until target state
  appears, retrying up to `max` times with `settle` seconds between checks
- **`reset` step** — deterministic cold-launch: `force-stop` → `open_app` → poll until
  state → optionally dismiss dev toasts/LogBox overlays
- **`dismiss` step** — conditional overlay dismiss: checks a11y snapshot for indicator
  strings, only presses key if an overlay is actually present (never mis-fires)
- **`wait_log` dict syntax** — supports `pattern`, `timeout`, `min_s` (catches stale-buffer
  phantom passes), and `clear` (opt-out of `logcat -c`)
- **`FlowResult` extended** — now carries `log_line` and `log_elapsed_s` when a `wait_log`
  step matches, surfaced in `tvqa run` JSON output for agent sanity-checking
- **`logwait.py` hardened** — `clear_buffer` param (default true) + `min_s` guard; a match
  that arrives faster than the threshold is treated as suspicious and raises timeout
- **8 new tests** — `nav` pass/fail, `reset` pass/dismiss, `dismiss` present/absent,
  `wait_log` dict syntax + `min_s` catch

### Changed

- **`tc255_live_403.yaml`** — migrated from blind `keyevent + sleep` navigation to
  `reset` + `nav` + `dismiss` state-gated steps; `wait_log` now uses dict syntax with
  `min_s: 5` to catch phantom passes
- **`login_remembered.yaml`** — uses `reset` with `dismiss_toast: true` for deterministic
  cold-boot to login form
- **`AGENTS.md`** — new "Navigation steps" section documenting `nav`, `reset`, `dismiss`,
  and `wait_log` dict syntax

## [0.3.0] - 2026-07-31

### Added

- **Proxy mode presets** (`tvqa/proxy.py` `MODES`) — 6 aliases: `token403`, `blackhole`, `origin403`, `vodswap`, `auth_expired`, `auth_revoke`
- **Addon registry** (`project.yaml` `proxy.addons`) — aliases → relative paths, resolved by `resolve_mode()`
- **`proxy` step in runner** (`tvqa/runner.py`) — `proxy: {mode: vodswap, env: {...}}` with env override support
- **`proxy_assert` step** — fail-fast verification that mitmproxy is running and device proxy is set
- **`tvqa proxy check` CLI** — validates mitmproxy installation, addon paths, and device proxy state
- **`tvqa hygiene check --project`** — addon path validation alongside proxy/wm hygiene
- **13 new tests** — `resolve_mode`, `proxy` step, `proxy_assert`, `proxy check`, `hygiene --project`

### Changed

- **6 per-issue flows updated** (tc255, tc257, tc268, tc269, tc270, tc275) — replaced verbose `proxy_start` + env dicts with compact `proxy: {mode: X}` syntax
- **AGENTS.md** — new "Proxy fault-injection steps" section with preset examples and project.yaml addons registry

### Known Issues / TODO

- **VOD playback 403 on emulator** — ExoPlayer `HttpDataSource$InvalidResponseCodeException` prevents S4, S5, S9 from completing; likely proxy/CDN or development-build token issue
- **`settings_submenu` state** — needs OCR calibration (submenus open as overlays)

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

[0.3.0]: https://github.com/CesarRivasP/tv-qa-harness/releases/tag/v0.3.0
[0.2.0]: https://github.com/CesarRivasP/tv-qa-harness/releases/tag/v0.2.0
[0.1.0]: https://github.com/CesarRivasP/tv-qa-harness/releases/tag/v0.1.0
