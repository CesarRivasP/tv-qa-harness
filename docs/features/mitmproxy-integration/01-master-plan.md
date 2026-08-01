# Master Plan — Mitmproxy Integration

> **Objetivo:** Make network-fault E2E testing as simple as `tvqa run flows/tc268_proxy_swap.yaml --project projects/epic-app`.

- **Estado:** proposed
- **Fecha:** 2026-07-31
- **Owner técnico:** tvqa maintainer
- **Owner externo:** epic-app qa team
- **Documentos relacionados:**
  - `02-implementation-and-e2e.md` — plan de implementación + pruebas E2E
  - `03-stakeholder-requirements.md` — requerimientos para epic-app qa team

> Todo dato compartido de este doc proviene de `_facts.yml`. No editar números/nombres aquí a mano — cambiarlos en el registry y correr `sync`.

---

## Changelog

### 2026-07-31 — v1: initial spec after audit of single-file plan

---

## 1. Problema

Hoy correr un flow de red-fault requiere conocimiento manual de rutas absolutas, combinaciones de env vars, y setup previo de mitmproxy. Los gaps concretos son:

| ID | Gap | Impacto |
|---|---|---|
| G1 | Addon path friction — `proxy_start` exige path absoluto al `.py` del addon. | Flujos se rompen si el repo se mueve. |
| G2 | No mode presets — los 6 modos (`token403`, `blackhole`, `origin403`, `vodswap`, `auth_expired`, `auth_revoke`) son combinaciones de env vars que el autor debe recordar. | Errores de configuración, copy-paste de env dicts. |
| G3 | No proxy health check — si mitmproxy no está corriendo o el device no tiene proxy seteado, el flow falla con timeout genérico de estado (30s). | Debug lento, tokens quemados en esperas innecesarias. |
| G4 | No integration con epic-app preflight — `preflight.sh` y `cleanup.sh` del repo epic-app duplican lógica de `tvqa hygiene`. | Doble mantenimiento, posible drift. |
| G5 | Auth addons no descubribles — `auth_expired_user_test.py` y `auth_refresh_revoke_test.py` no tienen path estable ni registry. | No se pueden referenciar desde flows. |
| G6 | No log capture — mitmproxy stdout/stderr va a `DEVNULL`; cuando un flow falla, no hay artefacto de red. | Imposible diagnosticar fallos de addon. |

Además, el token-budget contract de tvqa prohíbe nuevos round-trips por paso. Cualquier solución debe mantener: **un comando → una línea JSON**.

---

## 2. Solución elegida

Introducir un **registry de addons y presets de modo** en `project.yaml`, más un nuevo step `proxy` que resuelva `mode → addon + env` automáticamente.

**Por qué no hardcodear la tabla de modos en tvqa core:**
- Los addons (`epic_stall_test.py`, `auth_*`) viven en el repo de epic-app; sus semánticas (env vars, valores por defecto) son del dominio de EpicTV, no del framework tvqa.
- Hardcodearlos en `tvqa/proxy.py` acoplaría el core a un proyecto concreto, violando el principio de que tvqa es genérico.

**Por qué no un UI web o inspector interactivo:**
- tvqa es text-first. Un UI quemaría tokens y rompería el contrato actual.

**Por qué no reimplementar los addons en tvqa:**
- Los addons son scripts de mitmproxy con lógica de negocio de red; mantenerlos en epic-app permite que el equipo de QA los evolucione sin tocar tvqa.

---

## 3. Arquitectura

### 3.1 Componentes que cambian

| Componente | Cambio | Fase |
|---|---|---|
| `runner.py` | Parsea `proxy.addons` y `proxy.modes` de `project.yaml`. Nuevo handler `proxy` en `_exec_step`. | 1 |
| `tvqa/proxy.py` | Resuelve `mode` a `addon` + `env` leyendo `project.yaml`; ya no hardcodea tabla. | 1 |
| `project.yaml` | Nuevas claves `proxy.addons` (paths relativos a project root) y `proxy.modes` (presets). | 1 |
| Flow YAMLs (`tc255`–`tc276`) | Reemplazan `proxy_start` inline por step `proxy: {mode: X}`. | 1 |
| `tvqa/hygiene.py` | Opcionalmente valida `proxy.addons` cuando recibe `--project`. Mantiene kill de mitmdump por PID. | 2 |
| `tvqa/cli.py` | Nuevo subcomando `proxy check`. | 2 |
| `runner.py` | Nuevo step `proxy_assert`. Soporte para top-level `proxy:` key en flow (lifecycle implícito). | 2–3 |

### 3.2 Estrategia de rollout

1. **Phase 1 (inmediata):** registry + modo presets. Todavía se usa `proxy_stop` explícito en flows. `pytest` baseline 38/38 passing debe seguir verde.
2. **Phase 2 (siguiente sesión):** health checks (`proxy check`, `proxy_assert`) + integración con hygiene.
3. **Phase 3 (cuando se necesite):** log capture (`--proxy-log`) + lifecycle implícito vía top-level `proxy:` en flow YAML.

### 3.3 Coordinación crítica

- **No romper backward compatibility:** `proxy_start` / `proxy_stop` existentes siguen funcionando. `proxy` es azúcar sintáctico.
- **Token-budget contract:** todos los nuevos comandos (`tvqa proxy check`, `tvqa run` con proxy) retornan **una línea JSON**. Nunca multi-line dumps.
- **Rutas relativas:** los paths en `proxy.addons` son relativos al **project root** (el directorio pasado a `--project`), no al cwd ni a `project.yaml`.

---

## 4. Especificación de datos

### 4.1 `project.yaml` — proxy section (nuevo schema)

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

### 4.2 Nuevo step `proxy` (flow YAML)

```yaml
- proxy:
    mode: vodswap          # alias → resuelve addon + default env desde project.yaml
    env:                   # overrides opcionales
      EPIC_TARGET_PROXY: proxy2
```

> El step `proxy` **inicia** el proxy. No lo detiene. Usar `proxy_stop` explícito al final del flow, o el top-level `proxy:` key de Phase 3.

### 4.3 `tvqa proxy check` — respuesta JSON

```json
{
  "mitmproxy_installed": true,
  "mitmproxy_running": false,
  "device_proxy_set": false,
  "addons_found": {
    "epic_stall": true,
    "auth_expired": false
  }
}
```

> Debe coincidir field-for-field con `contracts.proxy_check_response` en `_facts.yml`.

---

## 5. Seguridad

- **Sin credenciales hardcodeadas:** los flows usan `$TVQA_USERNAME` y `$TVQA_PASSWORD` (ya existentes). Los addons de mitmproxy no reciben credenciales; manipulan tráfico de red basado en env vars de comportamiento (`EPIC_MODE`, etc.).
- **No nuevas superficies de ataque:** el registry solo declara paths de archivos `.py` existentes; no ejecuta código arbitrario ni acepta URLs remotas.
- **Aislamiento de projectos:** cada `--project` carga su propio `project.yaml`; un modo mal configurado en un proyecto no afecta a otro.

---

## 6. Costo y escalabilidad

- **Costo computacional:** mitmproxy corre como proceso hijo local; no hay servicio persistente ni infra adicional.
- **Costo de tokens:** la solución no añade round-trips LLM. `tvqa run <flow>` sigue siendo **un comando → una línea JSON**.
- **Escalabilidad:** añadir un nuevo modo de red-fault = una entrada en `proxy.modes` de `project.yaml`. Cero cambios en tvqa core.

---

## 7. Checklist maestro

### Phase 1 — Registry + Mode Presets
- [ ] `runner.py`: parsea `proxy.addons` y `proxy.modes` en `_Ctx.__init__`.
- [ ] `runner.py`: handler `proxy` en `_exec_step` resuelve mode → addon + env.
- [ ] `tvqa/proxy.py`: elimina tabla hardcodeada; lee modes desde `project.yaml`.
- [ ] `projects/epic-app/project.yaml`: añade secciones `addons` + `modes`.
- [ ] Actualizar al menos un flow (ej. `tc268_proxy_swap.yaml`) al nuevo syntax.
- [ ] `pytest` baseline verde: 38/38 passing.
- [ ] `AGENTS.md`: documenta el nuevo step `proxy`.

### Phase 2 — Health Checks + Preflight
- [ ] `tvqa proxy check` CLI subcomando implementado.
- [ ] `proxy_assert` step handler en `runner.py`.
- [ ] `tvqa hygiene check --project <dir>` valida addon paths.
- [ ] `projects/epic-app/README.md`: sección de proxy.

### Phase 3 — Log Capture + Lifecycle
- [ ] Flag `--proxy-log` en `tvqa run`.
- [ ] Soporte para top-level `proxy:` key en flow YAML (start en step 0, stop en finally).
- [ ] PID tracking para `hygiene clean` (`/tmp/tvqa-*.pid`).

---

## 8. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Se mueven los archivos `.py` de addons en epic-app | Media | Alto | Usar paths relativos al project root; epic-app QA team es responsable de estabilidad de rutas (ver `03-stakeholder-requirements.md` §3). |
| mitmproxy no instalado en la máquina del agente | Baja | Alto | `tvqa proxy check` detecta antes de correr flow; `proxy_assert` fail-fast. |
| Break de backward compatibility en `proxy_start` | Baja | Alto | `proxy_start` / `proxy_stop` se mantienen sin cambios de interfaz. |
| Aumento de tiempo de ejecución por startup de mitmproxy | Baja | Medio | mitmproxy arranca en ~1s; no afecta el token-budget porque sigue siendo un solo comando. |
| Confusión sobre quién mantiene la tabla de modos | Media | Medio | Documentado en `03-stakeholder-requirements.md`: modes viven en `project.yaml`, no en tvqa core. |
