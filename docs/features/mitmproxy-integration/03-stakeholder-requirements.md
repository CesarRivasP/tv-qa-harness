# Requerimientos para epic-app qa team — Mitmproxy Integration

> Documento para el owner externo. Lista lo que necesitamos que implemente/valide de su lado para completar la solución.

- **Fecha:** 2026-07-31
- **Contexto completo:** `01-master-plan.md`
- **Alcance:** runner.py, tvqa/proxy.py, tvqa/hygiene.py, project.yaml schema, flow YAML syntax, AGENTS.md

> Datos compartidos vienen de `_facts.yml`. Contratos deben coincidir con doc 01 §4 y doc 02 Parte B.

---

## Changelog

### 2026-07-31 — v1: initial spec after audit of single-file plan

---

## 1. Idea en una frase

tvqa va a lanzar vuestros addons de mitmproxy (`epic_stall_test.py`, `auth_expired_user_test.py`, `auth_refresh_revoke_test.py`) **por nombre de modo**, sin que el agente necesite saber rutas absolutas ni combinaciones de env vars.

---

## 2. Lo que nosotros ponemos (nuestro lado)

- **tvqa core:** parser de `proxy.addons` y `proxy.modes` en `project.yaml`; resolución de `mode → addon + env`.
- **Nuevo step `proxy`:** azúcar sintáctico para `proxy_start` con modo preset.
- **Health checks:** `tvqa proxy check` y `proxy_assert` para fallar rápido si mitmproxy no está listo.
- **Log capture (Phase 3):** opción `--proxy-log` para depurar fallos de addon.

---

## 3. Lo que necesitamos que hagas

1. **Mantener rutas estables de addons.** Los paths en `project.yaml` son relativos al root del proyecto. Si movéis `epic_stall_test.py` a otra carpeta, actualizad `proxy.addons.epic_stall` en `project.yaml`.

2. **No cambiar la interfaz de env vars sin avisar.** tvqa inyecta las variables definidas en `proxy.modes.<mode>.env` al lanzar `mitmdump`. Si renombráis `EPIC_MODE` a `EPIC_FAULT_MODE` en el addon, el preset `token403` dejará de funcionar. Coordinad cambios de interfaz con el tvqa maintainer.

3. **Añadir nuevos modos en `project.yaml`, no en tvqa core.** Si creáis un nuevo modo de fault (ej. `rate_limit`), añadidlo a `proxy.modes` en `project.yaml`. No se requieren cambios en `tvqa/proxy.py`.

4. **Validar que los addons funcionan standalone.** Correr `mitmdump -s epic_stall_test.py` con las env vars del modo debe comportarse como esperáis. tvqa no debuguea lógica interna de los addons.

---

## 4. Payload / interfaz que vas a recibir (referencia)

Cuando tvqa lanza mitmproxy con un modo, el entorno del proceso hijo contiene las variables del preset. Ejemplo para `vodswap`:

```bash
EPIC_MODE=vodswap
EPIC_TARGET_PROXY=proxy2
EPIC_TARGET_SPEED_FAIL=502
```

Vuestros addons deben leer estas variables y actuar en consecuencia. tvqa no filtra ni transforma los valores.

---

## 5. Checklist para ti (owner externo)

- [ ] Confirmar que las rutas en `proxy.addons` apuntan a archivos existentes en el repo epic-app.
- [ ] Confirmar que cada modo en `proxy.modes` tiene las env vars que el addon espera.
- [ ] Ejecutar `mitmdump -s <addon_path>` manualmente con las env vars de cada modo; verificar que el addon no crashea.
- [ ] Revisar que los flows de red-fault (`tc255`–`tc276`) usan el nuevo step `proxy` y no paths absolutos inline.
- [ ] Si se añade un nuevo addon de auth/red-fault, crear PR que actualice `project.yaml` (no tvqa core).

---

## 6. Cómo lo probamos juntos

### E2E coordinado (mirror de doc 02 Parte C)

1. **Setup:** epic-app QA team asegura que `project.yaml` tiene `addons` y `modes` correctos.
2. **Ejecución:** tvqa maintainer corre `tvqa run flows/tc268_proxy_swap.yaml --project projects/epic-app`.
3. **Verificación:** resultado JSON `passed: true`. Si `passed: false`, revisar juntos:
   - ¿El addon path existe? (`tvqa proxy check`)
   - ¿Las env vars del modo coinciden con lo que el addon lee?
   - ¿Hay logs de mitmproxy? (`--proxy-log artifacts/mitmproxy.log`)

---

## 7. Preguntas para cerrar

1. ¿Las rutas actuales de los addons (`variants/epic-app/docs/...`) son estables, o hay plan de moverlas?
2. ¿Hay más addons de red-fault en desarrollo que deberían entrar en el registry ahora?
3. ¿El equipo epic-app QA prefiere que tvqa mate mitmproxy automáticamente en `finally` (top-level `proxy:` key de Phase 3), o preferís control explícito con `proxy_stop`?

---

## Anexo A — Ejemplo de `project.yaml` completo (referencia)

```yaml
package: com.epictv
app_name: EpicTV
serial_hint: emulator-5554
expected_resolution: "1920x1080"
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

> Copiar de `_facts.yml` (`addon_paths` + `modes`) sin modificar valores.
