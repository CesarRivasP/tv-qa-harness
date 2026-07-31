import json
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from tvqa.runner import run_flow, FlowResult


def _write_flow(tmp_path, flow):
    path = tmp_path / "flow.yaml"
    path.write_text(yaml.safe_dump(flow))
    return path


def _project(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "states.yaml").write_text(yaml.safe_dump({
        "states": {"home": {"method": "a11y", "expected_text": "Home"}}
    }))
    return proj


def test_run_flow_passes_and_returns_summary(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "login",
        "steps": [
            {"keyevent": "DPAD_CENTER"},
            {"wait_state": "home", "timeout": 5},
            {"assert_state": "home"},
        ],
    })
    with patch("tvqa.runner.Adb"), patch("tvqa.runner.AgentDevice") as dev_cls, \
         patch("tvqa.runner.ProxyHarness"):
        # state_check_fn receives ctx.device (tvqa.runner.AgentDevice) by injection now,
        # so one runner-namespace mock covers the a11y snapshot for wait_state/assert_state.
        dev_cls.return_value.snapshot.return_value = '@e1 [heading] "Home"'
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert isinstance(result, FlowResult)
    assert result.passed is True
    assert result.steps_total == 3
    assert result.failed_step is None
    assert result.evidence is None


def test_run_flow_fails_saves_evidence_path_and_stops(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "login",
        "steps": [
            {"assert_state": "home"},
            {"keyevent": "DPAD_CENTER"},  # must NOT execute after the failure
        ],
    })
    with patch("tvqa.runner.Adb") as adb_cls, patch("tvqa.runner.AgentDevice") as dev_cls, \
         patch("tvqa.runner.ProxyHarness"):
        dev_cls.return_value.snapshot.return_value = '@e1 [heading] "Login"'  # no "Home"
        adb_cls.return_value.screenshot.side_effect = lambda p: Path(p).write_bytes(b"\x89PNG")
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is False
    assert result.failed_step == 0
    assert "home" in result.detail
    assert result.evidence is not None and result.evidence.endswith(".png")
    assert Path(result.evidence).exists()
    adb_cls.return_value.keyevent.assert_not_called()


def test_run_flow_backend_error_returns_json_not_raise(tmp_path):
    # A crashing adb/agent-device call must be absorbed into a FlowResult, never
    # propagate a traceback out of run_flow (token-budget rule 2).
    flow_path = _write_flow(tmp_path, {
        "name": "boom",
        "steps": [{"keyevent": "DPAD_CENTER"}],
    })
    with patch("tvqa.runner.Adb") as adb_cls, patch("tvqa.runner.AgentDevice"), \
         patch("tvqa.runner.ProxyHarness"):
        adb_cls.return_value.keyevent.side_effect = RuntimeError("adb died")
        adb_cls.return_value.screenshot.side_effect = RuntimeError("no device")  # evidence fails too
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is False
    assert result.failed_step == 0
    assert "adb died" in result.detail
    assert result.evidence is None


def test_run_flow_proxy_steps_start_and_stop(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "fault",
        "steps": [
            {"proxy_start": {"addon": "stall.py", "env": {"EPIC_MODE": "origin403"}}},
            {"proxy_stop": {}},
        ],
    })
    with patch("tvqa.runner.Adb"), patch("tvqa.runner.AgentDevice"), \
         patch("tvqa.runner.ProxyHarness") as proxy_cls:
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is True
    proxy_cls.return_value.start.assert_called_once()
    # stop is called once by proxy_stop step + possibly once in finally if _proc still set.
    # With the real implementation stop() clears _proc so finally skips it; mock doesn't.
    assert proxy_cls.return_value.stop.call_count >= 1


def test_cli_run_prints_one_json_line(tmp_path):
    from click.testing import CliRunner
    from tvqa.cli import main

    flow_path = _write_flow(tmp_path, {"name": "f", "steps": [{"sleep": 0.01}]})
    runner = CliRunner()
    result = runner.invoke(main, ["run", str(flow_path), "--project", str(_project(tmp_path))])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload["passed"] is True
    assert payload["flow"] == "f"
