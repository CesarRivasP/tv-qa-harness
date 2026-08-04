"""Declarative e2e flow runner. Executes flow.yaml steps locally — actions,
server-side waits, assertions, proxy fault injection — and returns ONE compact
summary. The whole point: an LLM agent spends ~60 tokens on an entire flow
instead of one round trip per step. On failure it saves a screenshot to
<project>/artifacts/ and reports only the PATH.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from tvqa.adb import Adb, resolve_serial, lan_ip
from tvqa.device import AgentDevice, AgentDeviceError
from tvqa.logwait import wait_for_line, LogWaitTimeout
from tvqa.proxy import ProxyHarness, resolve_mode
from tvqa.states import StateRegistry
from tvqa.wait import poll_until, state_check_fn


class StepFailed(RuntimeError):
    pass


@dataclass
class FlowResult:
    flow: str
    passed: bool
    steps_total: int
    failed_step: int | None
    detail: str
    evidence: str | None
    duration_s: float
    log_line: str | None = None
    log_elapsed_s: float | None = None


class _Ctx:
    def __init__(self, project_dir: Path, serial: str | None):
        self.project_dir = project_dir
        self.registry = StateRegistry.load(project_dir / "states.yaml")
        # project.yaml is optional; when present it supplies proxy host/port and a
        # serial hint so those aren't hardcoded here.
        project_yaml = project_dir / "project.yaml"
        cfg = yaml.safe_load(project_yaml.read_text()) if project_yaml.exists() else {}
        cfg = cfg or {}
        proxy_cfg = cfg.get("proxy", {})
        # Autodetect over hardcoding: whichever single device is attached wins,
        # so switching between emulator and physical needs zero project.yaml
        # edits. serial_hint is only a last resort when 0 or 2+ are attached.
        resolved_serial = resolve_serial(serial, cfg.get("serial_hint", "emulator-5554"))
        self.serial = resolved_serial
        self.adb = Adb(serial=resolved_serial)
        # Target agent-device at the same physical device adb/proxy use. Without an
        # explicit --device, agent-device follows its stale default-session binding
        # (typically emulator-5554) and every a11y snapshot/open hits the wrong device.
        # agent-device selects by friendly NAME, not the adb serial — separate key,
        # only needed when 2+ devices are registered with agent-device; None is
        # fine (auto-picks) for the common single-target case. Env var lets you
        # pin a name for a physical run without touching project.yaml.
        self.device = AgentDevice(
            platform="android",
            device=cfg.get("agent_device_name") or os.environ.get("TVQA_DEVICE_NAME"),
            session=cfg.get("agent_device_session") or os.environ.get("TVQA_DEVICE_SESSION", "tvqa"),
        )
        # host_ip: explicit project.yaml value wins; otherwise derive from the
        # resolved serial. "10.0.2.2" only resolves inside the emulator's QEMU
        # NAT — a physical device needs this machine's real LAN IP instead,
        # which changes across networks/DHCP, so we read it live rather than
        # hardcode a snapshot that goes stale the next time you switch WiFi.
        host_ip = proxy_cfg.get("host_ip") or (
            "10.0.2.2" if resolved_serial.startswith("emulator-") else lan_ip()
        )
        self.proxy = ProxyHarness(
            serial=resolved_serial,
            host_ip=host_ip,
            port=proxy_cfg.get("port", 8080),
        )
        self.addons: dict[str, str] = proxy_cfg.get("addons", {})
        self.work_dir = project_dir / "artifacts"
        self.work_dir.mkdir(exist_ok=True)
        self.last_log_line: str | None = None
        self.last_log_elapsed_s: float | None = None


def _exec_step(step: dict, ctx: _Ctx) -> None:
    if "open_app" in step:
        ctx.device.open_app(step["open_app"])
    elif "keyevent" in step:
        ctx.adb.keyevent(step["keyevent"])
    elif "type" in step:
        raw = str(step["type"])
        expanded = os.path.expandvars(raw)  # support $VAR or ${VAR}
        text = expanded.replace("\\", "\\\\").replace('"', '\\"').replace(" ", "%s")
        ctx.adb.shell(f'input text "{text}"')
    elif "press" in step:
        ctx.device.press(step["press"])
    elif "sleep" in step:
        time.sleep(float(step["sleep"]))
    elif "shell" in step:
        ctx.adb.shell(step["shell"])
    elif "wait_state" in step:
        name = step["wait_state"]
        timeout = float(step.get("timeout", 30))
        check = state_check_fn(ctx.registry, name, adb=ctx.adb, device=ctx.device, work_dir=ctx.work_dir)
        if not poll_until(check, timeout_s=timeout):
            raise StepFailed(f"state {name!r} not seen within {timeout}s")
    elif "nav" in step:
        spec = step["nav"]
        key = spec["key"]
        until_state = spec.get("until_state")
        max_retries = int(spec.get("max", 10))
        settle_s = float(spec.get("settle", 1.0))
        for attempt in range(max_retries):
            ctx.adb.keyevent(key)
            if until_state is None:
                break
            time.sleep(settle_s)
            check = state_check_fn(ctx.registry, until_state, adb=ctx.adb, device=ctx.device, work_dir=ctx.work_dir)
            if check():
                break
        else:
            if until_state:
                raise StepFailed(
                    f"nav: state {until_state!r} not reached after {max_retries} {key} presses"
                )
    elif "reset" in step:
        spec = step["reset"]
        app = spec.get("app", "EpicTV")
        # agent-device `open` resolves by app NAME, but `am force-stop` needs the
        # PACKAGE. Passing the name to force-stop silently no-ops (no cold boot).
        package = spec.get("package")
        until_state = spec.get("until_state")
        timeout = float(spec.get("timeout", 30))
        dismiss_toast = spec.get("dismiss_toast", False)
        dismiss_key = spec.get("dismiss_key", "DPAD_CENTER")
        ctx.adb.shell(f"am force-stop {package or app}")
        ctx.device.open_app(app)
        if until_state:
            check = state_check_fn(ctx.registry, until_state, adb=ctx.adb, device=ctx.device, work_dir=ctx.work_dir)
            if not poll_until(check, timeout_s=timeout):
                raise StepFailed(f"reset: state {until_state!r} not seen within {timeout}s")
        if dismiss_toast:
            try:
                snap = ctx.device.snapshot()
                indicators = ("overlay", "toast", "warning", "error", "logbox", "SerializableStateInvariant")
                if any(ind in snap.lower() for ind in indicators):
                    ctx.adb.keyevent(dismiss_key)
                    time.sleep(1)
            except AgentDeviceError:
                pass
    elif "dismiss" in step:
        spec = step["dismiss"]
        indicators = spec.get("indicators", ["overlay", "toast", "warning", "error", "logbox"])
        key = spec.get("key", "DPAD_CENTER")
        settle_s = float(spec.get("settle", 0.5))
        try:
            snap = ctx.device.snapshot()
            snap_lower = snap.lower()
            found = any(ind.lower() in snap_lower for ind in indicators)
            if found:
                ctx.adb.keyevent(key)
                time.sleep(settle_s)
        except AgentDeviceError:
            pass
    elif "dismiss_rn_overlay" in step:
        # RN dev LogBox (warning/error overlay) blocks a11y interaction and
        # doesn't reliably close on DPAD_CENTER. No-op-safe when absent.
        try:
            ctx.device.dismiss_rn_overlay()
        except AgentDeviceError:
            pass
    elif "wait_log" in step:
        raw = step["wait_log"]
        if isinstance(raw, dict):
            pattern = raw["pattern"]
            timeout = float(raw.get("timeout", 30))
            clear_buffer = raw.get("clear", True)
            min_s = float(raw.get("min_s", 0.0))
        else:
            pattern = raw
            timeout = float(step.get("timeout", 30))
            clear_buffer = True
            min_s = 0.0
        try:
            result = wait_for_line(pattern, timeout, serial=ctx.serial, clear_buffer=clear_buffer, min_s=min_s)
            ctx.last_log_line = result.line
            ctx.last_log_elapsed_s = result.elapsed_s
        except LogWaitTimeout as e:
            raise StepFailed(str(e))
    elif "assert_state" in step:
        name = step["assert_state"]
        check = state_check_fn(ctx.registry, name, adb=ctx.adb, device=ctx.device, work_dir=ctx.work_dir)
        if not check():
            raise StepFailed(f"assert_state {name!r} did not match")
    elif "assert_no_log" in step:
        # Inverse of wait_log: PASS when the pattern does NOT appear within the
        # window. Used for no-loop assertions (e.g. after the breaker gives up,
        # the self-heal line must not keep firing). A match = failure.
        raw = step["assert_no_log"]
        if isinstance(raw, dict):
            pattern = raw["pattern"]
            window = float(raw.get("window", raw.get("timeout", 30)))
        else:
            pattern = raw
            window = float(step.get("timeout", 30))
        try:
            result = wait_for_line(pattern, window, serial=ctx.serial, clear_buffer=True, min_s=0.0)
        except LogWaitTimeout:
            pass  # good: forbidden line never appeared within the window
        else:
            raise StepFailed(f"assert_no_log: forbidden line appeared: {result.line!r}")
    elif "proxy" in step:
        spec = step["proxy"]
        addon_path, env = resolve_mode(spec["mode"], ctx.addons, spec.get("env"))
        ctx.proxy.start(addon_path=addon_path, env=env)
    elif "proxy_start" in step:
        spec = step["proxy_start"]
        ctx.proxy.start(addon_path=spec["addon"], env=spec.get("env", {}))
    elif "proxy_assert" in step:
        spec = step["proxy_assert"]
        timeout = float(spec.get("timeout", 5))
        # Verify mitmproxy process is alive
        if ctx.proxy._proc is None or ctx.proxy._proc.poll() is not None:
            raise StepFailed(f"proxy_assert: mitmproxy not running")
        # Verify device proxy is set
        result = ctx.adb.shell("settings get global http_proxy")
        if "null" in result or not result.strip():
            raise StepFailed(f"proxy_assert: device proxy not set (http_proxy={result.strip()})")
        # Wait up to timeout for proxy to be fully ready (best-effort)
        time.sleep(0.5)  # brief settling
    elif "proxy_stop" in step:
        ctx.proxy.stop()
    else:
        raise StepFailed(f"unknown step: {step!r}")


def run_flow(flow_path: Path, project_dir: Path, serial: str | None = None) -> FlowResult:
    flow_path, project_dir = Path(flow_path), Path(project_dir)
    flow = yaml.safe_load(flow_path.read_text())
    name = flow.get("name", flow_path.stem)
    steps = flow["steps"]
    ctx = _Ctx(project_dir, serial)

    start = time.monotonic()
    failed_step, detail, evidence = None, "ok", None
    try:
        for i, step in enumerate(steps):
            try:
                _exec_step(step, ctx)
            except StepFailed as e:
                failed_step, detail = i, str(e)
                raise
            except Exception as e:  # backend error (adb/agent-device/mitmdump)
                failed_step, detail = i, f"{type(e).__name__}: {e}"
                raise
    except Exception:
        # BOTH a StepFailed assertion AND an unexpected backend error land here, so a
        # crashing adb/agent-device/mitmdump call still returns ONE JSON line (token-budget
        # rule 2) instead of dumping a traceback into the agent's context.
        shot = ctx.work_dir / f"{name}-step{failed_step}.png"
        try:
            ctx.adb.screenshot(shot)
            evidence = str(shot)
        except Exception:
            evidence = None
    finally:
        # Never leave a dead proxy configured, even on failure (see proxy.py docstring).
        if ctx.proxy._proc is not None:
            ctx.proxy.stop()

    return FlowResult(
        flow=name,
        passed=failed_step is None,
        steps_total=len(steps),
        failed_step=failed_step,
        detail=detail,
        evidence=evidence,
        duration_s=round(time.monotonic() - start, 2),
        log_line=ctx.last_log_line,
        log_elapsed_s=ctx.last_log_elapsed_s,
    )
