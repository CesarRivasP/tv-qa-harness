# tvqa — Feedback & calibration handoff for the tool developer

**From:** the agent driving `tvqa` against **epic-app** (React Native Android TV,
`release/1.3.21`, package `com.epictv`) on `emulator-5554`.
**Date:** 2026-08-02. **Build under test:** `1.3.34.development` (dev/LogBox build).
**Install:** editable (`import tvqa` → `src/tvqa/`), so source edits are live.

Purpose: everything the LLM developing `tvqa` needs to finish fixing/calibrating it,
from the perspective of an agent that just tried to run the net-issue E2E regression
(tc255/257/268/269/270) end-to-end and could not get a single trustworthy pass.

---

## TL;DR

1. **The log oracle was silently returning false positives for every flow.** Fixed
   (commit `d87c4ad`) but please review the approach and harden it — see §1.
2. **`state check/wait` crashed on 0-node a11y frames.** Fixed (`d87c4ad`).
3. **The real blocker is navigation, not the oracle.** Flows drive the app with blind,
   fixed-sleep `keyevent` sequences. That is not reliable unattended on this build
   (variable cold-boot, conditional LogBox toasts, sparse a11y). This needs a design
   change in the runner (§4), not just per-flow tweaks.
4. **Most flow YAMLs are uncalibrated stubs** (`TODO(calibrate)` blind `DPAD_RIGHT`).
   Only the Live TV path is calibrated now (§3).

---

## 1. Oracle bug: `wait_for_line` matched stale ring-buffer lines (FIXED, please review)

**Symptom I hit:** every `wait_log` "passed" in ~0.1s regardless of whether the event
happened. tc255 "passed" in 21s even though its token403 fault can't fire before 45s.

**Root cause:** `wait_for_line` ran plain `adb logcat`, which **replays the entire ring
buffer** before tailing live. So a stale line from an earlier attempt (`playerFailed`,
`HANDLERELOADVIDEO`) or the ever-present `ReactNativeJS` memory-monitor spam matched
instantly. Oracles were meaningless.

**Failed first fix (worth knowing):** I tried `adb logcat -T "<device-time>"` where the
time came from `adb shell date "+%m-%d %H:%M:%S.000"`. **This is a no-op on this device.**
The device's toybox `date` errors with `date: Max 1 argument` because `adb shell` word-
splits the argv — `%H:%M:%S.000` arrives as a separate argument. `since` came back empty
and the code fell through to plain `logcat` again. If you ever want the `-T` approach,
quote the format for the *device* shell: `adb shell 'date +"%m-%d %H:%M:%S.000"'`.

**Applied fix (`d87c4ad`):** clear the buffer with `adb logcat -c` immediately before
tailing. This is the same primitive the manual test procedure uses. Small race (an event
between clear and `Popen`) is acceptable for these flows because faults are injected and
then awaited over seconds.

**Asks for you:**
- Consider making the clear **opt-out-able** per step (`wait_log: {pattern: ..., since: now|keep}`)
  — a few flows may legitimately want to see a line that fired slightly before the wait.
- Consider `-b all` / picking buffers explicitly; native ExoPlayer lines and `ReactNativeJS`
  are on different buffers and the default set has bitten us before.
- Return the **matched line + elapsed** in the flow JSON (not just `passed`), so an agent
  can sanity-check timing (e.g. "403 at 47s" is real; "at 2s" is suspect) without reading a PNG.
- A `wait_log` that matches should optionally assert a **minimum elapsed** (`min_s`) so a
  too-fast match is treated as suspicious/failed. This would have caught the stale-buffer bug.

## 2. `state check/wait` crashed on empty a11y snapshots (FIXED)

`state_check_fn` called `device.snapshot()`, which **raises** `AgentDeviceError` when the
a11y helper returns 0 nodes. On this build that happens constantly (cold boot, LogBox
overlay, the video player screen). `poll_until` propagated the exception and the whole
`tvqa state wait` / flow crashed with a Python traceback instead of polling.

Fixed in `d87c4ad`: a 0-node frame is caught and treated as "state not present yet" so
polling continues. **Ask:** apply the same tolerance anywhere else `device.snapshot()` is
called in a loop (I only patched `wait.py`).

## 3. Calibration state per flow (epic-app project)

| Flow | Nav calibrated? | Notes |
|---|---|---|
| `login.yaml` | ⚠️ broken on remember-me | Types user/pass into fields **prefilled by "Recordarme"** → doubles them (`cesarrivascesarrivas`) → `401 authentication_failed`. See `login_remembered.yaml` (submit prefill, no typing). |
| `login_remembered.yaml` | ✅ new | Cold-boot shows an "Aceptar" session dialog first (only after a logout); then login form with `login_button` focusable. |
| `tc255_live_403` | ✅ nav, ⚠️ cold-boot timing | Live TV path calibrated (see below); oracle moved to logcat. Reaches playback **warm**; blind cold-boot timing still misses (§4). |
| `tc257/tc268/tc269/tc270` | ❌ stubs | Still `TODO(calibrate)` blind `DPAD_RIGHT/DOWN`. VOD flows need a VOD title nav path (not yet calibrated — the movie grid is 0-node a11y). |
| `tc275_auth_*` | ❌ blocked | Needs mitmproxy addons `auth_expired_user_test.py` / `auth_refresh_revoke_test.py`, which are **ephemeral scratchpad files absent from disk**. `tvqa proxy check` reports them missing. |

**Calibrated Live TV nav (from Home):** open left drawer `DPAD_LEFT` (focus lands on
"Home") → `DPAD_DOWN ×4` (My list, Movies, Series, Live TV) → `DPAD_CENTER` (grid) →
`DPAD_DOWN` (channel 1) → `DPAD_CENTER` (play).

**State anchors:** `live_tv_grid` was anchored to `"TV en vivo"` which is **not in the
a11y tree**; changed to `"Costa Rica"` (the country selector — stable, live-only). Note
`home_screen_rail: "Top 10"` is **content-rotated** (the hero/rows change), so it is an
unreliable gate — sometimes present, sometimes not.

## 4. The core design gap: unattended navigation on a sparse-a11y dev build

This is the most important item and it is **not fixable with flow tweaks alone.**

Observed constraints on this build:
- **Cold boot is slow and variable** (~15-20s to interactive; sometimes 40s+). Fixed
  `sleep` before the first `keyevent` either wastes time or fires nav into a not-ready screen.
- **LogBox / `SerializableStateInvariantMiddleware` dev toasts** appear *conditionally*
  as full overlays that **steal focus** and cover the a11y tree. A blind `DPAD_CENTER` to
  dismiss them is destructive when no toast is present (it activates whatever is focused).
- **a11y is sparse or 0-node** on: splash/boot, the video player, home (partially), and the
  movie/VOD grids. It is **rich** on: the login form and the **Live TV grid**. So you can
  only state-gate a subset of screens.
- **`open_app` only foregrounds the last screen** — it does not reset to Home. The only
  deterministic reset I found is `adb am force-stop com.epictv` + relaunch (session
  persists → cold-boots to Home), then dismiss the dev toast.

**Concrete features that would make this driveable — requests for the tool:**

1. **State-gated navigation step.** A step that presses a key and then waits for a target
   state, retrying/re-pressing up to N times, e.g.
   ```yaml
   - nav: {key: DPAD_DOWN, until_state: live_tv_grid, max: 6, settle: 1}
   ```
   Blind `keyevent` + separate `wait_state` is too brittle; the retry+gate must be one
   primitive. Gate on the rich anchors (login form, live grid) and the nav becomes robust.

2. **A `reset_home` / cold-launch step** that force-stops, relaunches, waits for
   interactivity, and dismisses transient dev toasts — encapsulating the reset dance so
   every flow doesn't reimplement it.

3. **Conditional dismiss** that only acts if an overlay/toast is actually present
   (the a11y snapshot already flags "React Native warning/error overlay detected" — key off
   that), so it never mis-fires on real content. `agent-device react-native dismiss-overlay`
   appears to exist under the hood; expose it as a safe, idempotent step.

4. **A screenshot-free playback oracle helper.** Confirming "video is actually playing" is
   currently guesswork. A helper that checks ExoPlayer state via logcat markers (e.g.
   `RNVExoplayer` render/`STATE_READY`, or segment fetches) would let nav-reached-playback
   be asserted before fault injection — otherwise a nav miss looks identical to a real bug.

5. **Assert the proxy is actually intercepting.** After a `proxy:` step, verify
   `settings get global http_proxy` is set AND the addon is seeing traffic. My tc255 could
   not distinguish "403 never fired because playback never started" from "proxy wasn't
   actually in path." A post-`proxy` health assertion (e.g. addon logs first intercepted
   request) removes that ambiguity.

6. **On flow failure, don't skip teardown.** tc255 failed at the `wait_log` step *before*
   its `proxy_stop`, which would have left the proxy set (it happened to be cleaned, but
   make it guaranteed): run registered teardown steps in a `finally`.

## 5. Environment facts the tool should encode / not re-learn

- **JS logs DO reach logcat** via `ReactNativeJS` on this `.development` build (despite Metro
  running). So JS-level oracles (`playerFailed`, self-heal lines, `HANDLERELOADVIDEO`) are
  catchable by `wait_log`. The suite's older note ("`.development` → Metro only") does not
  hold here; verify per build but default to logcat-visible.
- **Device clock / `date` quirk:** see §1 — toybox `date` argv splitting. Don't rely on
  host-formatted device timestamps without device-shell quoting.
- **Proxy preset default:** `token403` uses `EPIC_EXPIRE_AFTER_S=45`. Any oracle timeout for
  token403 must exceed 45s + the native ExoPlayer retry window (~16s observed) ⇒ ~65s+.
- **QA creds:** `cesarrivas` / `12345` (via `TVQA_USERNAME`/`TVQA_PASSWORD`). Remember-me is
  ON, so a re-typing login flow will double them.
- **Content is live/real:** live channels and VOD reflect real backend state. A channel can
  be legitimately down at origin; a flow must not attribute an organic error to its injected
  fault (this is why the playback-reached assertion in §4.4/4.5 matters).

## 6. What this session changed (already committed to `tv-qa-harness@main`)

- `d87c4ad` — `src/tvqa/logwait.py` (buffer clear), `src/tvqa/wait.py` (0-node tolerance),
  `tests/test_logwait.py` (+regression test). Full suite 52 pass.
- `122c5a2` — `projects/epic-app/states.yaml` (`live_tv_grid` anchor), `flows/tc255_live_403.yaml`
  (calibrated nav + logcat oracle), `flows/login_remembered.yaml` (new).

## 7. What the *tool developer* session changed (v0.3.1)

- `89ec6f1` — `src/tvqa/runner.py`: `nav`, `reset`, `dismiss` steps; `wait_log` dict syntax
  with `min_s` and `clear`; `FlowResult` extended with `log_line`/`log_elapsed_s`.
- `89ec6f1` — `src/tvqa/logwait.py`: `clear_buffer` param + `min_s` guard.
- `89ec6f1` — `src/tvqa/cli.py`: `tvqa run` JSON includes `log_line`/`log_elapsed_s`.
- `89ec6f1` — `flows/tc255_live_403.yaml`: uses `reset`, `nav`, `dismiss`, `wait_log` dict.
- `89ec6f1` — `flows/login_remembered.yaml`: uses `reset` with `dismiss_toast`.
- `89ec6f1` — `AGENTS.md`: Navigation steps documentation.
- Full suite 60 pass.

**Status:** §4.1 (nav), §4.2 (reset), §4.3 (dismiss), §4.6 (wait_log min_s), §1 (clear opt-out)
are now implemented. §4.4 (playback-reached assertion), §4.5 (addon traffic verification), and
§4.6 (teardown guarantee) remain for future work.

**Still blocked:** validating any flow to a trustworthy green — VOD nav calibration
(tc257/268/269/270 are stubs) and auth addon availability (tc275) are pending.
Every pre-`d87c4ad` tvqa "green" should be considered invalid.
(The `epic-app/docs/e2e_test_suite.md` "last run ✅" entries are unaffected — those were manual
`adb` + mitmproxy runs, not tvqa flows.)

## 8. Fast repro for the tool dev

```bash
export TVQA_USERNAME=cesarrivas TVQA_PASSWORD=12345
cd tvqa-harness
tvqa hygiene check                                   # expect clean
tvqa run projects/epic-app/flows/tc255_live_403.yaml --project projects/epic-app
# Observe: nav uses state-gated retries; reset handles cold-boot + toast dismiss.
# The oracle is honest (buffer cleared) and self-validating (min_s guard).
# A pass means a real post-injection 403 was observed in logcat.
```

Related agent memory: `feedback_tvqa_harness_gotchas`. Suite of intent per test case:
`epic-app/docs/e2e_test_suite.md`.
