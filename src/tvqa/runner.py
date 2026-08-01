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

from tvqa.adb import Adb
from tvqa.device import AgentDevice
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


class _Ctx:
    def __init__(self, project_dir: Path, serial: str | None):
        self.project_dir = project_dir
        self.serial = serial
        self.registry = StateRegistry.load(project_dir / "states.yaml")
        # project.yaml is optional; when present it supplies proxy host/port and a
        # serial hint so those aren't hardcoded here.
        project_yaml = project_dir / "project.yaml"
        cfg = yaml.safe_load(project_yaml.read_text()) if project_yaml.exists() else {}
        cfg = cfg or {}
        proxy_cfg = cfg.get("proxy", {})
        self.adb = Adb(serial=serial)
        self.device = AgentDevice(platform="android")
        self.proxy = ProxyHarness(
            serial=serial or cfg.get("serial_hint", "emulator-5554"),
            host_ip=proxy_cfg.get("host_ip", "10.0.2.2"),
            port=proxy_cfg.get("port", 8080),
        )
        self.addons: dict[str, str] = proxy_cfg.get("addons", {})
        self.work_dir = project_dir / "artifacts"
        self.work_dir.mkdir(exist_ok=True)


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
    elif "wait_log" in step:
        try:
            wait_for_line(step["wait_log"], float(step.get("timeout", 30)), serial=ctx.serial)
        except LogWaitTimeout as e:
            raise StepFailed(str(e))
    elif "assert_state" in step:
        name = step["assert_state"]
        check = state_check_fn(ctx.registry, name, adb=ctx.adb, device=ctx.device, work_dir=ctx.work_dir)
        if not check():
            raise StepFailed(f"assert_state {name!r} did not match")
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
    )
