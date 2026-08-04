# E2E — Network / Proxy tests (epic-app Android TV)

Everything I drive through the **mitmproxy fault-injection harness**: CDN/token failures,
proxy swap, speed test, and self-heal. These are the cases where the *network* is the
system under test — I degrade traffic on the wire and assert the app's recovery behavior
from logs + player state.

- **App:** `com.epictv`, `release/1.3.21`, build `1.3.34.development`, `emulator-5554`.
- **Companion doc:** UI/navigation/auth cases live in `navigation_ui_tests.md`.
- **Source of intent + run history + tooling coverage matrix:** `./e2e_test_suite.md` (§#255/#257/#268/#269/#270).
- **tvqa flows:** `projects/epic-app/flows/`.

---

## Harness setup (common to every case here)

**Control path:** `adb` D-pad + `adb logcat` oracles. Argent CDP is unusable on this
react-native-tvos build (`Runtime.addBinding wasn't found`); do not rely on it.

**Fault injection — mitmproxy `epic_stall_test.py`** (local-only, do NOT recreate):

| Mode | Simulates | Env |
|---|---|---|
| `token403` | CDN URL token expiry | `EPIC_MODE=token403 EPIC_EXPIRE_AFTER_S=45` |
| `origin403` | Channel dead at origin (fresh URLs also 403) | `EPIC_MODE=origin403 EPIC_EXPIRE_AFTER_S=30` |
| `blackhole` | Full internet outage | `EPIC_MODE=blackhole EPIC_BLACKHOLE_AFTER_S=45 EPIC_BLACKHOLE_DURATION_S=40` |
| `vodswap` | ONE proxy down (only mode yielding a *positive* swap) | `EPIC_MODE=vodswap EPIC_TARGET_PROXY=proxy2 EPIC_TARGET_SPEED_FAIL=502` |

- **Wire-up:** `mitmdump -s epic_stall_test.py -p 8080`, then
  `adb shell settings put global http_proxy <MAC_LAN_IP>:8080`. Debug build trusts the
  baked mitm CA (HTTPS decrypts, no cert install). Addon **never** intercepts `api.epictv.mx`.
- **Hygiene:** open with `./scripts/qa/preflight.sh` (exit 0 = clean); close with
  `./scripts/qa/cleanup.sh` (kills mitmdump + logcat, deletes all 3 proxy keys, resets `wm`).
  Deleting only `http_proxy` leaves the proxy live → ECONNREFUSED → ErrorBoundary.
- **Oracle:** JS logs reach logcat via `ReactNativeJS` on a relaunched debug build
  (`HANDLERELOADVIDEO`, `playerFailed`, self-heal lines). On `.development` + live Metro they
  may go to Metro stdout instead — verify per build, default to logcat-visible.
- **⚠️ AVD limit:** this AVD cannot produce a real NetInfo offline→online transition (no root,
  no WiFi radio, airplane-mode doesn't drop emulated Ethernet). Positive heal-on-transition is
  unit-only here; negative/no-loop paths ARE device-reachable.

---

## #255 — live 403 / segment failure surfaces to `onError` fast

**Goal:** live 403 recovers ~5s worst case (was 15–30s). Fix: live `minLoadRetryCount` 5→2 +
live stale-check 15s→5s.

**Flow:** start live → confirm playback → `token403` mid-playback (expiry 45s) → 403 on
playlist/segment → measure recovery → clear poison → confirm resume with fresh token.
`projects/epic-app/flows/tc255_live_403.yaml`.

- **Oracle:** logcat `Response code: 403|playerFailed|HANDLERELOADVIDEO|bad_http_status`,
  then recovery `HANDLERELOADVIDEO|handleReloadVideo`. Timeout ≥65s (403 fires at 45s + ~16s
  native ExoPlayer retry window).
- **Regression:** VOD unaffected (stale-check stays 15s, `minLoadRetryCount` stays 5).
- **PASS:** `onError` reaches JS reliably; persistently-poisoned token ends in clean
  `isExhausted` ("Channel unavailable"), not an infinite spinner.
- **Last device run:** 2026-07-13 ✅ — first 403 → `playerFailed` 16.26s (native), →
  `handleReloadVideo(bad_http_status)` 0.27s.

## #257 — CDN 502 de-noise (`REACT-NATIVE-1YT`)

**Goal:** `beforeSend` drops only `SentryHttpClientException` + status 502 + host
`proxy[123].cuca200.net`; everything else preserved.

**Flow:** 502 from `proxyN.cuca200.net` → NOT in Sentry; 502 from a different host (API) →
in Sentry; non-502 (500) from proxy host → in Sentry (status guard).
`projects/epic-app/flows/tc257_cdn_502.yaml`.

- **PASS:** proxy-host 502 silenced, everything else preserved.
- **Coverage:** unit-primary — `isCdnMediaHttpNoise` in `config/sentry.js`,
  `__tests__/config/sentry.test.js` 7/7. Re-run before any release touching the filter's
  hosts/status. Device/mitm run is optional (manual).

## #268 — mid-playback proxy swap yanks stream (black flash + rewind)

**Goal:** decouple trigger (excessive buffering ≥8s / VOD `onError`) from application
(controlled remount via `RELOAD_REASON.PROXY` + `PROXY_GENERATION_KEY` bump).
`useGetVideoData` no longer subscribes reactively to `BEST_PROXY_KEY`.

**Flow (positive swap needs `vodswap`):** blackhole/origin403 kill *all* streaming so the
speed test also fails (`changed:false`) — only `vodswap` degrades ONE proxy and yields a
winner. `projects/epic-app/flows/tc268_proxy_swap.yaml`.

| TC | Scenario | PASS |
|---|---|---|
| TC1 | Background proxy write during playback | no black frame / no remount / generation unchanged (static/unit) |
| TC2 | Excessive buffering ≥8s | timer fires once → `attemptProxySwap` → winner → spinner not black-flash → resume same position; gen +1 |
| TC3 | Transient blip <8s | timer cleared; no speed test, no bump, no remount |
| TC4 | VOD stream error | `onError` → swap first; `changed:true` swap+remount, STALE skipped; else fall through to STALE |
| TC5 | Live excluded | `handleExcessiveBuffering` short-circuits on `CONTENT_TYPE.LIVE` |
| TC6 | Buffering cooldown shared | 2nd ≥8s stall within 10min → `{winner:null, changed:false}` |
| TC7 | Breaker exhausts if new proxy also bad | `retryCountRef` climbs per PROXY remount; at `MAX_RETRIES` (8) → clean error, no loop |
| TC8 | Position preserved across swap | resume within ~1–2s, no rewind to `00:00` (original bug) |

- **PASS (headline):** black flash + rewind to `00:00` never reproduces, even under total
  stall; positive swap preserves position with a spinner.
- **Last device run:** 2026-07-14 ✅ — TC8 no-black-flash confirmed (froze on last frame
  `03:10`, scrubber intact); TC2/TC4 positive swap confirmed via `vodswap` (`502 proxy2` ×5 →
  winner `proxy3` `changed:true` → 96 proxy3 segments, 0×502 → advanced to `07:14`).
  `__tests__/utils/proxySpeedTest.test.ts` 33/33.

## #270 — speed test rejects fast-erroring proxies

**Goal:** `measureDownloadSpeed` scores an up-but-502 proxy **0**, not high. Fix:
`if (!response.ok) return 0;` after `fetch` (status gate — RN has no streaming body, byte-gate
draft was wrong).

**Flow (`vodswap` + `EPIC_TARGET_SPEED_FAIL=502`):** degrade best_proxy (manifest 502 +
`5MB.png` synthetic 502); healthy proxies serve synthetic 200 (2 MB). Confirm the 502 target
scores 0 and a healthy proxy wins. `projects/epic-app/flows/tc270_speed_test.yaml`.

- **PASS:** `changed:true` with a healthy winner; `206 Partial Content` (Range) NOT rejected
  (`response.ok` covers 200–299).
- **Last device run:** 2026-07-14 ✅ — byte-gate draft → all-zero → no swap → "Canal no
  disponible" (exposed RN `response.body === null`); status-gate fix → winner `proxy2`
  `changed:true` → sustained proxy2 manifest ~4min, 0×502. `EPIC_TARGET_SPEED_FAIL=502` is
  the reusable regression asset. Unit `proxySpeedTest` + `proxyResolver` 35/35.

## #269 — auto-heal on network return (VOD/live)

**Goal:** when connectivity returns after a sustained outage, force **exactly one** remount
instead of the player wedging on the last decoded frame. Qualifying terminal states: exhausted
`'stream'` (reset breaker + remount) and VOD buffering-`isStalled` (plain STALE remount).
`decoder` exhaustion excluded. Trigger = offline→online edge on `NetInfoUtil` + AppState-resume
fallback, one-shot via `healFiredRef`.

**Oracle (grep-able):** `self-heal on network return (exhausted)` /
`self-heal on network return (stalled)`. `projects/epic-app/flows/tc269_self_heal.yaml`,
plus the one-command `network_fault_recovery.yaml` (origin403 → error modal → restore → heal).

| Flow | Scenario | PASS |
|---|---|---|
| E2E-1 | VOD blackhole ~75s → restore | `self-heal … (stalled)` ≤1 NetInfo cycle + progress advances, no input |
| E2E-2 | Live exhausted (blackhole/origin403 to `PlayerError`) → restore | `self-heal … (exhausted)` + exits `PlayerError`, resumes |
| E2E-3 | Decoder terminal (negative) | NO self-heal log; stays `PlayerError` (`exhaustedReason==='stream'` gate) |
| E2E-4 | Flapping (negative loop) — cycle net 3–4× | exactly 1 self-heal line; no spinner loop |
| E2E-5 | AppState path — stalled → HOME → restore in bg → foreground | single recovery remount on resume |
| E2E-6 | No-regression — micro-stalls <8s | zero self-heal lines, zero spurious remounts |

- **⚠️ AVD:** E2E-1/E2E-5 and positive transitions can't be produced (no real NetInfo edge) →
  unit-only (`__tests__/screens/VideoPlayer/Layout.heal.test.js`). E2E-2's negative/no-loop
  assertion IS device-reachable and caught the real bug.
- **Last device run:** 2026-07-30 ✅ — E2E-2 via `origin403` surfaced an **infinite reconnect
  loop** (heal fired on NetInfo's immediate current-state callback, resetting the breaker every
  ~35s). Found + fixed (edge guard `sawOffline`) + device-verified: player exhausts and stays on
  "Channel unavailable", no loop.
- **⚠️ 2026-08-03 — E2E-2 attempted with a REAL WiFi cutoff instead of `origin403`, exposed a
  gap: see #280.** `origin403` fails at proxy/CDN level and never trips
  `NetInfo.isInternetReachable`, so the global "Network Error" screen (`useNetworkError.js`,
  15s threshold) never appears and the player breaker runs free to genuine exhaustion — that's
  what E2E-2's 07-30 pass actually exercised. A **real** WiFi radio-off (AMC live, held ~150s to
  span the full 8-retry backoff ladder) hits the global screen first: it unmounts the player at
  ~15s with the breaker stuck at `retryCount:2`, never reaches `isExhausted`, and on reconnect
  the global screen self-dismisses back to the Live TV grid **without resuming the channel** —
  `handleRecoverFromExhausted` never fires because exhaustion itself is never reached this way.
  **#269's exhausted-self-heal is therefore verified only against proxy-level failures, not
  against genuine connectivity loss** — open question for whoever picks up #280.

---

## #279 — `ERROR_CODE_IO_NETWORK_CONNECTION_FAILED` missing from reload allowlist

**Goal:** confirm `handleReloadVideo` fires for a VOD `onError` carrying ExoPlayer's dedicated
network-loss code, not just `ERROR_CODE_IO_BAD_HTTP_STATUS` / `ERROR_CODE_IO_UNSPECIFIED`. Fix:
added `'ExoPlaybackException: ERROR_CODE_IO_NETWORK_CONNECTION_FAILED'` to `ERRORS` in
`components/VideoPlayer/constants.js`.

**Distinct from #269 E2E-1:** #269's VOD case is a silent buffering stall (`isStalled`, no
`onError` at all). This case is an **explicit `onError`** — a real WiFi radio cycle mid-playback
throws `ExoPlaybackException: Source error` (root cause `UnknownHostException`, DNS not yet
resolved in the post-reconnect revalidation window) with `errorString` set to
`ERROR_CODE_IO_NETWORK_CONNECTION_FAILED`. Pre-fix, this code fell through the allowlist check
in `usePlayerActions.js:onError` straight to `LoggerUtil.loggerPlayerError` (Sentry-only) —
`handleReloadVideo` never ran, zero `HANDLERELOADVIDEO` log, player wedged on the error frame
indefinitely with no recovery path (worse than #269: not even the first breaker retry fires).

**Oracle (grep-able):** `HANDLERELOADVIDEO` with `reason:"stale"` appearing within a few seconds
of the reconnect; absence = regression.

**Repro (real device only — needs a genuine WiFi radio cycle, no AVD/mitmproxy substitute):**
1. Play VOD to `ONLOAD`.
2. `adb shell svc wifi disable` → wait ~8s → `adb shell svc wifi enable` (tight, single command
   chain — don't let the gap grow past ~10s or you drift into #269's exhausted/network-error
   territory instead of this specific onError path).
3. Watch logcat for `ExoPlaybackException` + `HANDLERELOADVIDEO`.

- **⚠️ Physical device + USB adb required.** Wireless adb dies the instant WiFi disables (the
  control channel rides the same radio) — see `feedback_physical_tv_usb_adb_network_toggle`
  memory. USB-C data cable + "Depuración USB" (separate toggle from "Depuración inalámbrica")
  keeps `adb devices -l` alive through the whole cycle.
- **Last device run:** 2026-08-03 ✅ — pre-fix repro confirmed (Chromecast `sabrina`, VOD "The
  Mandalorian and Grogu"): exact `errorString` captured via temporary diagnostic log (reverted),
  zero recovery observed for 60s+. Fix applied (`ERRORS` allowlist) same session, then
  **post-fix re-verified same device/session**: identical WiFi cycle → same
  `ERROR_CODE_IO_NETWORK_CONNECTION_FAILED` → `HANDLERELOADVIDEO {retryCount:1,
  reason:"stale"}` fired → remount → `ONLOAD {reloadVideo:true, playerTime:282.7}` — resumed
  from the exact pre-error position, no user input. First attempt of the post-fix pass hit a
  clean reconnect (DNS resolved before ExoPlayer retried, no error at all) — this error is
  timing-dependent on the DNS revalidation window, not deterministic every cycle; needed a
  second WiFi cycle to reproduce and confirm the fix.

---

## Deferred
- **#257-B** real proxy failover on live 502/5xx (`runProxySpeedTest` on `onError`) — rides on
  #255-A; validate real `REACT-NATIVE-1YT` event shape in Sentry first.
