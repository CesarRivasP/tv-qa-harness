# EpicTV QA Flows (`projects/epic-app`)

This directory contains the **tvqa** E2E flow definitions for the EpicTV Android TV
app (`com.epictv`).

## Quick start

```bash
export TVQA_USERNAME=your_qa_username
export TVQA_PASSWORD=your_qa_password
cd ~/Documents/work/tv-qa-harness

# Pre-flight
tvqa hygiene check
tvqa devices

# Run a single flow
tvqa run projects/epic-app/flows/s1_auth.yaml --project projects/epic-app

# Run the whole smoke suite (bash loop)
for f in projects/epic-app/flows/s*.yaml; do
  tvqa run "$f" --project projects/epic-app
done
```

**Output is ONE JSON line per flow.** Parse it — do not ask for more output.

## Flow inventory

### Smoke suite (S1–S10) — happy-path regression

| Flow | File | States used | Notes |
|------|------|-------------|-------|
| S1 Auth | `s1_auth.yaml` | `login_form` → `profile_select` | Keyboard.Native, ENTER per field |
| S2 Profiles | `s2_profiles.yaml` | `profile_select` → `home_screen_rail` | Adult then Kids |
| S3 Home | `s3_home.yaml` | `home_screen_rail` | Carousel scroll, focus-trap guard |
| S4 VOD playback | `s4_vod_playback.yaml` | `home_screen_rail` → `vod_player` | Resume, pause, seek |
| S5 VOD next-episode | `s5_vod_next_episode.yaml` | `home_screen_rail` → `vod_player` | Trigger next-episode control |
| S6 Live TV | `s6_live_tv.yaml` | `home_screen_rail` → `live_tv_grid` | Zap, toggle favorite |
| S7 Search | `s7_search.yaml` | `home_screen_rail` → `search_screen` → `vod_player` | Native keyboard input |
| S8 Settings | `s8_settings.yaml` | `home_screen_rail` → `settings_root` → `settings_submenu` | Submenu navigation |
| S9 Lifecycle | `s9_lifecycle.yaml` | `home_screen_rail` → `vod_player` → `home_screen_rail` | HOME background → relaunch |
| S10 Logout | `s10_logout.yaml` | `home_screen_rail` → `settings_root` → `login_form` | Session cleared |

### Per-issue flows — hardened edge cases

| Issue | File | Harness | Oracle / PASS criteria |
|-------|------|---------|------------------------|
| #265 font scaling | `tc265_font_scaling.yaml` | `wm density` | No clipping at 720p; Top 10 badge visible |
| #255 live 403 | `tc255_live_403.yaml` | `epic_stall_test.py` (token403) | `playerFailed` reaches JS; recovers after proxy stop |
| #257 CDN 502 de-noise | `tc257_cdn_502.yaml` | `epic_stall_test.py` (origin403) | Manual Sentry check: 0 new `REACT-NATIVE-1YT` for proxy 502 |
| #268 proxy swap | `tc268_proxy_swap.yaml` | `epic_stall_test.py` (vodswap kill) | No black flash, position preserved, `vod_player` stays |
| #270 speed-test status gate | `tc270_speed_test.yaml` | `epic_stall_test.py` (vodswap 502) | Healthy proxy wins (`changed:true`); playback continues |
| #269 self-heal | `tc269_self_heal.yaml` | `epic_stall_test.py` (origin403) | Player **stays** exhausted; no `self-heal` loop in logcat |
| #275 auth expired | `tc275_auth_expired.yaml` | `auth_expired_user_test.py` | Expired-subscription modal; no Sentry event for `postLoginAuth` |

## Calibration status

| State | Method | Calibrated? | Notes |
|-------|--------|-------------|-------|
| `login_form` | a11y | ✅ | `Inicia sesión` visible |
| `profile_select` | a11y | ✅ | `Quién está mirando` visible |
| `home_screen_rail` | a11y | ✅ | `Home` visible |
| `vod_player` | ocr | ⚠️ placeholder | `:` time display box guessed; measure on device |
| `live_tv_grid` | a11y | ⚠️ placeholder | `En vivo` guessed; verify with snapshot |
| `search_screen` | a11y | ⚠️ placeholder | `Buscar` guessed; verify with snapshot |
| `settings_root` | a11y | ⚠️ placeholder | `Configuración` guessed; verify with snapshot |
| `settings_submenu` | a11y | ⚠️ placeholder | `Cuenta` guessed; adjust to actual first submenu header |
| `channel_unavailable` | ocr | ✅ | `unavailable` substring |
| `network_error_modal` | ocr | ✅ | `Error de red` substring |
| `auth_error_modal` | ocr | ⚠️ placeholder | `expirado` guessed; measure actual modal text |

### How to calibrate a new state

1. Navigate to the screen on the emulator.
2. Run `tvqa snapshot` (text-only).
3. If useful text nodes appear → `method: a11y`, `expected_text: "<exact text>"`.
4. If empty/noisy → `method: ocr`, open a screenshot in Preview/GIMP, measure the
   bounding box `[left, top, right, bottom]` in physical pixels, set `expected_substring`.
5. Edit `states.yaml`, save, commit.

## Environment variables

| Variable | Required for | Example |
|----------|--------------|---------|
| `TVQA_USERNAME` | S1, S2, S9, S10, tc275 | `cesarrivas` |
| `TVQA_PASSWORD` | S1, S2, S9, S10, tc275 | `12345` |

Do **not** commit credentials. Use `.env` (ignored by git) or export in your shell.

## AVD limitations (documented)

- **No real NetInfo offline→online transition** on this emulator (no root, no WiFi
  radio, airplane-mode doesn't drop Ethernet). The positive self-heal paths
  (E2E-1/E2E-5 in #269) are unit-only; the negative/no-loop path (E2E-2) is
  device-reachable.
- **Keyboard.Native** is the real system TextInput overlay, not a custom grid.
  `type` steps use `adb shell input text`; submit per-field with `keyevent 66`.

## References

- `docs/e2e_test_suite.md` in the app repo — authoritative test plan (Part 1 + Part 2)
- `AGENTS.md` in the harness repo — token-budget rules for AI agents
