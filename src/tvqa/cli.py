"""tvqa CLI entry point. Every subcommand prints compact JSON or a one-line
result — never a raw image, never a log dump — so an LLM agent driving this
tool spends minimal tokens per verification step. `tvqa run` (Task 12) is the
preferred entry point for e2e; these commands are the single-step primitives.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import click

from tvqa.adb import Adb
from tvqa.device import AgentDevice
from tvqa.states import StateRegistry
from tvqa.logwait import wait_for_line, LogWaitTimeout
from tvqa.wait import poll_until, state_check_fn
from tvqa import hygiene as _hygiene
from tvqa.runner import run_flow


@click.group()
def main():
    """Text-first QA driver for RN TV apps."""


@main.command()
def devices():
    """List attached adb devices."""
    for serial in Adb().devices():
        click.echo(serial)


@main.command()
@click.option("--serial", default=None)
@click.argument("code")
def tap(serial, code):
    """Send a single keyevent (23 or DPAD_CENTER)."""
    Adb(serial=serial).keyevent(code)
    click.echo(json.dumps({"ok": True, "keyevent": code}))


@main.command()
def snapshot():
    """Print the current accessibility snapshot. For calibrating states.yaml by
    hand — NOT for routine agent verification (use `state check` instead)."""
    click.echo(AgentDevice().snapshot())


def _check_one(registry, state_name, serial, tmp) -> "StateResult":
    method = registry.method_of(state_name)
    if method == "a11y":
        return registry.check(state_name, snapshot_text=AgentDevice().snapshot())
    shot_path = Path(tmp) / "shot.png"
    Adb(serial=serial).screenshot(shot_path)
    return registry.check(state_name, screenshot_path=shot_path)


@main.group()
def state():
    """Screen-state verification commands."""


@state.command("check")
@click.option("--states-file", required=True, type=click.Path(exists=True))
@click.option("--state", "state_name", required=True)
@click.option("--serial", default=None)
def state_check(states_file, state_name, serial):
    """Capture once and check against ONE named state. Prints JSON."""
    registry = StateRegistry.load(Path(states_file))
    with tempfile.TemporaryDirectory() as tmp:
        result = _check_one(registry, state_name, serial, tmp)
    click.echo(
        json.dumps({"state": result.state, "matched": result.matched, "detail": result.detail})
    )


@state.command("which")
@click.option("--states-file", required=True, type=click.Path(exists=True))
@click.option("--serial", default=None)
def state_which(states_file, serial):
    """Answer 'which known screen am I on?' — one snapshot + one screenshot max,
    reused across all states. Prints JSON with the list of matched state names.
    """
    registry = StateRegistry.load(Path(states_file))
    methods = {registry.method_of(n) for n in registry.names()}
    snapshot_text = AgentDevice().snapshot() if "a11y" in methods else None
    with tempfile.TemporaryDirectory() as tmp:
        shot_path = None
        if methods & {"ocr", "phash"}:
            shot_path = Path(tmp) / "shot.png"
            Adb(serial=serial).screenshot(shot_path)
        results = registry.check_all(screenshot_path=shot_path, snapshot_text=snapshot_text)
    matched = [r.state for r in results if r.matched]
    click.echo(json.dumps({"matched": matched}))


@state.command("wait")
@click.option("--states-file", required=True, type=click.Path(exists=True))
@click.option("--state", "state_name", required=True)
@click.option("--timeout", "timeout_s", default=30.0, type=float)
@click.option("--serial", default=None)
def state_wait(states_file, state_name, timeout_s, serial):
    """Block (server-side) until STATE matches; print ONE JSON line."""
    registry = StateRegistry.load(Path(states_file))
    with tempfile.TemporaryDirectory() as tmp:
        check = state_check_fn(
            registry, state_name,
            adb=Adb(serial=serial), device=AgentDevice(), work_dir=Path(tmp),
        )
        matched = poll_until(check, timeout_s=timeout_s)
    click.echo(json.dumps({"state": state_name, "matched": matched, "timeout_s": timeout_s}))


@main.command("log-wait")
@click.argument("pattern")
@click.option("--timeout", "timeout_s", default=30.0, type=float)
@click.option("--serial", default=None)
def log_wait(pattern, timeout_s, serial):
    """Block until PATTERN appears in logcat; print the matched line as JSON."""
    try:
        result = wait_for_line(pattern, timeout_s, serial=serial)
        click.echo(json.dumps({"matched": True, "line": result.line, "elapsed_s": result.elapsed_s}))
    except LogWaitTimeout:
        click.echo(json.dumps({"matched": False, "line": None, "timeout_s": timeout_s}))


def _resolve_serial(serial):
    if serial:
        return serial
    found = Adb().devices()
    if not found:
        raise click.ClickException("no adb devices attached")
    return found[0]


@main.group()
def hygiene():
    """Device-state hygiene: detect/clear leftover proxy + wm overrides."""


@hygiene.command("check")
@click.option("--serial", default=None)
def hygiene_check(serial):
    """Report leftover proxy/wm overrides from a prior run. Prints JSON; exits 1 if dirty."""
    report = _hygiene.check(_resolve_serial(serial))
    click.echo(json.dumps({"clean": report.clean, "issues": report.issues}))
    if not report.clean:
        raise SystemExit(1)


@hygiene.command("clean")
@click.option("--serial", default=None)
def hygiene_clean(serial):
    """Reset proxy keys + wm size/density, then re-check. Prints JSON."""
    report = _hygiene.clean(_resolve_serial(serial))
    click.echo(json.dumps({"clean": report.clean, "issues": report.issues}))


@main.command("run")
@click.argument("flow_file", type=click.Path(exists=True))
@click.option("--project", "project_dir", required=True, type=click.Path(exists=True))
@click.option("--serial", default=None)
def run(flow_file, project_dir, serial):
    """Execute a flow.yaml locally; print ONE JSON summary line. The preferred
    entry point for e2e — one agent round trip per flow, not per step."""
    result = run_flow(Path(flow_file), project_dir=Path(project_dir), serial=serial)
    click.echo(json.dumps({
        "flow": result.flow,
        "passed": result.passed,
        "steps": result.steps_total,
        "failed_step": result.failed_step,
        "detail": result.detail,
        "evidence": result.evidence,
        "duration_s": result.duration_s,
    }))
    if not result.passed:
        raise SystemExit(1)
