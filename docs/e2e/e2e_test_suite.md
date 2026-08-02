# E2E Test Suite — epic-app (Android TV)

> **Canonical location: `tv-qa-harness/docs/e2e/e2e_test_suite.md`** (moved here 2026-08-02 to
> co-locate the intent/history with the `tvqa` runner). The old path
> `epic-app/docs/e2e_test_suite.md` is now a redirect stub. Paths in the prose that read as
> `epic-app`-relative (e.g. `releases/v1.3.35_test_plan.md`, `config/sentry.js`) refer to the
> **epic-app** repo; flow/harness paths (`projects/epic-app/flows/…`, `scripts/qa/…`) refer to
> **this** repo. Companion runner docs: `network_proxy_tests.md`, `navigation_ui_tests.md`.

Single source of truth for the device-driven / harness E2E test plans across all
hardening rounds on `release/1.3.21`. Consolidates what used to live scattered in
`releases/v1.3.35_test_plan.md`, `player_autoheal_on_network_return_269_plan.md` §5.1,
`sentry_fixes_implementation_plan_2026_07_21.md`, and
`version_1_3_21_issues/proxy_speed_test_status_check_plan.md`.

- **Part 1 — Regression suite:** a **general app smoke** (happy-path sweep of every major flow)
  followed by the **per-issue** checklists (harness setup + cases + PASS criteria + last-run status
  line). Run this before each release.
- **Part 2 — Run history:** the full device-run records, preserved verbatim-in-substance.

> **Not here:** the inline `### Test` blocks in `releases/v1.3.21.md` are per-round release-note
> context (device-verified negatives / rejected experiments), not standalone E2E plans — left in
> place. Unit-test coverage lives with each feature; this doc is device/harness E2E only.

---

## Tooling coverage matrix — what `tvqa` covers vs. other means

Tracks **which tool actually produced each verification**, so we never conflate "a `tvqa` flow
exists" with "verified by `tvqa`". As of 2026-08-02 the honest state is: **every green in this
suite came from adb+mitmproxy or unit tests — zero from a `tvqa` flow.** `tvqa` flows exist but
are stubs/blocked/partially-calibrated (nav on the sparse-a11y dev build is the blocker; see
`AGENT_FEEDBACK_2026-08.md`). Every pre-`d87c4ad` `tvqa` "green" is invalid (stale-buffer oracle
bug, since fixed).

**`tvqa` flow status legend:** ✅ green (trustworthy) · ⚠️ partial (calibrated but timing/AVD-
limited) · ❌ stub (blind `TODO(calibrate)` nav) · 🚫 blocked (missing addon / env).

**Verification medium** = the tool that produced the ✅ that the per-issue section reports.

| Test / issue | `tvqa` flow (`projects/epic-app/flows/`) | `tvqa` status | Verified by (medium) | Last ✅ |
|---|---|---|---|---|
| S1–S10 smoke | `s1..s10_*.yaml` | ❌ stubs (blind D-pad) | **adb** D-pad manual | per release |
| #265 font/UI scaling | `tc265_font_scaling.yaml` | ❌ not calibrated | **adb** `wm density` + `scripts/qa/tv-ui-matrix.sh` (visual diff) + **unit** | 2026-07-13 |
| #255 live 403 → onError | `tc255_live_403.yaml` | ⚠️ nav-calibrated, oracle honest; cold-boot timing misses | **adb + mitmproxy** (`token403`) + **unit** | 2026-07-13 |
| #257 CDN 502 de-noise | `tc257_cdn_502.yaml` | ❌ stub | **unit** (`sentry.test.js` 7/7); mitmproxy optional | 2026-07-13 (unit) |
| #268 proxy swap | `tc268_proxy_swap.yaml` | ❌ stub | **adb + mitmproxy** (`vodswap`) + **unit** (33/33) | 2026-07-14 |
| #269 self-heal on net return | `tc269_self_heal.yaml`, `network_fault_recovery.yaml` | ⚠️ partial (AVD can't do real NetInfo edge) | **adb + mitmproxy** (`origin403`) + **unit** (`Layout.heal` 6) | 2026-07-30 |
| #270 speed test rejects 502 | `tc270_speed_test.yaml` | ❌ stub | **adb + mitmproxy** (`vodswap`+`502`) + **unit** (35/35) | 2026-07-14 |
| #275/#276/#277 auth `expired_user` | `tc275_auth_expired.yaml` | 🚫 blocked (scratchpad addons absent from disk) | **adb + mitmproxy** (auth addons) + **unit** (70/70) | 2026-07-21 |

**Read as:** the "Verified by" column is authoritative for release sign-off today. The `tvqa`
column is the automation backlog — promote a row to ✅ only after a flow runs green with the
fixed oracle and a state-gated nav path. When that happens, update **both** this matrix and the
per-issue "Last run" line.

---

## How to run (common setup)

**Platform:** Android TV emulator (`emulator-5554`, `sdk_google_atv64_arm64`), package `com.epictv`.
Project is **Android TV** — not Apple TV. See `[[reference_regression_testing_entrypoint]]`.

**Control path — adb-first.** Argent CDP/sim tools are **unusable on this react-native-tvos build**
(`Runtime.addBinding wasn't found` → every `Runtime.enable` times out; `gesture-tap`/`describe`/
`screenshot`/`list-simulators` are iOS-simulator-only). Confirmed non-transient 2026-07-13. Drive the
device with `adb shell input keyevent` (D-pad 21/22/19/20/23/4), `adb exec-out screencap -p`, and
`adb logcat`. Re-check whether a newer Argent build restores CDP before relying on it.

**Tool-by-test matrix** (pick by test type, do not re-deliberate):

| Test type | Tool | Why |
|---|---|---|
| UI scaling / resolution / clipping | **adb** | `wm density`/`wm size` (argent can't set density) |
| Network behavior (403/502/throttle, recovery timing) | **adb + mitmproxy** | proxy via `settings put global http_proxy`; timing from logcat |
| Native/JS logs, crashes, ANR, timing | **adb** | `logcat` / `dumpsys` |
| Repeated same-flow regression | **argent flow record/replay** | when CDP works — record once, replay per release |
| Performance (re-renders, CPU, mem) | **argent profilers** + `adb dumpsys meminfo` | |

**Network harness — mitmproxy `epic_stall_test.py`** (local-only, already exists, do **not** recreate —
`docs/version_1_3_21_issues/testing/`, backup in KB `testing/`; see `[[live_403_test_harness]]`). Modes:

| Mode | Simulates | Env |
|---|---|---|
| `token403` | URL token expiry (~60min) | `EPIC_MODE=token403 EPIC_EXPIRE_AFTER_S=45` |
| `blackhole` | Full internet outage | `EPIC_MODE=blackhole EPIC_BLACKHOLE_AFTER_S=45 EPIC_BLACKHOLE_DURATION_S=40` |
| `origin403` | Channel dead at origin (fresh URLs also fail) | `EPIC_MODE=origin403 EPIC_EXPIRE_AFTER_S=30` |
| `vodswap` | ONE proxy down (502) — the only mode that produces a *positive* swap | `EPIC_MODE=vodswap EPIC_TARGET_PROXY=proxy2 EPIC_TARGET_SPEED_FAIL=502` |

Run: `mitmdump -s epic_stall_test.py -p 8080` (from the harness dir), then
`adb shell settings put global http_proxy <MAC_LAN_IP>:8080`. Debug build's baked mitmproxy CA is
trusted by the debug `network_security_config` — HTTPS decrypts, no cert install. The addon **never**
intercepts `api.epictv.mx` (except the auth-specific scratchpad addons, which do).

**JS log destination:** on `.development` builds JS logs (`HANDLERELOADVIDEO`, breadcrumbs) go to
**Metro stdout**, not logcat — logcat only carries native ExoPlayer/codec lines. On a plain relaunched
debug build they surface in logcat via `ReactNativeJS`. `LoggerUtil.addBreadcrumb` is Sentry-only (no
console); `LoggerUtil.loggerInfo` prints (dev only) — that is why the #269 heal emits **both**.

**Hygiene (one command each — do NOT run the steps by hand):**
- Open: `./scripts/qa/preflight.sh` (exit 0 = CLEAN).
- Close: `./scripts/qa/cleanup.sh` (kills mitmdump + logcat, deletes all 3 proxy keys, resets `wm`).
  Deleting only `http_proxy` leaves the proxy live → ECONNREFUSED → ErrorBoundary — always use the script.

**⚠️ AVD limitation (device-verified 2026-07-30).** This AVD **cannot produce a real NetInfo
offline→online transition.** No root (`ip link set eth0 down` → permission denied, no `su`), no WiFi
radio (`svc wifi` no-ops; transport is emulated Ethernet `eth0` via QEMU slirp), airplane-mode does not
tear down the Ethernet network agent, and a mitmproxy blackhole/403 blocks content at the proxy without
flipping `NetInfo.isConnected` (interface stays up). Consequence for #269: the positive heal path (heal
*on* transition) is unit-only on this AVD; the negative/no-loop path is device-reachable (needs no real
transition). Full device coverage would need a WiFi-transport AVD, a rooted AVD (`CAP_NET_ADMIN`), or a
physical device.

---

# Part 1 — Regression suite

## General app smoke (happy path)

No harness — plain adb D-pad navigation through the major flows. Goal: catch crashes, focus-traps
(D-pad dead / no focusable view — `[[feedback_tv_focus_host_invariant]]`), and broken/blank screens on a
release build **before** drilling into the issue-specific network cases below. Run once per release on the
emulator; keep `adb logcat` watching for `AndroidRuntime` / `FATAL` / `ReactNativeJS` errors and a stuck
`mCurrentFocus`.

| # | Flow | Steps | Watch for |
|---|---|---|---|
| S1 | Auth | Login (user/pass) → PinCode if prompted | login succeeds, no crash on submit |
| S2 | Profiles | select adult profile; then relaunch → select Kids profile | both load; Kids gating applies |
| S3 | Home | scroll carousels (Top 10, Continuar viendo, Estrenos), D-pad U/D/L/R | no focus-trap, rows render, no blank cards |
| S4 | VOD playback | open a "Continuar viendo" title → Resume → play → pause → seek (D-pad L/R on progress) → resume | plays, seek commits, position preserved; overlay hides/shows |
| S5 | VOD next-episode | series title → play → trigger next-episode control | advances without remount-to-start |
| S6 | Live TV | Live grid → open a channel → zap to another → toggle favorite | plays, zapping doesn't kill focus, favorite persists |
| S7 | Search | Search → type query (native keyboard) → open a result | results render, keyboard input works |
| S8 | Settings | Settings root → submenus | navigable, no clipping |
| S9 | Lifecycle | from a playing VOD: HOME (background) → relaunch (foreground) | resumes to Home/session, no zombie player, no crash |
| S10 | Logout | Settings/profile → logout | returns to login, session cleared |

- **PASS:** every flow completes; zero crashes/ANR; zero focus-traps (D-pad always has a focusable
  target); no blank/broken screens.
- **Note:** this is the app-wide baseline — the per-issue sections below drill into network/player/auth edge
  behavior with the harness. A general-smoke failure blocks the release regardless of the issue cases.

## #265 — `fontSize` dp → `Style.px` sweep

**Goal:** text scales proportionally on sub-1080p panels (no oversize/clipping).

- **Visual smoke** (per screen with wrapped `fontSize`, vs prior build, no clipping/overflow):
  Auth (Login, PinCode) · Profiles (list, CreateProfile UserInfo+UserLanguage, ProfileName) · Settings
  (root + MenuContainer submenus) · Content rows (Home carousels, Media/Poster cards, Avatar) · Live
  (LiveSideBar preview, Banner) · Player (PlayerTitle, PlaybackRate) · Transient (Toast, NetworkError,
  LayoutMessages, native Keyboard).
- **Automated:** `scripts/qa/tv-ui-matrix.sh` — 720p + 1080p profiles, screenshot diff. font-scale axis
  stable (fs1.0 == fs1.3 by native clamp); only resolution axis matters.
- **Specific check (carry forward):** Home → "Top 10" carousel, numbers 1–10 fully visible / not clipped
  by the card top edge, in at least one sub-1080p resolution (the `topTenTitle` raw-dp offset regression).
- **PASS:** no new clipping, text scales with panel height.
- **Last run:** 2026-07-13 ✅ (720p-equiv `wm density 320` + 1080p `wm density 160`; found+fixed the Top 10
  badge raw-dp offset, commit `22c1a5f`).

## #255 — live 403/segment failure surfaces to `onError` fast

**Goal:** live 403/segment failure recovers ~5s worst case (was ~15–30s). Root fix: live
`minLoadRetryCount` 5→2 + live stale-check 15s→5s.

- **Harness (`token403`, mid-playback expiry at 45s):** start live → confirm playback → inject 403 on
  playlist/segment for `proxyN.cuca200.net` → measure recovery → clear/expire poison → confirm resume
  with fresh token.
- **Regression:** VOD unaffected (stale-check stays 15s, `minLoadRetryCount` stays 5). `deriveStallCause`
  `network` vs `token` tag still correct vs `TOKEN_TTL_HINT_MS` (50min). `STALE_REFRESH_AFTER_RETRIES` (2)
  doesn't escalate refresh prematurely on a transient blip.
- **PASS:** onError reaches JS reliably; persistently-poisoned token ends in clean `isExhausted`
  ("Channel unavailable"), not infinite spinner.
- **Last run:** 2026-07-13 ✅ — first internal 403 → `playerFailed` **16.26s** (ExoPlayer native retry
  window, not JS-tunable); `playerFailed` → JS `handleReloadVideo(bad_http_status)` **0.27s** (this is the
  #255 fix; native onError wins the race, 5s stale-check never had to fire).

## #257 — CDN 502 de-noise (`REACT-NATIVE-1YT`)

**Goal:** `beforeSend` drops only `SentryHttpClientException` + status 502 + host `proxy[123].cuca200.net`.

- **mitmproxy (manual, optional):** 502 from `proxyN.cuca200.net` → does NOT reach Sentry; 502 from a
  different host (API) → DOES reach; non-502 (500) from proxy host → DOES reach (status guard).
- **PASS:** proxy-host 502 silenced, everything else preserved.
- **Last run:** unit only (2026-07-13) — `isCdnMediaHttpNoise` in `config/sentry.js`,
  `__tests__/config/sentry.test.js` 7/7. Re-run `yarn jest __tests__/config/sentry.test.js` before any
  release touching the filter's hosts/status.

## #268 — mid-playback proxy swap yanks stream (black flash + rewind)

**Goal:** decoupled trigger (excessive buffering ≥8s / VOD `onError`) from application (controlled
remount via `RELOAD_REASON.PROXY` + `PROXY_GENERATION_KEY` bump). `useGetVideoData` no longer subscribes
reactively to `BEST_PROXY_KEY`. Harness for the positive swap: **`vodswap`** mode (only mode that yields a
winner — blackhole/origin403 kill *all* streaming so the speed test also fails → `changed:false`).

| TC | Scenario | PASS |
|---|---|---|
| TC1 | Background proxy write during active playback | no black frame / no remount / `PROXY_GENERATION_KEY` unchanged (structurally true after reactive-subscription removal — unit/static) |
| TC2 | Excessive buffering ≥8s continuous | timer fires once → `attemptProxySwap` → if winner, `bumpProxyGeneration` + `handleReloadVideo(PROXY)` → **spinner not black-flash** → resume same position; generation +1 |
| TC3 | Transient blip <8s | timer cleared on `isBuffering:false`; no speed test, no bump, no remount |
| TC4 | VOD stream error | `onError` → `attemptProxySwap` first; `changed:true` → swap+remount, STALE path skipped; `changed:false` → falls through to STALE |
| TC5 | Live excluded | `handleExcessiveBuffering` short-circuits on `CONTENT_TYPE.LIVE`; `onError` skips swap → BAD_HTTP/STALE |
| TC6 | Buffering cooldown shared | second ≥8s stall within 10min → `runProxySpeedTestOnBuffering` short-circuits (`{winner:null, changed:false}`) |
| TC7 | Breaker exhausts if new proxy also bad | `retryCountRef` climbs per PROXY remount; at `MAX_RETRIES` (8) → clean error state, not infinite loop |
| TC8 | Position preserved across swap | resume within ~1–2s of noted position, no rewind to start (the original bug symptom) |

- **PASS (headline):** the original symptom (black flash + rewind to `00:00`) never reproduces, even under
  total stall; a positive swap preserves position with a spinner.
- **Last run:** 2026-07-14 ✅ — **TC8 / no-black-flash CONFIRMED** (blackhole froze on last decoded frame at
  `03:10`, scrubber intact, no jump to 0) and **TC2/TC4 positive swap CONFIRMED end-to-end** via `vodswap`
  (`502 en proxy2` ×5 → swap → winner `proxy3` `changed:true` → 96 proxy3 segments, 0×502 → recovered,
  advanced to `07:14`). TC1 unit/static; TC2–TC8 internal assertions covered by
  `__tests__/utils/proxySpeedTest.test.ts` 33/33. Full detail in Part 2 → Run 2026-07-13 / 2026-07-14.

## #270 — speed test rejects fast-erroring proxies

**Goal:** `measureDownloadSpeed` must score a fast-erroring (up-but-502) proxy **0**, not high. Fix:
`if (!response.ok) return 0;` after `fetch` (status gate only — RN has **no** streaming body, so the
byte-gate draft was wrong; see `[[feedback_rn_fetch_no_streaming_body]]`, `[[project_proxy_speed_test_status_gate_270]]`).

- **Harness (`vodswap` + `EPIC_TARGET_SPEED_FAIL=502`):** degrade best_proxy (manifest 502 + `5MB.png`
  synthetic 502); healthy proxies serve synthetic 200 (2 MB). Confirm the fix scores the 502 target 0 and
  a healthy proxy wins.
- **PASS:** `changed:true` with a healthy winner; `206 Partial Content` (Range) must NOT be rejected
  (`response.ok` covers 200–299).
- **Last run:** 2026-07-14 ✅ — byte-gate draft → all-zero → no swap → "Canal no disponible" (exposed the
  RN `response.body === null` bug); status-gate fix → winner `proxy2` `changed:true` → sustained proxy2
  manifest ~4min, 0×502 → video kept rendering. `EPIC_TARGET_SPEED_FAIL=502` is the reusable regression
  asset (`kill` = total transport outage). Unit `__tests__/utils/proxySpeedTest.test.ts` + `proxyResolver`
  35/35.

## #269 — auto-heal on network return (VOD/live)

**Goal:** when connectivity returns after a sustained outage, force **exactly one** remount instead of the
player staying wedged on the last decoded frame. Two terminal states qualify: exhausted `'stream'`
(`handleRecoverFromExhausted` — reset breaker + remount) and VOD buffering-`isStalled` (plain STALE remount,
counted by the breaker). `decoder` exhaustion is excluded (device-side codec, reconnect can't fix). Live
stall stays with the existing stale-check. Trigger = **offline→online edge** on `NetInfoUtil` +
AppState-resume fallback, one-shot via `healFiredRef`.

**Observability (oracle):** the heal emits distinct grep-able lines —
`self-heal on network return (exhausted)` and `self-heal on network return (stalled)` (breadcrumb + `loggerInfo`).

**Preconditions:** `preflight.sh` clean; build with the heal breadcrumbs; `adb logcat -c` then
`adb logcat | rg -i "self-heal|reload|exhausted|proxy swap"`.

| Flow | Scenario | PASS |
|---|---|---|
| E2E-1 | **VOD blackhole (primary)** — VOD → play → blackhole ~75s (drain buffer) → confirm frozen → restore | logcat `self-heal … (stalled)` ≤1 NetInfo cycle AND progress advances, no user input |
| E2E-2 | **Live exhausted → return** — live → play → blackhole/origin403 until `PlayerError` → restore | logcat `self-heal … (exhausted)` + exits `PlayerError` and resumes |
| E2E-3 | **Decoder terminal (negative)** — force decoder failure → `PlayerError(decoder)` → toggle net | NO self-heal log; stays `PlayerError` (verifies `exhaustedReason==='stream'` gate) |
| E2E-4 | **Flapping (negative loop)** — stalled/exhausted, cycle net off/on 3–4× | exactly 1 self-heal line (one-shot `healFiredRef`); no spinner loop |
| E2E-5 | **AppState path** — VOD stalled → background (`KEYCODE_HOME`) → restore net in bg → foreground | single recovery remount on resume |
| E2E-6 | **No-regression happy path** — normal VOD+live, micro-stalls <8s (short blackhole, restore before threshold) | zero self-heal lines, zero spurious remounts (`isStalled` never set) |

- **Regression pair:** argent flows for E2E-1/E2E-2 saved as the minimum re-run set (when CDP works).
  **Maestro:** pilot is IN DEVELOPMENT / unreliable (`[[maestro_e2e_exploration]]`) — do not block on it;
  reliable path today is adb + mitmproxy + logcat.
- **⚠️ On this AVD** (per the limitation above): E2E-1 / E2E-5 and the *positive* transition paths cannot be
  produced (no real NetInfo edge); covered by unit only (`__tests__/screens/VideoPlayer/Layout.heal.test.js`).
  E2E-2's **negative/no-loop** assertion IS device-reachable and is the one that caught the real bug.
- **Last run:** 2026-07-30 ✅ — E2E-2 via `origin403` surfaced an **infinite reconnect loop** (heal fired on
  NetInfo's immediate current-state callback, resetting the breaker every ~35s). **Found + fixed** (edge
  guard) + device-verified: post-fix the player exhausts and **stays** on "Channel unavailable", no loop.
  See `[[project_player_269_selfheal_bug_found_and_fixed]]`,
  `[[feedback_netinfo_addeventlistener_fires_immediately]]`. Full detail in Part 2 → Run 2026-07-30.

## #275 / #276 / #277 — auth `403 expired_user` (Sentry de-noise + revoke-modal copy)

**Goal:** `403 error_code:expired_user` = expired subscription (business state), distinct from the
deliberate `401` revoke. Fix: `expectedErrorCodes` degradation in `loggerError` (Cambio A/B) + revoke-path
`error_code` priority in `config/axios.js` (Cambio C). Canonical Sentry group after merge:
**`REACT-NATIVE-1XD`**. Runner: `adb` + a **puntual** mitmproxy addon (scratchpad
`auth_expired_user_test.py` / `auth_refresh_revoke_test.py`) — these **do** intercept `api.epictv.mx`;
proxy via `10.0.2.2:8080`.

| TC | Scenario | PASS |
|---|---|---|
| TC1 | Login `403 expired_user` on `/token/` (#275, B) | expired-subscription modal shows AND no new Sentry event for `postLoginAuth` (only `category:'api'` breadcrumb) |
| TC2 | Refresh `403 expired_user` on `/token/refresh/` (resource `401 invalid_token` triggers reactive refresh) (#277, C) | revoke modal shows `EXPIRED_USER_MESSAGE` ("Tu cuenta ha expirado…"), NOT `SESSION_EXPIRED_MESSAGE` |
| TC3 | Undeclared 403 (e.g. `device_login_detected`) or no `error_code` | still reaches `captureException` (unit-covered, not re-run on device) |

- **PASS:** noise gone for `expired_user`, trace preserved as breadcrumb; revoke modal prioritizes the
  refresh's `error_code`.
- **Last run:** 2026-07-21 ✅ — A/B decisive with Sentry-envelope capture (CONTROL sends event, WITH-FIX 0
  events → breadcrumb); Cambio C A/B decisive (CONTROL shows session-expired copy, WITH-FIX shows
  account-expired). Unit `logger.test.js` + `axios.test.js` 70/70; full suite 499 pass / 1 skip. Detail in
  Part 2 → Run 2026-07-21.

---

# Part 2 — Run history (device)

Full records, most recent first. These are the "resultado real" logs the suite entries summarize.

## Run 2026-07-30 — #269 self-heal (loop bug found + fixed)

Android TV emulator `emulator-5554`. Goal: run #269 E2E on device.

- **Argent** did not attach to the Android emulator (v0.5.3 lists iOS sims only) → fell back to adb
  (`input keyevent` + `screencap` + `logcat`) per the standing rule.
- **E2E-1 (VOD blackhole) not reproducible on this AVD:** a 90s mitm blackhole
  (`MAIN_PLAYER_BUFFER_CONFIG.maxBufferMs=30000`) did not drain into the 8s excessive-buffering timer —
  ExoPlayer/local caching absorbed the outage, `isStalled` never set. Not a false negative, just never
  exercised. Moot given the NetInfo-transition blocker below.
- **E2E-2 (live `origin403`) → BUG FOUND.** Live channel "Acceso Total 24/7" → play → mitm `origin403`
  poisons the playlist. Breaker climbed `retryCount` 1→4 (`bad_http_status`) → exhausted → **then the heal
  fired and reset the breaker**, and repeated: logcat showed `SELF-HEAL ON NETWORK RETURN (EXHAUSTED)`
  every ~35s, **3 cycles and counting**, with the device never actually offline. Root cause:
  `NetInfoUtil.addEventListener` invokes its callback **immediately with the current state on subscribe**,
  not just on transitions — so the heal fired on that first "online" snapshot, defeating the fail-fast
  circuit breaker → infinite reconnect loop.
- **Fix:** explicit offline→online **edge guard** (`sawOffline` flag) in `Layout.js`'s heal effect — only
  heal when a real offline callback was observed first; the initial snapshot never fires the action.
  Added `LoggerUtil.loggerInfo` alongside the Sentry-only breadcrumb so the heal is grep-able in logcat.
- **Re-verified post-fix (same `origin403` repro, clean relaunched build):** breaker climbed
  `retryCount` 1→4 → exhausted → **"Channel unavailable", stays there**, no self-heal line, no loop,
  confirmed clean over 90s+.
- **Coverage:** `__tests__/screens/VideoPlayer/Layout.heal.test.js` (6 cases) encodes this exact failure —
  the "does NOT heal on the listener's initial current-state callback" case fails without the fix. Full
  VideoPlayer suite 79/79; lint clean (only pre-existing `progressTimeValue` baseline errors).
- **AVD limitation documented** (see How-to-run): no root / no WiFi radio / airplane-mode doesn't drop
  Ethernet / mitm doesn't flip `NetInfo.isConnected` → a genuine NetInfo transition can't be produced here.
  Positive path unit-only; negative/no-loop path device-verified (this run).
- **Cleanup:** `cleanup.sh` — no mitmdump, proxy keys cleared.
- Memory: `[[project_player_269_selfheal_bug_found_and_fixed]]`,
  `[[feedback_netinfo_addeventlistener_fires_immediately]]`.

## Run 2026-07-21 — #275/#276/#277 auth `expired_user` (A/B/C decisive)

Emulator `emulator-5554`, debug 1.3.35 + live Metro JS with Cambio A/B/C. Puntual mitmproxy addons
(`auth_expired_user_test.py`, `auth_refresh_revoke_test.py`) that intercept `api.epictv.mx`; baked debug
CA trusted.

**TC1 login (22E) — A/B with Sentry envelope capture** (dumping decompressed envelopes to `ingest.sentry.io`):

| Run | 403 expired_user on `/token/` | Envelope to Sentry |
|---|---|---|
| **CONTROL** (fix reverted) | yes | `"type":"event"` with `"postLoginAuth: {…}"` → **captureException SENT** |
| **WITH FIX** | yes | **0 events** → degraded to **breadcrumb** |

Bonus: the real QA account is **expired in backend** — a genuine login returned `403 expired_user` and
showed the correct modal, confirming the `errorMessage.data.error_code` read-path on device.

**TC2 revoke modal (22H / Cambio C) — A/B** (synthetic login with future-exp JWT; `403 expired_user` on
refresh; a real `getUserDetail 401 invalid_token` triggers the reactive refresh):

| Run | resource 401 | refresh 403 | Revoke modal |
|---|---|---|---|
| **CONTROL** (Cambio C reverted, `git stash`) | `invalid_token` | `expired_user` | ❌ "Tu **sesión** ha expirado…" (`SESSION_EXPIRED_MESSAGE`) |
| **WITH FIX** | `invalid_token` | `expired_user` | ✅ "Tu **cuenta** ha expirado…" (`EXPIRED_USER_MESSAGE`) |

Logcat confirmed the chain: `postRefreshToken`/`postRefreshTokenQuery` → `403 expired_user` (degraded to
breadcrumb by B) + `getUserDetail` → `401 invalid_token`. Mapping in `hooks/useSessionHandler.js`
(`getErrorMessageByErrorCode`).

**Post-merge Sentry (2026-07-22):** `22E`+`22H`+`1WT` merged into primary **`REACT-NATIVE-1XD`** (culprit
`LoggerUtil#loggerError`, old pre-refactor `captureException`; only release 1.3.21). `1XD` is the canonical
ID. Do **not** resolve until the fix ships from `release/1.3.21`; mark `resolvedInNextRelease` on ship;
count decays with adoption (`[[project_1_3_21_fixes_landed_in_1_3_27]]`).

**Unit:** `logger.test.js` + `axios.test.js` 70/70 (declared `expired_user`→breadcrumb,
undeclared→captureException, no-`error_code`→captureException; refresh `error_code` wins over the 401).
Full suite 499 pass / 1 skip. **Cleanup:** `cleanup.sh`, addons ephemeral in scratchpad, live harness
untouched. Session left the QA account logged out (expected effect of the refresh 403). Memory:
`[[auth_session_revocation_model]]`.

## Run 2026-07-14 — #270 speed-test status gate (`vodswap` + `EPIC_TARGET_SPEED_FAIL=502`)

Emulator `sdk_google_atv64_arm64`. Harness `vodswap` gained `EPIC_TARGET_SPEED_FAIL` (`kill` legacy | `502`
new); healthy synthetic-200 body bumped 4 KB → 2 MB. `api.epictv.mx` in mitm `--ignore-hosts` (raw tunnel,
honors "never intercept api"; also fixed a token-refresh 401 that intercepting the API had caused). JS logs
from **Metro stdout**.

- **Metro gotcha:** the pre-existing Metro served a **frozen transform cache** (byte-identical bundle across
  edits; `touch` + `watchman watch-del-all` did not invalidate). Had to bounce Metro with `--reset-cache`;
  confirmed the fix in the served bundle by grepping a unique marker before each device run.
- **First attempt (byte-gate draft):** best_proxy `proxy3` degraded → speed test ran (proxy3=502,
  healthy=200 2 MB) → **no swap**; JS showed only `reason:"stale"` reloads, `retryCount` 1→8 → **"Canal no
  disponible"** (`isExhausted`). Root cause = RN `response.body === null` — this reproduced the #270 bug's
  downstream effect on-device.
- **Second attempt (status-gate-only fix):** best_proxy `proxy3` degraded → `attemptProxySwap` speed test:
  `502 sintetico proxy3` (scored 0), `200 sintetico sano` proxy1/2/4 → **winner `proxy2`, `changed:true`**
  → generation bumped → URL re-resolved to `cdn.cuca200.net/proxy2/…` → **sustained proxy2 manifest ~4min,
  0×502** → **playback recovered and kept rendering video** (screencap of a live content frame). ✅
- **Unit:** `proxySpeedTest.test.ts` + `proxyResolver.test.ts` 35/35 (5xx-never-wins + healthy-2xx-wins;
  truncated-body dropped as un-testable in RN). **Cleanup:** kill mitmdump, delete proxy key; Metro left
  running (bounced with `--reset-cache`).

## Run 2026-07-14 — #268 field QA (positive swap proven via `vodswap`)

Emulator `sdk_google_atv64_arm64`, controlled entirely via `adb` (Argent CDP still unusable per 2026-07-13).
Logged in, played VOD "Obsession". Network via mitmproxy harness.

- **Setup confirmed:** VOD is proxied (`proxy2.cuca200.net/p1/manifest/obsession2026.json/segment-*.ts <<
  200`; `p1` VOD target resolved from `/auto/`, `best_proxy=proxy2`) → #268 swap logic applies. Debug
  build's embedded mitmproxy CA works (HTTPS decrypted). JS logs → **Metro**, not logcat, on `.development`.
- **TC8 / no-black-flash — CONFIRMED.** Blackhole mid-VOD: baseline `02:58` → advanced to `03:10` → **froze
  on buffer exhaustion holding the last decoded frame**. No black screen, no jump to `00:00`; scrubber read
  `03:10`/`01:49:23` intact. **Directly refutes the original #268 symptom** (black flash + rewind to start).
- **TC1 (no yank on background write) — static/unit only.** The reactive-subscription removal
  (`useMMKVString(BEST_PROXY_KEY)` → `useMMKVNumber(PROXY_GENERATION_KEY)`) makes this structurally true;
  not reachable as a live repro (see 2026-07-13 teardown note).
- **TC2/TC4 positive swap (`changed:true`) — CONFIRMED end-to-end via `vodswap`.** blackhole/origin403 can't
  produce it (kill *all* streaming → speed test also fails → `changed:false` → correct fall-through to STALE).
  Built `EPIC_MODE=vodswap EPIC_TARGET_PROXY=proxy2` (degrades only the active proxy). Two subtleties: the
  active proxy's `5MB.png` is `flow.kill()`-ed (not 502'd) so `measureDownloadSpeed` throws → 0 (a 502 would
  score *high* since fetch doesn't throw on HTTP error and computes size/elapsed regardless — ⚠️ this is the
  latent quirk #270 fixed); healthy proxies get a synthetic fast 200. Observed: VOD "Obsession" resumed at
  `03:10`, `502 en proxy2` ×5 → onError → `attemptProxySwap('stream error')` → speed test (`KILL proxy2`=0;
  `200 sintetico` ×3 valid) → **winner `proxy3` (`changed:true`)** → `bumpProxyGeneration` → URL re-resolved
  → **96 proxy3 segments, 0×502** → **recovered, advanced to `07:14`, position preserved, no black flash.**
- **Clean recovery — CONFIRMED.** `force-stop` + relaunch → Home loads, session persists, stream healthy.
- **→ #269 filed here.** A *severe multi-transition* outage (kill proxy → gap → 75s blackhole → remove
  proxy) wedged the player at `03:10` with no auto-recover on full network return — pre-existing breaker
  exhaustion, tracked as #269 (see Run 2026-07-30). **Cleanup:** killed mitmdump/logcat, proxy `null`.

## Run 2026-07-13 — #268 CDP/teardown findings

Emulator `sdk_google_atv64_arm64`. The run that established the adb-first constraint.

- **CDP/`debugger-*` unavailable on this build — not a config issue, do not re-attempt without an upstream
  fix.** `~/.argent/tool-server.log`: `Runtime.addBinding wasn't found` then every `Runtime.enable` on the
  same `device_id` times out — this Hermes/react-native-tvos build lacks a CDP method Argent depends on.
  Confirmed after `restart-app` and full Metro restart. Blocks `debugger-connect/-status/-evaluate/
  -component-tree` (no internal-state assertions). `gesture-tap`/`describe`/`screenshot`/`list-simulators`/
  `button` are iOS-sim-only. Fell back to `adb input keyevent` + `screencap` + `logcat`.
- **Proxy residue from the #255 harness was still poisoning the emulator** (global `http_proxy` → dead
  mitmproxy) → `Network Error` on everything until cleared. **Any future run should check/clear proxy first.**
- **TC1 not reachable via plain HOME backgrounding** — the player unmounts fully by design before resume
  fires: `HOME` → `[USEMEMORYMANAGER] … clearing memory caches` → `ExoPlayerImpl: Release` → lands on the
  Episodes list. `KEYCODE_APP_SWITCH` produced no lifecycle log on this AVD skin. Working theory for the
  real trigger: a brief `active→inactive→active` blip that does *not* reach `background` (screensaver /
  dialog occlusion), so async `runProxySpeedTest` completes against a still-mounted player. Not confirmed;
  needs `inactive`-without-`background` or CDP.
- **Confirmed instead:** VOD (Rick and Morty S9E6) plays/pauses/resumes at a sane position across a real
  mount/unmount/remount, no crash. TC2–TC8 not executed (need CDP or a network-degradation harness — the
  latter arrived 2026-07-14). Internal-logic assertions covered by unit (`proxySpeedTest.test.ts` 33/33).

---

## Deferred / not yet in a build
- **#257-B** real proxy failover on live 502/5xx (`runProxySpeedTest` on `onError`) — rides on #255-A;
  validate real `REACT-NATIVE-1YT` event shape in Sentry first.
