# Net E2E Plan — #269 self-heal on network return (physical Android TV, no OCR)

> Working plan for validating the STAGING fix (#269 auto-heal on network return, VOD/live)
> via tvqa on a **physical Android TV** with real WiFi toggling. Oracle is **100% logcat** —
> no OCR, no screencap. Self-contained; another agent can resume from here.

## Fixed decisions (from the user, 2026-08-03)

- **Device target:** physical Android TV + real WiFi toggle (user-operated). This is the ONLY
  way to produce a real NetInfo `offline→online` transition — the emulator cannot (no root,
  no WiFi radio, emulated Ethernet `eth0` via QEMU slirp; mitmproxy blackhole/403 blocks *at
  the proxy* without flipping `NetInfo.isConnected`). See `epic-app/docs/mitmproxy_harness_context.md` §7.
- **Build:** debug build with `network_security_config` + baked mitmproxy CA must be
  **rebuilt+installed** carrying the current working-tree #269 code.
- **Oracle:** logcat-only. No OCR states on the player screen (a11y there is 0-node).

## The fix under test (uncommitted working tree, `release/1.3.21`)

- `screens/VideoPlayer/Layout.js` — unified NetInfo self-heal effect + AppState-resume fallback.
- `screens/VideoPlayer/hooks/usePlayerActions.js` — new `isStalled` signal (set on 8s buffering
  timer, cleared on progress/onBuffer(false)/onLoad).
- `screens/VideoPlayer/hooks/useReloadPlayer.js` — `handleRecoverFromExhausted` (reset stream
  counters + one remount; decoder retries NOT reset).
- `utils/proxyResolver.ts`, `utils/proxySpeedTest.ts` — comment-only (#270 cooldown 30min, N×2MB).
- Unit tests: `Layout.heal.test.js`, `usePlayerActions.stall.test.js`, `useReloadPlayer.test.js`
  — **39 pass** (2026-08-03). These cover the positive-heal logic at unit level.

## Oracle lines (grep-able in logcat)

- `self-heal on network return (exhausted)` — emitted by `handleRecoverFromExhausted`.
- `self-heal on network return (stalled)` — emitted by the VOD-stalled heal branch.
- Support tokens: `isExhausted`, `reload_exhausted`, `playerFailed`, `bad_http_status`,
  `HANDLERELOADVIDEO`, `[epic][diag STREAM]`, ExoPlayer `STATE_READY` (playback-reached gate).

## Coverage matrix

| Path | Validates | Where | Oracle |
|---|---|---|---|
| Positive VOD-stalled | resumes on network return | physical + WiFi | line `(stalled)` + resume |
| Positive live-exhausted | recovers on network return | physical + WiFi | line `(exhausted)` + resume |
| Negative / no-loop | stays exhausted, no reconnect loop | physical or emu | origin403; ABSENCE of repeated `self-heal` after proxy_stop |
| Decoder terminal | stays PlayerError, no loop | physical | logcat, no `self-heal` |
| Net flapping | ≤1 remount per episode | physical | logcat |
| Speed-test swap (#270) | 502-proxy scores 0, healthy wins | physical or emu | vodswap+502, `changed:true` |

## Environment facts (measured 2026-08-03)

- **Mac LAN IP:** `192.168.1.172` (`ipconfig getifaddr en0`). Physical device proxy host = this,
  NOT `10.0.2.2` (that is the emulator-only alias).
- **mitmproxy CA:** `~/.mitmproxy/mitmproxy-ca-cert.pem` == repo baked
  `android/app/src/debug/res/raw/mitmproxy_ca.pem` (`diff -q` empty). No recopy needed.
- **netsec config:** `android/app/src/debug/res/xml/network_security_config.xml` present;
  debug `AndroidManifest.xml` has `android:networkSecurityConfig="@xml/network_security_config"`.
- **Tooling installed:** `mitmdump`, `tvqa`, `agent-device`, `android/gradlew`.
- **Device attached at plan time:** NONE (`adb devices` empty) — Phase 0 blocker.
- **QA creds:** `cesarrivas` / `12345` (`TVQA_USERNAME`/`TVQA_PASSWORD`). Remember-me ON → a
  re-typing login doubles creds → 401. Use prefill-submit (see `login_remembered.yaml`).

## Phases

### Phase 0 — Prereqs (needs device connected)
1. USER: connect Android TV over adb (LAN) → provide `adb devices` serial.
2. Build+install debug carrying working-tree #269: `cd android && ./gradlew installDebug`.
3. CA already matches, netsec already present → no cert steps.

### Phase 1 — Calibrate harness to physical device (tool edits)
- `projects/epic-app/project.yaml`: `proxy.host_ip: 10.0.2.2 → 192.168.1.172`; `serial_hint → <physical serial>`.
- Convert `tc269_self_heal.yaml` / `tc270_speed_test.yaml` to **logcat-only** oracle: drop OCR
  `assert_state` on player; add a playback-reached logcat gate (`STATE_READY`) before fault injection.
- New positive-heal driver flow(s): `drive_to_vod` + `drive_to_live` (nav only, stop at
  playback-reached). Positive heal runs as DISCRETE tvqa commands (agent cues human WiFi toggle),
  NOT one server-side flow, because the human needs real-time cues.

### Phase 2 — Preflight
- `tvqa hygiene check` · `tvqa proxy check --project projects/epic-app`.
- Verify a11y anchors on physical: `login_form` "Inicia sesión", `profile_select` "Who is
  watching?", `live_tv_grid` "Costa Rica", `home_screen_rail` "Top 10" (rotated — weak gate).

### Phase 3 — Run net tests (no OCR)
- Automated (server-side `tvqa run`): `tc270_speed_test` (vodswap+502), `tc269_self_heal` negative.
- Positive #269 (discrete, agent-cued WiFi toggle):
  1. `tvqa run drive_to_vod` → playback-reached.
  2. **[USER] WiFi OFF** → `tvqa log-wait "isStalled|excessive buffering" -t 60`.
  3. **[USER] WiFi ON** → `tvqa log-wait "self-heal on network return \(stalled\)" -t 60` → resume.
  4. Repeat for live-exhausted with line `(exhausted)`.

### Phase 4 — Cleanup + report
- `scripts/qa/cleanup.sh` (kills mitmdump + adb logcat, deletes all 3 proxy keys, resets wm).
- `tvqa hygiene clean`. Report per-flow JSON + which oracle lines fired.

## Manual steps mapped (user actions)
- **M1** connect Android TV to adb (once) → serial.
- **M2** WiFi OFF / WiFi ON on agent cue (the real offline→online; 2 flows).
- **M3** (if remember-me off) initial login — or agent drives it.

## Progress log
- 2026-08-03: plan created. Context gathered (harness README/AGENTS/CHANGELOG/feedback, app fix
  diff, mitmproxy harness doc, tc269/tc270 flows, states.yaml). Unit tests 39 pass. Mac IP + CA
  verified. Awaiting device connect for Phase 0.
- 2026-08-03 (cont.): device connected — **Chromecast Google TV (sabrina), Android 14**, wireless
  adb serial `adb-26251HFDD6RBL8-WOEk68._adb-tls-connect._tcp`.
  - **Phase 0 DONE.** `installDevelopmentDebug` (flavored; plain `installDebug` is ambiguous).
    Install first blocked by `INSTALL_FAILED_UPDATE_INCOMPATIBLE` (field-build signature) →
    `adb uninstall com.epictv` + `adb install -r app-development-debug.apk` = Success. Metro
    already up on 8081; `adb reverse tcp:8081 tcp:8081` set. App boots, `ReactNativeJS` logcat live.
  - **Oracle path CONFIRMED.** `LoggerUtil.loggerInfo` gated on `__DEV__` (true in dev-debug) →
    `console.info` → logcat tag `ReactNativeJS`. logger.js **UPPERCASES the flow name**, so the
    heal line in logcat is `SELF-HEAL ON NETWORK RETURN (EXHAUSTED|STALLED)`. tvqa `wait_for_line`
    is `re.IGNORECASE` + tails all of logcat → lowercase patterns match. `reportExhausted` and the
    `proxy swap` breadcrumb are **Sentry-only** (NOT logcat); the logcat-visible retry marker is
    `HANDLERELOADVIDEO`, playback-reached marker is `ONLOAD`/`ONREADYFORDISPLAY`. proxySpeedTest.ts
    has **zero** logger calls → speed test invisible in logcat (only its consequence `HANDLERELOADVIDEO`).
  - **Phase 1 DONE (tool edits):** project.yaml `host_ip`→192.168.1.172, `serial_hint`→physical.
    New runner step **`assert_no_log`** (PASS when pattern absent in window) = the no-loop oracle;
    +2 unit tests (20/20 runner tests pass). tc269 tail rewritten logcat-only (ONLOAD gate →
    origin403 → HANDLERELOADVIDEO → exhaust → `assert_no_log "self-heal on network return"`).
    tc270 de-OCR'd (ONLOAD gate + HANDLERELOADVIDEO swap oracle). New `drive_to_vod.yaml` /
    `drive_to_live.yaml` (login+nav+play, stop at ONLOAD) for the human-cued positive path.
  - **Phase 2 DONE:** hygiene clean (set `private_dns_mode off`); proxy check — `epic_stall` addon
    FOUND (all #269/#270 modes covered); missing auth_expired/auth_revoke addons are #275-only, N/A.
  - **Phase 3 — negative path: PASSED (device-verified, 2026-08-03).** Automated
    end-to-end tc269 YAML hit intermittent device-side playback flakiness (first
    play after cold-boot/remount sometimes never fires onLoad — app-side, unrelated
    to #269, see tvqa memory `tvqa_physical_device_setup`), so the fault-injection
    half was driven as discrete commands once a channel (AMC) was confirmed
    playing: `proxy: {mode: origin403, EPIC_EXPIRE_AFTER_S: 30}` → real retry loop
    engaged (`HANDLERELOADVIDEO retryCount:1 reason:stale` @38s) → breaker
    exhausted → proxy stopped → `assert_no_log "self-heal on network return"` held
    clean 45s. **Confirms the #269 no-loop guarantee on real hardware, zero OCR.**
  - **Phase 3 — positive path (STALLED + EXHAUSTED via real WiFi toggle): PENDING
    human WiFi hands.** See choreography below.
  - **2026-08-03 (cont.): switched tc270 to EMULATOR** (4K_TV AVD, emulator-5554,
    agent-device name "4K TV") — tc270 doesn't need real WiFi (proxy-fault-only),
    so physical device wasn't required and its network was the actual blocker
    (real ERR_NETWORK on token refresh, root cause never isolated). Chromecast
    disconnected (`adb disconnect`); `ADB_MDNS=0` set (adb was auto-reconnecting
    to the paired Chromecast every ~2s via mDNS, causing `more than one
    device/emulator` — export in shell profile). Reinstalled current debug APK
    on emulator (old install was a stale build, uninstall+install needed, same
    signature-mismatch pattern as physical). agent-device session binding on
    emulator needed the SAME session/device juggling as physical (`DEVICE_IN_USE`,
    stale `default` session pre-bound with a mismatched cached display name) —
    fixed by killing the agent-device daemon process (`kill <pid of daemon.js>`)
    to drop all live device claims, then using `agent_device_session: default`
    with no `--device` selector. project.yaml: `proxy.host_ip` → `10.0.2.2`,
    `serial_hint` → `emulator-5554`, `agent_device_name` removed.
  - Fresh install wiped persisted session → one-time manual login via
    `flows/login.yaml` needed recalibration: `press '@ref'` (tap-by-ref) on a
    text field opens agent-device's OWN floating compose IME
    (`com.callstack.agentdevice.imehelper`) which does NOT commit into the RN
    TextInput (text visibly doubles/accumulates in a floating box, real field
    stays empty) — the WORKING pattern is keyevent-only: native-focused field →
    `adb shell input keyevent DPAD_CENTER` → `agent-device type` → `adb shell
    input keyevent 66` (commits correctly into the real field, confirmed via
    screenshot each step). Login succeeded, profile "cesar" selected, session
    now persisted (Recordarme) on the emulator.
  - **tc270 automated run: got to step 20/22** (reset→nav→priming-play→
    dismiss_rn_overlay→real play→ONLOAD gate all passed with ZERO manual
    intervention — unlike physical device, no onLoad flakiness hit). Failed
    only at the vodswap swap-trigger wait (`HANDLERELOADVIDEO` not seen in 60s)
    — this is the flow's own documented pre-existing limitation (vodswap
    degrades the speed-test URL, not necessarily the live CDN stream, so no
    buffering was forced this run). NOT a new emulator bug. #270 itself is
    already device-verified 2026-07-14; this automated oracle is regression-only
    and known-fragile. **Net result: emulator eliminated ALL physical-device
    friction this session (session targeting, cold-boot flakiness, network
    blocker) for the tests that don't need real WiFi.**

## Positive-heal choreography (human WiFi toggle — run as DISCRETE commands)
Creds: `TVQA_USERNAME=cesarrivas TVQA_PASSWORD=12345`. From harness dir.

**STALLED branch (VOD):**
1. `tvqa run projects/epic-app/flows/drive_to_vod.yaml --project projects/epic-app` → wait `passed:true`.
2. Agent: `tvqa log-wait "onbuffer|handlereloadvideo" -t 60` **[USER: WiFi OFF now]** (stall builds ~8s).
3. Agent: `tvqa log-wait "self-heal on network return \(stalled\)" -t 60` **[USER: WiFi ON now]** → PASS = heal fired + resume.

**EXHAUSTED branch (live):**
1. `tvqa run projects/epic-app/flows/drive_to_live.yaml --project projects/epic-app` → `passed:true`.
2. **[USER: WiFi OFF, hold ~60s]** so the breaker runs MAX_RETRIES and exhausts.
3. Agent: `tvqa log-wait "self-heal on network return \(exhausted\)" -t 60` **[USER: WiFi ON now]** → PASS.

Note: WiFi OFF/ON = the real NetInfo offline→online edge the emulator can't produce and the fix
gates on (`sawOffline` guard). Keep the app foregrounded (backgrounding triggers the AppState-resume
fallback, a different code path).
