# Mitmproxy Integration Plan — tvqa

> **Goal:** Make network-fault E2E testing as simple as `tvqa run flows/tc268_proxy_swap.yaml --project projects/epic-app`.
> **Constraint:** Keep the token-budget contract intact. No new per-step agent round trips.

---

## 1. Current State (what already works)

| Component | Status | Gap |
|---|---|---|
| `tvqa/proxy.py` | ✅ Start/stop mitmdump, clears 3 proxy keys | No addon registry; path must be absolute |
| `runner.py` steps `proxy_start` / `proxy_stop` | ✅ Functional | Requires full addon path + env dict inline |
| `hygiene.py` | ✅ Detects proxy residue | Doesn't verify mitmproxy is installed/running |
| `project.yaml` proxy section | ✅ host_ip/port configurable | No addon aliases or mode presets |
| Flows `tc255`–`tc275` | ⚠️ Skeletons written | Not executable end-to-end without manual mitmproxy setup |
| `tc276_auth_revoke.yaml` | ⚠️ Added later (issue #276/#277) | Same gap as above |

## 2. Gaps Identified

### G1 — Addon path friction
Today a flow author must know the absolute path to `epic_stall_test.py`:
```yaml
- proxy_start:
    addon: /Users/admin/Documents/work/epic-app/variants/epic-app/docs/version_1_3_21_issues/testing/epic_stall_test.py
```
This breaks if the epic-app repo moves or if the addon is renamed.

### G2 — No mode presets
The 4 modes (`token403`, `blackhole`, `origin403`, `vodswap`) are just env-var combinations. Authors must remember which env keys each mode needs.

### G3 — No proxy health check
If mitmproxy isn't running or the device proxy isn't set, the flow fails with a generic timeout instead of "proxy not active."

### G4 — No integration with epic-app preflight/cleanup
`./scripts/qa/preflight.sh` and `cleanup.sh` in epic-app do the same job as `tvqa hygiene`, but they live in the app repo. tvqa should either call them or replicate their checks.

### G5 — Auth addons not discoverable
`auth_expired_user_test.py` and `auth_refresh_revoke_test.py` are scratchpad files with no stable path. They need a registry entry.

### G6 — No log capture from mitmproxy
When a proxy flow fails, the mitmproxy stderr/stdout is lost (`DEVNULL`). A debug mode should pipe it to `artifacts/`.

---

## 3. Proposed Design (3 phases)

### Phase 1 — Addon Registry + Mode Presets (immediate, low effort)

**Add to `project.yaml` (paths relative to project root):**
```yaml
proxy:
  host_ip: "10.0.2.2"
  port: 8080
  addons:
    epic_stall: "variants/epic-app/docs/version_1_3_21_issues/testing/epic_stall_test.py"
    auth_expired: "variants/epic-app/docs/version_1_3_21_issues/testing/auth_expired_user_test.py"
    auth_revoke: "variants/epic-app/docs/version_1_3_21_issues/testing/auth_refresh_revoke_test.py"
  modes:
    token403:
      addon: epic_stall
      env:
        EPIC_MODE: token403
        EPIC_EXPIRE_AFTER_S: 45
    blackhole:
      addon: epic_stall
      env:
        EPIC_MODE: blackhole
        EPIC_BLACKHOLE_AFTER_S: 45
        EPIC_BLACKHOLE_DURATION_S: 40
    origin403:
      addon: epic_stall
      env:
        EPIC_MODE: origin403
        EPIC_EXPIRE_AFTER_S: 30
    vodswap:
      addon: epic_stall
      env:
        EPIC_MODE: vodswap
        EPIC_TARGET_PROXY: proxy2
        EPIC_TARGET_SPEED_FAIL: 502
    auth_expired:
      addon: auth_expired
    auth_revoke:
      addon: auth_revoke
```

**New runner step `proxy`:**
```yaml
- proxy:
    mode: vodswap          # alias → resolves addon + default env from project.yaml
    env:                   # optional overrides
      EPIC_TARGET_PROXY: proxy2
      EPIC_TARGET_SPEED_FAIL: 502
```
> The `proxy` step starts the proxy with the given mode. It does **not** stop it — use `proxy_stop` at the end of the flow, or rely on the flow-level `proxy:` key (Phase 3).

**Backward compatibility:** `proxy_start` / `proxy_stop` continue to work. `proxy` is syntactic sugar for `proxy_start` with mode resolution.

### Phase 2 — Health Checks + Preflight (medium effort)

**New CLI command:**
```bash
tvqa proxy check --project projects/epic-app
```

Returns JSON:
```json
{"mitmproxy_installed": true, "mitmproxy_running": false, "device_proxy_set": false, "addons_found": {"epic_stall": true, "auth_expired": false}}
```

**New runner step `proxy_assert`:**
```yaml
- proxy_assert:
    mode: vodswap        # optional: also verifies the addon for this mode is loaded
    timeout: 5
```
Fails fast if mitmproxy isn't installed, isn't running, or the device proxy isn't set. If `mode` is given, it also checks that the addon mapped to that mode is present in the registry. This avoids waiting 30s for a downstream state timeout.

**Integration with epic-app preflight:**
`tvqa hygiene check` gains an optional `--project` flag that also verifies `project.yaml` proxy section is valid and addons exist on disk.

### Phase 3 — Log Capture + Flow-Level Lifecycle (polish)

**Debug mode:**
```bash
tvqa run flows/tc268_proxy_swap.yaml --project projects/epic-app --proxy-log artifacts/mitmproxy.log
```

When `--proxy-log` is passed, `ProxyHarness.start()` redirects mitmproxy stdout/stderr to that file instead of `DEVNULL`.

**Flow-level `proxy` lifecycle (optional):**
```yaml
proxy:
  mode: vodswap
  env:
    EPIC_TARGET_PROXY: proxy2

steps:
  - open_app: com.epictv
  # ... rest of flow
```

If the flow has a top-level `proxy:` key, the runner starts it before step 0 and stops it in the `finally` block. This automates the current manual `proxy_start` / `proxy_stop` pattern without adding explicit steps to every flow.

---

## 4. Cases of Use (mapped to epic-app issues)

| Issue | Flow File | Mode | New Step Syntax |
|---|---|---|---|
| #255 live 403 | `tc255_live_403.yaml` | `token403` | `- proxy: {mode: token403}` |
| #257 CDN 502 | `tc257_cdn_502.yaml` | `vodswap` | `- proxy: {mode: vodswap, env: {EPIC_TARGET_PROXY: proxy1}}` |
| #268 proxy swap | `tc268_proxy_swap.yaml` | `vodswap` | `- proxy: {mode: vodswap}` |
| #269 self-heal | `tc269_self_heal.yaml` | `blackhole` | `- proxy: {mode: blackhole}` |
| #270 speed gate | `tc270_speed_gate.yaml` | `vodswap` | `- proxy: {mode: vodswap}` |
| #275 expired user | `tc275_auth_expired.yaml` | `auth_expired` | `- proxy: {mode: auth_expired}` |
| #276 / #277 revoke | `tc276_auth_revoke.yaml` | `auth_revoke` | `- proxy: {mode: auth_revoke}` |

> **Note on #276/#277:** Both issues share the same revocation scenario, so a single flow (`tc276_auth_revoke.yaml`) covers both. The default `EPIC_TARGET_SPEED_FAIL: 502` and `EPIC_BLACKHOLE_AFTER_S: 45` from the mode table are used as-is; only `#257` overrides the proxy target to `proxy1`.

---

## 5. Recommendations to Minimize Friction

### R1 — One command to rule them all
```bash
tvqa run projects/epic-app/flows/tc268_proxy_swap.yaml --project projects/epic-app
```
Should work without any prior manual `mitmdump` or `adb settings put` commands. The runner handles it.

### R2 — Fail fast with clear messages
- If `mode: vodswap` but `epic_stall` addon path doesn't exist → error at flow parse time, not at step 3.
- If mitmproxy isn't installed (`mitmdump --version` fails) → error before any adb command runs.

### R3 — Zero-config for happy path
If `project.yaml` has a complete `proxy:` section, the flow only needs:
```yaml
- proxy: {mode: vodswap}
```
No paths, no env dicts, no port numbers.

### R4 — Reuse existing hygiene contract
`tvqa hygiene clean` already clears proxy keys. It should also kill any `mitmdump` process started by tvqa (track PID in `artifacts/` or `/tmp/tvqa-*.pid`).

### R5 — Keep the JSON contract
Every new command returns ONE line of JSON. No multi-line dumps, no raw mitmproxy output.

### R6 — Auth addons are project config, not core code
The auth addons (`auth_expired`, `auth_revoke`) are specific to the EpicTV QA backend. They live in the epic-app project directory, and their modes are declared in `project.yaml` under `proxy.modes`. tvqa core only resolves `addons.<name>` paths and applies `modes.<mode>` env defaults; it does not hardcode EpicTV-specific semantics.

---

## 6. Implementation Checklist

### Phase 1 (this session)
- [ ] Add `addons` and `modes` dict parsing to `_Ctx.__init__` in `runner.py`
- [ ] Add `proxy` step handler in `_exec_step` with mode → env resolution from `project.yaml`
- [ ] Update `projects/epic-app/project.yaml` with `addons` + `modes` sections
- [ ] Update one flow (e.g., `tc268_proxy_swap.yaml`) to use new syntax
- [ ] Test: `pytest` still passing (baseline: 38/38 as of this writing)
- [ ] Update `AGENTS.md` with new `proxy` step examples

### Phase 2 (next session)
- [ ] Add `tvqa proxy check` CLI command
- [ ] Add `proxy_assert` runner step
- [ ] Add `--project` flag to `tvqa hygiene check` for addon validation
- [ ] Update `projects/epic-app/README.md` with proxy section

### Phase 3 (when needed)
- [ ] Add `--proxy-log` flag to `tvqa run`
- [ ] Add top-level `proxy:` key support in flow YAML
- [ ] PID tracking for `hygiene clean` to kill mitmdump

---

## 7. Non-Goals (out of scope)

- **Do not** reimplement `epic_stall_test.py` in Python inside tvqa. It belongs to the epic-app repo.
- **Do not** add a web UI or interactive proxy inspector. tvqa is text-first.
- **Do not** support iOS/tvOS. This is Android TV only.
- **Do not** change the token-budget contract. Images still go to `artifacts/`, JSON still one line.

---

## 8. Success Criteria

1. An agent can run `tvqa run flows/tc268_proxy_swap.yaml --project projects/epic-app` and get a `passed: true/false` JSON in one round trip.
2. No manual `mitmdump` invocation is required for any of the 7 per-issue flows.
3. `tvqa hygiene clean` leaves zero mitmproxy processes and zero proxy keys.
4. A new mode can be added by adding one entry to `proxy.modes` in `project.yaml` (no tvqa core changes required).
