# AGENTS.md — tvqa

> **Token-budget rules for AI agents driving this CLI.**  
> Violating these rules burns the user's subscription in minutes. This file is
> mandatory reading before touching any device operation.

## Context

This repo contains **tvqa** — a text-first QA CLI for React Native Android TV apps.
It was built after a 5-hour Claude Pro subscription was consumed in ~5 minutes
by an agent doing `adb screencap` → `Read PNG` loops (~165K tokens). The fix is
to push all verification **out of the LLM context and into local scripts**.

## Golden Rule

**Never `Read` a PNG unless `tvqa run` returns `passed: false` AND the `detail`
field does not explain why.**

---

## Allowed commands (whitelist)

These are the **only** device-interaction commands an agent may use:

```bash
# Pre-flight
tvqa hygiene check
tvqa devices

# Execute a complete E2E flow (ONE command → ONE JSON line)
tvqa run <flow.yaml> --project <project-dir>

# Check a single state
tvqa state check --states-file <states.yaml> --state <name>

# Wait for a state (server-side polling)
tvqa state wait --states-file <states.yaml> --state <name> --timeout <s>

# Wait for a logcat line
tvqa log-wait "<regex>" --timeout <s>

# Snapshot text (calibration only — NOT for routine verification)
tvqa snapshot
```

## Forbidden commands (blacklist)

Running any of these without explicit human approval is a rule violation:

```bash
# NEVER — burns tokens on every invocation
adb exec-out screencap -p > shot.png          # ❌
adb shell input keyevent ... && screencap ...  # ❌
Read shot.png                                   # ❌ (image in context)
adb logcat                                      # ❌ (multi-line dump)
```

## Workflow for each EpicTV test session

### 1. Pre-flight (always)

```bash
tvqa hygiene check
tvqa devices
```

If `clean: false`, run `tvqa hygiene clean` first.

### 2. Run the flow

```bash
tvqa run projects/epic-app/flows/login.yaml --project projects/epic-app
```

**Output is ONE JSON line.** Example:

```json
{"flow": "login", "passed": true, "steps": 18, "failed_step": null, "detail": "ok", "evidence": null, "duration_s": 14.2}
```

**Do not ask for more output. Do not run another command to "verify". Parse the JSON.**

### 3. If `passed: false`

Read the `detail` field first. It tells you exactly what failed:

```json
{"passed": false, "failed_step": 4, "detail": "state 'login_form' not seen within 20.0s", "evidence": "projects/epic-app/artifacts/login-step4.png"}
```

- If `detail` is clear → adjust the YAML and re-run. **Do not read the PNG.**
- If `detail` is ambiguous (e.g., OCR mismatch without telling you what text was found) → read the PNG **once** via `Read <evidence>`.

### 4. If you need to debug a step

Use **text-only** commands:

```bash
# Check current state
tvqa state which --states-file projects/epic-app/states.yaml

# Check a specific state
tvqa state check --states-file projects/epic-app/states.yaml --state login_form

# Check accessibility tree (text only)
tvqa snapshot
```

All of these return text. **None return images.**

---

## Calibration protocol (human or supervised only)

Adding a new screen to `states.yaml` requires understanding the app's real UI.
This is the **only** phase where a human (or supervised agent) may inspect the
emulator visually.

1. Navigate to the screen on the emulator
2. Run `tvqa snapshot`
3. If the snapshot shows useful text → `method: a11y`
4. If the snapshot is empty/noisy → `method: ocr` or `phash`
5. For `ocr`: the human measures the bounding box in Preview/GIMP and writes
   the `[left, top, right, bottom]` coordinates into `states.yaml`
6. **Commit the calibrated YAML** so future agents never need to measure again

---

## Why agent-device snapshots can be sparse

If `tvqa snapshot` returns only 2 nodes (e.g., `@e1 [group] "Back"`), it usually
means:
- A system modal is covering the app (permission dialog, update banner)
- The app is on a video player screen with poor a11y
- The app hasn't finished loading

**Do not conclude "a11y doesn't work for this app".** Dismiss the modal
(`keyevent: DPAD_CENTER`), wait (`sleep: 2`), and retry `tvqa snapshot`.

---

## Credentials handling

The login flow uses environment variables:

```bash
export TVQA_USERNAME=your_qa_username
export TVQA_PASSWORD=your_qa_password
tvqa run projects/epic-app/flows/login.yaml --project projects/epic-app
```

Do **not** hardcode credentials in committed YAML. The committed `login.yaml` uses
`$TVQA_USERNAME` / `$TVQA_PASSWORD` and `runner.py` expands them via `os.path.expandvars()`.

---

## Proxy fault-injection steps

Network-fault E2E flows use the `proxy` step (mode presets) instead of the raw
`proxy_start` / `proxy_stop` steps. The harness resolves the mode name to an
addon path + env vars via the `project.yaml` registry.

### project.yaml addons registry

```yaml
proxy:
  # host_ip: omit it — autodetected (10.0.2.2 for an emulator serial, else
  # this machine's live LAN IP). Only set it explicitly if autodetect picks
  # the wrong interface (e.g. VPN active).
  port: 8080
  addons:
    epic_stall: "../../../epic-app/.../epic_stall_test.py"
    auth_expired: "../../../epic-app/.../auth_expired_user_test.py"
    auth_revoke: "../../../epic-app/.../auth_refresh_revoke_test.py"
```

### Preset modes (zero-config)

```yaml
# token403 — expires CDN token after 45s
- proxy: {mode: token403}

# origin403 — poisons playlist origin
- proxy: {mode: origin403, env: {EPIC_EXPIRE_AFTER_S: "30"}}

# vodswap — degrades one proxy, healthy ones survive
- proxy: {mode: vodswap, env: {EPIC_TARGET_PROXY: proxy2}}

# blackhole — full outage for 40s
- proxy: {mode: blackhole}

# auth addons (intercept api.epictv.mx)
- proxy: {mode: auth_expired}
- proxy: {mode: auth_revoke}
```

`env` overrides are merged on top of the preset defaults. `proxy_stop` still
works to tear down the proxy mid-flow. Legacy `proxy_start` continues to
function for non-epic-app projects.

---

## Navigation steps (state-gated, retry-capable)

These steps replace blind `keyevent + sleep` sequences that are brittle on
development builds with variable cold-boot timing and sparse a11y.

### `nav` — press a key until a target state appears

```yaml
- nav:
    key: DPAD_DOWN
    until_state: live_tv_grid
    max: 6          # max retries
    settle: 1       # seconds to wait after each press before checking state
```

Presses `key`, waits `settle` seconds, checks `until_state`. Repeats up to `max`
times. Fails fast if the state never appears. If `until_state` is omitted, the
step is a single unconditional keypress.

### `reset` — deterministic cold-launch

```yaml
- reset:
    app: EpicTV
    package: com.epictv       # force-stop needs the PACKAGE, not the display name
    until_state: home_screen_rail
    timeout: 30
    dismiss_toast: true      # optional: dismiss LogBox/dev overlay if present
    dismiss_key: DPAD_CENTER
```

1. `adb am force-stop <package or app>` — pass `package`; the display `app`
   name silently no-ops force-stop (no real cold boot).
2. `open_app <app>` — this one resolves by display NAME, not package.
3. Poll `until_state` up to `timeout`
4. If `dismiss_toast: true`, check snapshot for overlay indicators and dismiss

This is the preferred entry step for every flow because `open_app` alone only
foregrounds the last screen, it does not reset state.

### `dismiss_rn_overlay` — close the RN dev LogBox

```yaml
- dismiss_rn_overlay: {}
```

Closes a React Native dev warning/error (LogBox) overlay via `agent-device
react-native dismiss-overlay`. No-op-safe if none is present. More reliable
than guessing a keyevent for LogBox, which doesn't always close on
`DPAD_CENTER`. Common after a throwaway/priming play leaves a
state-update-after-unmount warning behind.

### `dismiss` — conditional overlay dismiss

```yaml
- dismiss:
    key: DPAD_CENTER
    indicators: ["overlay", "toast", "warning", "error", "logbox"]
    settle: 0.5
```

Checks the current a11y snapshot for any of the `indicators` strings (case-
insensitive). If found, presses `key` and waits `settle`. If no indicator is
found, the step is a no-op. This never mis-fires on real content.

### `wait_log` — dict syntax with min_s guard

```yaml
- wait_log:
    pattern: "playerFailed"
    timeout: 90
    min_s: 5          # fail if match arrives faster than this (catches stale-buffer phantom)
    clear: true       # default: clear logcat buffer before tailing; set false to keep prior lines
```

`min_s` treats a match that is "too fast" as suspicious (likely a stale ring-
buffer line from an earlier attempt). This catches the phantom-pass bug that
produced false greens before the buffer-clear fix.

The matched line + elapsed time are returned in the flow JSON as `log_line` and
`log_elapsed_s`, so an agent can sanity-check timing without reading a PNG.

### `assert_no_log` — no-loop oracle (inverse of wait_log)

```yaml
- assert_no_log:
    pattern: "self-heal on network return"
    window: 45
```

PASSES only if `pattern` does NOT appear in logcat within `window` seconds. A
match = failure. Use for regression steps where a line firing at all means a
bug (e.g. a self-heal loop after the breaker should have given up for good).
`timeout` is accepted as an alias for `window`.

## Device targeting (autodetect — usually needs zero config)

`serial_hint` / `proxy.host_ip` / `agent_device_name` are intentionally
**unset** in `project.yaml`. `runner.py` resolves them from whatever single
adb device is attached:

- **serial** — `resolve_serial()` (`tvqa/adb.py`) uses the sole attached
  device; `serial_hint` in `project.yaml` is only a fallback for the
  ambiguous case (0 or 2+ devices attached at once).
- **proxy host_ip** — `"10.0.2.2"` if the resolved serial starts with
  `emulator-`, else this machine's live LAN IP via `lan_ip()`. Never
  hardcode a physical device's LAN IP in `project.yaml` — it changes across
  networks/DHCP and silently breaks the next session on a different WiFi.
- **agent-device name/session** — `agent_device_name` only matters if
  `agent-device` itself has 2+ registered devices; `None` auto-picks, which
  is fine for the common single-target case. Prefer the env vars
  `TVQA_DEVICE_NAME` / `TVQA_DEVICE_SESSION` over editing `project.yaml` when
  pinning a physical target for one session.

**Do not commit a device-specific `serial_hint`/`host_ip`/`agent_device_name`
into `project.yaml`.** A prior session did this after calibrating against a
physical Chromecast, and it would have broken every emulator/CI run using the
committed defaults (fixed in v0.3.3).

## Example correct session

```bash
$ tvqa hygiene check
{"clean": true, "issues": []}

$ tvqa proxy check --project projects/epic-app
{"proxy_installed": true, "addons_found": {"epic_stall": true, ...}, "clean": true}

$ tvqa run projects/epic-app/flows/login.yaml --project projects/epic-app
{"flow": "login", "passed": true, "steps": 18, ...}

$ tvqa run projects/epic-app/flows/network_fault_recovery.yaml --project projects/epic-app
{"flow": "network_fault_recovery", "passed": true, "steps": 8, ...}

$ tvqa run projects/epic-app/flows/tc268_proxy_swap.yaml --project projects/epic-app
{"flow": "tc268_proxy_swap", "passed": true, "steps": 14, ...}
```

**Total tokens consumed by the agent: ~120 (two round trips).**  
**Total device interactions verified: two complete E2E flows.**

---

## Enforcement

If an agent violates these rules (uses `adb screencap`, reads PNGs routinely, or
dumps `adb logcat` into the context), stop the session immediately and ask the
user whether to continue with corrected instructions.
