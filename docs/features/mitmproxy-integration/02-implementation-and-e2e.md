# Implementación + Pruebas E2E — Mitmproxy Integration

> Complementa a `01-master-plan.md`. Pasos de código (archivo por archivo) + plan de pruebas end-to-end.

- **Fecha:** 2026-07-31
- **Baseline de tests:** 38/38 passing

> Datos compartidos vienen de `_facts.yml`. Cross-refs a `01-master-plan.md §N` deben resolver a secciones reales.

---

## Changelog

### 2026-07-31 — v1: initial spec after audit of single-file plan

---

## Parte A — Plan de implementación

### Fase 1 — Addon Registry + Mode Presets

**Archivo:** `runner.py`
- En `_Ctx.__init__`, después de cargar `project.yaml`, extraer `proxy.addons` (dict `name → path relativo`) y `proxy.modes` (dict `mode → {addon, env}`).
- Resolver paths relativos al **project root** (`--project` dir), no al cwd.
- **Verificación fase 1:** `runner.py` unit tests levantan un `project.yaml` dummy con `addons` + `modes`; `_Ctx` parsea sin error.

**Archivo:** `tvqa/proxy.py`
- Eliminar cualquier tabla hardcodeada de `mode → env`.
- `ProxyHarness.start()` acepta ahora `addon_path` (absoluto ya resuelto) y `env` (dict mergeado de `project.yaml` modes + overrides del flow).
- **Verificación fase 1:** `pytest tvqa/test_proxy.py` (o equivalente) pasa con mocks de `subprocess.Popen`.

**Archivo:** `projects/epic-app/project.yaml`
- Añadir sección `proxy.addons` y `proxy.modes` con los valores de `_facts.yml` (ver `01-master-plan.md §4.1`).
- **Verificación fase 1:** `tvqa proxy check --project projects/epic-app` (una vez implementado en Fase 2) reporta `addons_found: {epic_stall: true, ...}`.

**Archivo:** `projects/epic-app/flows/tc268_proxy_swap.yaml`
- Reemplazar bloque `proxy_start` inline por:
  ```yaml
  - proxy:
      mode: vodswap
  ```
- Asegurar que `proxy_stop` sigue presente al final del flow.
- **Verificación fase 1:** `tvqa run flows/tc268_proxy_swap.yaml --project projects/epic-app` retorna JSON de resultado (no error de parseo).

**Archivo:** `AGENTS.md`
- Añadir ejemplo del nuevo step `proxy` en la sección de steps permitidos.
- **Verificación fase 1:** diff de `AGENTS.md` revisado; no contradice whitelist de comandos device-interaction.

---

### Fase 2 — Health Checks + Preflight

**Archivo:** `tvqa/cli.py`
- Nuevo subcomando `proxy check`:
  ```python
  # tvqa/cli.py
  @cli.command()
  @click.option('--project', required=True, type=click.Path(exists=True))
  def proxy_check(project):
      ...
  ```
- Salida: una línea JSON que coincide con `contracts.proxy_check_response` de `_facts.yml`.
- **Verificación fase 2:** ejecutar `tvqa proxy check --project projects/epic-app` → JSON válido, keys correctas.

**Archivo:** `runner.py`
- Nuevo handler `proxy_assert`:
  - Si `mode` está presente, verificar que el addon exista en `project.yaml`.
  - Chequear que `mitmdump` responda (`mitmdump --version` o PID file).
  - Chequear `adb shell settings get global http_proxy` contra `host_ip:port`.
  - Timeout: 5s (fail-fast vs 30s de state wait).
- **Verificación fase 2:** flow con `proxy_assert` falla inmediatamente si mitmproxy no está corriendo, en <5s.

**Archivo:** `tvqa/hygiene.py`
- Añadir flag opcional `--project`.
- Cuando se pasa `--project`, validar que todos los `proxy.addons` paths existan en disco.
- **Verificación fase 2:** `tvqa hygiene check --project projects/epic-app` incluye campo `addons_valid` en JSON de salida.

**Archivo:** `projects/epic-app/README.md`
- Añadir sección de proxy explicando los modos disponibles y cómo añadir nuevos.
- **Verificación fase 2:** README.md contiene la tabla de modos y un ejemplo de `project.yaml`.

---

### Fase 3 — Log Capture + Flow-Level Lifecycle

**Archivo:** `tvqa/cli.py` + `runner.py`
- Flag `--proxy-log <path>` en `tvqa run`.
- Pasar path a `ProxyHarness.start()`; si existe, redirigir stdout/stderr de `mitmdump` al archivo en vez de `DEVNULL`.
- **Verificación fase 3:** correr flow con `--proxy-log artifacts/mitmproxy.log`; archivo contiene logs de mitmproxy.

**Archivo:** `runner.py`
- Soporte para top-level `proxy:` key en flow YAML:
  ```yaml
  proxy:
    mode: vodswap
    env:
      EPIC_TARGET_PROXY: proxy2

  steps:
    - open_app: com.epictv
  ```
- Lógica: en `run_flow()`, si existe top-level `proxy`, ejecutar `proxy_start` antes de step 0 y `proxy_stop` en `finally`.
- **Verificación fase 3:** flow con top-level `proxy:` no necesita step `proxy_stop` al final; `hygiene clean` mata el proceso si el flow aborta.

**Archivo:** `tvqa/hygiene.py`
- Leer `/tmp/tvqa-*.pid` (o archivo en `artifacts/`) para encontrar procesos `mitmdump` lanzados por tvqa.
- Matarlos durante `hygiene clean`.
- **Verificación fase 3:** después de `tvqa run` que crashea, `tvqa hygiene clean` deja 0 procesos `mitmdump`.

---

## Parte B — Plan de pruebas

### B.1 — Unitarias

- [ ] `test_ctx_proxy_modes`: `_Ctx` carga `proxy.modes` desde `project.yaml` y resuelve `mode: vodswap` a addon + env correctos.
- [ ] `test_ctx_addons_path_resolution`: paths relativos en `proxy.addons` se resuelven absolutos respecto al project root.
- [ ] `test_proxy_step_handler`: `_exec_step` con `proxy` step genera el comando `mitmdump` con addon y env esperados.
- [ ] `test_proxy_assert_installed`: `proxy_assert` con `mode` dado valida existencia del addon path.
- [ ] `test_proxy_assert_running`: `proxy_assert` falla si `mitmdump` no responde en 5s.
- [ ] **Baseline verde:** suite existente sigue en 38/38 passing.

### B.2 — Integración / contrato

- [ ] `tvqa proxy check --project projects/epic-app` retorna JSON que satisface `contracts.proxy_check_response`:
  - keys: `mitmproxy_installed`, `mitmproxy_running`, `device_proxy_set`, `addons_found`.
  - `addons_found` es `Dict[str, bool]`.
- [ ] `tvqa run flows/tc268_proxy_swap.yaml --project projects/epic-app` retorna JSON de 1 línea con `passed: bool`.
- [ ] `tvqa run ... --proxy-log artifacts/mitmproxy.log` crea archivo no-vacío.

---

## Parte C — Pruebas E2E (manual)

### C.1 Happy path
1. `tvqa hygiene check` → clean.
2. `tvqa run projects/epic-app/flows/tc268_proxy_swap.yaml --project projects/epic-app`.
3. Resultado esperado: JSON `{"passed": true, ...}` en una línea.

### C.2 Continuidad (back-to-back flows)
1. Correr `tc255_live_403.yaml` (mode `token403`).
2. Inmediatamente después, correr `tc268_proxy_swap.yaml` (mode `vodswap`).
3. Resultado esperado: ambos `passed: true`; `hygiene clean` entre flows no es necesaria si cada flow hace `proxy_stop`.

### C.3 Error — addon path missing
1. Renombrar `epic_stall_test.py` temporalmente.
2. `tvqa run flows/tc268_proxy_swap.yaml --project projects/epic-app`.
3. Resultado esperado: error en **parse time** (antes de adb), indicando que `epic_stall` addon no se encuentra.

### C.4 Error — mitmproxy no instalado
1. Renombrar/mover `mitmdump` del PATH.
2. `tvqa run flows/tc268_proxy_swap.yaml --project projects/epic-app`.
3. Resultado esperado: error antes de cualquier comando adb, JSON con `passed: false` y `detail: mitmproxy not installed`.

### C.5 Timeout / fail-fast
1. Correr flow que incluye step `proxy_assert: {mode: vodswap, timeout: 5}` sin haber iniciado mitmproxy.
2. Resultado esperado: falla en <5s, no espera 30s de state timeout.

---

## Criterios de aceptación (Definition of Done)

> MUST match `acceptance[]` en `_facts.yml` item-for-item.

1. An agent can run `tvqa run flows/tc268_proxy_swap.yaml --project projects/epic-app` and get a `passed: true/false` JSON in one round trip.
2. No manual `mitmdump` invocation is required for any of the 7 per-issue flows.
3. `tvqa hygiene clean` leaves zero mitmproxy processes and zero proxy keys.
4. A new mode can be added by adding one entry to `proxy.modes` in `project.yaml` (no tvqa core changes required).
