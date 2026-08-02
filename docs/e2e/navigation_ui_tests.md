# E2E — Navigation / UI / Auth tests (epic-app Android TV)

Everything that is **not** network-fault injection: the happy-path navigation smoke, font/UI
scaling, auth/session behavior, and the login flows. Here the *app* is the system under test —
I drive the D-pad and assert focus, rendering, and modal/copy correctness.

- **App:** `com.epictv`, `release/1.3.21`, build `1.3.34.development`, `emulator-5554`.
- **Companion doc:** proxy / CDN / self-heal cases live in `network_proxy_tests.md`.
- **Source of intent + run history + tooling coverage matrix:** `./e2e_test_suite.md` (General smoke, #265, #275/#276/#277).
- **tvqa flows:** `projects/epic-app/flows/`.

---

## Setup (common)

**Control path:** `adb shell input keyevent` (D-pad 21/22/19/20/23, BACK 4, HOME) + `adb logcat`
for crashes/focus. No mitmproxy needed except the auth cases (§#275).

**Login — Remember-me trap:** `Recordarme` prefills user/pass. A flow that types on top doubles
them (`cesarrivascesarrivas`) → `401 authentication_failed`. Use `login_remembered.yaml`
(submit prefill, no typing). Creds via `TVQA_USERNAME`/`TVQA_PASSWORD` (`cesarrivas` / `12345`),
never hardcoded in committed YAML.

**Navigation reality on this build:** blind fixed-sleep D-pad nav is brittle unattended —
variable cold-boot, conditional LogBox dev toasts that steal focus, sparse/0-node a11y on most
screens (rich only on the **login form** and **Live TV grid**). Prefer state-gated nav where an
anchor exists; `live_tv_grid` anchor = `"Costa Rica"` (stable), NOT `"TV en vivo"` (absent).
`open_app` only foregrounds — deterministic reset = `adb am force-stop com.epictv` + relaunch
(session persists → cold-boots to Home), then dismiss the dev toast (`DPAD_CENTER`).

---

## General app smoke (happy path)

No harness — plain D-pad sweep of every major flow. Goal: catch crashes, focus-traps (D-pad
dead / no focusable view), and blank screens **before** drilling into issue-specific cases.
Watch `adb logcat` for `AndroidRuntime` / `FATAL` / `ReactNativeJS` errors and a stuck
`mCurrentFocus`. Flows `projects/epic-app/flows/s1..s10*.yaml`.

| # | Flow | Steps | Watch for |
|---|---|---|---|
| S1 | Auth | Login (user/pass) → PinCode if prompted | login succeeds, no crash on submit |
| S2 | Profiles | select adult; relaunch → select Kids | both load; Kids gating applies |
| S3 | Home | scroll carousels (Top 10, Continuar viendo, Estrenos), D-pad U/D/L/R | no focus-trap, rows render, no blank cards |
| S4 | VOD playback | Continuar viendo → Resume → play → pause → seek (L/R) → resume | plays, seek commits, position preserved; overlay hides/shows |
| S5 | VOD next-episode | series → play → next-episode control | advances without remount-to-start |
| S6 | Live TV | grid → open channel → zap to another → toggle favorite | plays, zapping doesn't kill focus, favorite persists |
| S7 | Search | Search → type query (native keyboard) → open result | results render, keyboard input works |
| S8 | Settings | root → submenus | navigable, no clipping |
| S9 | Lifecycle | playing VOD → HOME (background) → relaunch (foreground) | resumes, no zombie player, no crash |
| S10 | Logout | Settings/profile → logout | returns to login, session cleared |

- **PASS:** every flow completes; zero crashes/ANR; zero focus-traps; no blank/broken screens.
- **Note:** app-wide baseline. A smoke failure blocks the release regardless of the issue cases.

## #265 — `fontSize` dp → `Style.px` sweep (UI scaling)

**Goal:** text scales proportionally on sub-1080p panels (no oversize/clipping).
`projects/epic-app/flows/tc265_font_scaling.yaml`.

- **Visual smoke** (per screen with wrapped `fontSize`, vs prior build, no clipping/overflow):
  Auth (Login, PinCode) · Profiles (list, CreateProfile, ProfileName) · Settings (root +
  submenus) · Content rows (Home carousels, Media/Poster cards, Avatar) · Live (LiveSideBar,
  Banner) · Player (PlayerTitle, PlaybackRate) · Transient (Toast, NetworkError, Keyboard).
- **Automated:** `scripts/qa/tv-ui-matrix.sh` — 720p + 1080p profiles, screenshot diff.
  font-scale axis stable (fs1.0 == fs1.3 by native clamp); only resolution axis matters.
- **Specific check (carry forward):** Home → "Top 10" carousel, numbers 1–10 fully visible /
  not clipped by the card top edge in ≥1 sub-1080p resolution (the `topTenTitle` raw-dp offset).
- **PASS:** no new clipping, text scales with panel height.
- **Last run:** 2026-07-13 ✅ (`wm density 320`/`160`; found+fixed the Top 10 badge offset,
  commit `22c1a5f`).

## #275 / #276 / #277 — auth `403 expired_user` (Sentry de-noise + revoke-modal copy)

**Goal:** `403 error_code:expired_user` = expired subscription (business state), distinct from
the deliberate `401` revoke. Fix: `expectedErrorCodes` degradation in `loggerError` +
revoke-path `error_code` priority in `config/axios.js`. Canonical Sentry group
**`REACT-NATIVE-1XD`**. `projects/epic-app/flows/tc275_auth_expired.yaml`.

**Runner:** `adb` + a **puntual** mitmproxy addon (`auth_expired_user_test.py` /
`auth_refresh_revoke_test.py`) — these DO intercept `api.epictv.mx`; proxy via `10.0.2.2:8080`.
⚠️ These addons are ephemeral scratchpad files — **absent from disk**; `tvqa proxy check`
reports them missing. Recreate before running tc275.

| TC | Scenario | PASS |
|---|---|---|
| TC1 | Login `403 expired_user` on `/token/` (#275) | expired-subscription modal shows AND no new Sentry event for `postLoginAuth` (only `category:'api'` breadcrumb) |
| TC2 | Refresh `403 expired_user` on `/token/refresh/` (#277) | revoke modal shows `EXPIRED_USER_MESSAGE` ("Tu **cuenta** ha expirado…"), NOT `SESSION_EXPIRED_MESSAGE` |
| TC3 | Undeclared 403 (e.g. `device_login_detected`) or no `error_code` | still reaches `captureException` (unit-covered, not re-run on device) |

- **PASS:** noise gone for `expired_user`, trace preserved as breadcrumb; revoke modal
  prioritizes the refresh's `error_code`.
- **Last run:** 2026-07-21 ✅ — A/B decisive with Sentry-envelope capture (CONTROL sends event,
  WITH-FIX 0 events → breadcrumb); Cambio C A/B decisive (CONTROL session-expired copy,
  WITH-FIX account-expired). Unit `logger.test.js` + `axios.test.js` 70/70; full suite 499
  pass / 1 skip.

## Login flows (building blocks)

| Flow | Use | Notes |
|---|---|---|
| `login_remembered.yaml` | ✅ default | Submits Remember-me prefill (no typing). Cold-boot may show an "Aceptar" session dialog first (only after a logout), then login form with `login_button` focusable. |
| `login.yaml` | ⚠️ only if fields empty | Types user/pass — doubles them when Remember-me prefilled → `401`. |

---

## Known constraints (carry into every run)
- Argent CDP unusable on this react-native-tvos build → adb-first for everything.
- a11y is rich only on login form + Live TV grid; player / home / VOD grids are sparse/0-node —
  gate nav on those two anchors, drive the rest by calibrated keyevent sequences.
- Every pre-`d87c4ad` tvqa "green" is invalid (stale-buffer oracle bug); the suite's manual
  adb+mitmproxy ✅ entries are unaffected.
