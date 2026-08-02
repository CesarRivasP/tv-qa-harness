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


def test_run_flow_proxy_step_resolves_mode(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "fault",
        "steps": [
            {"proxy": {"mode": "vodswap", "env": {"EPIC_TARGET_PROXY": "proxy1"}}},
            {"proxy_stop": {}},
        ],
    })
    with patch("tvqa.runner.Adb"), patch("tvqa.runner.AgentDevice"), \
         patch("tvqa.runner.ProxyHarness") as proxy_cls:
        # Provide an addons registry via project.yaml
        proj = _project(tmp_path)
        (proj / "project.yaml").write_text(yaml.safe_dump({
            "proxy": {
                "addons": {"epic_stall": "stall.py"}
            }
        }))
        result = run_flow(flow_path, project_dir=proj, serial="emulator-5554")

    assert result.passed is True
    proxy_cls.return_value.start.assert_called_once()
    call_kwargs = proxy_cls.return_value.start.call_args[1]
    assert call_kwargs["addon_path"] == "stall.py"
    assert call_kwargs["env"]["EPIC_MODE"] == "vodswap"
    assert call_kwargs["env"]["EPIC_TARGET_PROXY"] == "proxy1"


def test_run_flow_proxy_step_unknown_mode_fails_fast(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "badmode",
        "steps": [{"proxy": {"mode": "nosuchmode"}}],
    })
    with patch("tvqa.runner.Adb"), patch("tvqa.runner.AgentDevice"), \
         patch("tvqa.runner.ProxyHarness"):
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is False
    assert result.failed_step == 0
    assert "Unknown proxy mode" in result.detail


def test_run_flow_proxy_step_missing_addon_fails_fast(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "nomissing",
        "steps": [{"proxy": {"mode": "token403"}}],
    })
    with patch("tvqa.runner.Adb"), patch("tvqa.runner.AgentDevice"), \
         patch("tvqa.runner.ProxyHarness"):
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is False
    assert result.failed_step == 0
    assert "missing from project.yaml" in result.detail


def test_run_flow_proxy_assert_passes_when_proxy_active(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "assert",
        "steps": [
            {"proxy": {"mode": "token403"}},
            {"proxy_assert": {"timeout": 1}},
            {"proxy_stop": {}},
        ],
    })
    with patch("tvqa.runner.Adb") as adb_cls, patch("tvqa.runner.AgentDevice"), \
         patch("tvqa.runner.ProxyHarness") as proxy_cls:
        proj = _project(tmp_path)
        (proj / "project.yaml").write_text(yaml.safe_dump({
            "proxy": {"addons": {"epic_stall": "stall.py"}}
        }))
        proxy_cls.return_value._proc = type("P", (), {"poll": lambda *a, **k: None})()  # running
        adb_cls.return_value.shell.return_value = "10.0.2.2:8080"
        result = run_flow(flow_path, project_dir=proj, serial="emulator-5554")

    assert result.passed is True


def test_run_flow_proxy_assert_fails_when_proxy_dead(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "assertdead",
        "steps": [
            {"proxy_assert": {"timeout": 1}},
        ],
    })
    with patch("tvqa.runner.Adb"), patch("tvqa.runner.AgentDevice"), \
         patch("tvqa.runner.ProxyHarness") as proxy_cls:
        proxy_cls.return_value._proc = None  # not running
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is False
    assert result.failed_step == 0
    assert "mitmproxy not running" in result.detail


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


def test_run_flow_nav_reaches_state(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "navtest",
        "steps": [
            {"nav": {"key": "DPAD_DOWN", "until_state": "home", "max": 3, "settle": 0.1}},
        ],
    })
    with patch("tvqa.runner.Adb") as adb_cls, patch("tvqa.runner.AgentDevice") as dev_cls, \
         patch("tvqa.runner.ProxyHarness"):
        # First two snapshots don't match, third does
        calls = [
            '@e1 [button] "Back"',
            '@e2 [button] "Menu"',
            '@e3 [heading] "Home"',
        ]
        dev_cls.return_value.snapshot.side_effect = calls
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is True
    assert adb_cls.return_value.keyevent.call_count == 3  # 3 retries until match


def test_run_flow_nav_fails_when_state_not_reached(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "navfail",
        "steps": [
            {"nav": {"key": "DPAD_DOWN", "until_state": "home", "max": 2, "settle": 0.1}},
        ],
    })
    with patch("tvqa.runner.Adb") as adb_cls, patch("tvqa.runner.AgentDevice") as dev_cls, \
         patch("tvqa.runner.ProxyHarness"):
        dev_cls.return_value.snapshot.return_value = '@e1 [button] "Other"'
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is False
    assert result.failed_step == 0
    assert "not reached after 2" in result.detail
    assert adb_cls.return_value.keyevent.call_count == 2


def test_run_flow_reset_reaches_state(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "resettest",
        "steps": [
            {"reset": {"app": "EpicTV", "until_state": "home", "timeout": 5}},
        ],
    })
    with patch("tvqa.runner.Adb") as adb_cls, patch("tvqa.runner.AgentDevice") as dev_cls, \
         patch("tvqa.runner.ProxyHarness"):
        dev_cls.return_value.snapshot.return_value = '@e1 [heading] "Home"'
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is True
    adb_cls.return_value.shell.assert_called_once_with("am force-stop EpicTV")
    adb_cls.return_value.keyevent.assert_not_called()  # no dismiss because no overlay


def test_run_flow_reset_with_dismiss(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "resetdismiss",
        "steps": [
            {"reset": {"app": "EpicTV", "until_state": "home", "timeout": 5, "dismiss_toast": True}},
        ],
    })
    with patch("tvqa.runner.Adb") as adb_cls, patch("tvqa.runner.AgentDevice") as dev_cls, \
         patch("tvqa.runner.ProxyHarness"):
        # First snapshots for poll_until (need "Home" to pass), then overlay for dismiss
        dev_cls.return_value.snapshot.side_effect = [
            '@e1 [heading] "Home"',      # poll_until match
            'React Native warning overlay detected',  # dismiss check
        ]
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is True
    adb_cls.return_value.keyevent.assert_called_once_with("DPAD_CENTER")


def test_run_flow_dismiss_only_when_overlay_present(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "dismiss",
        "steps": [
            {"dismiss": {"key": "DPAD_CENTER", "indicators": ["overlay"], "settle": 0.1}},
        ],
    })
    with patch("tvqa.runner.Adb") as adb_cls, patch("tvqa.runner.AgentDevice") as dev_cls, \
         patch("tvqa.runner.ProxyHarness"):
        dev_cls.return_value.snapshot.return_value = 'Some overlay warning here'
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is True
    adb_cls.return_value.keyevent.assert_called_once_with("DPAD_CENTER")


def test_run_flow_dismiss_skips_when_no_overlay(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "nodismiss",
        "steps": [
            {"dismiss": {"key": "DPAD_CENTER"}},
        ],
    })
    with patch("tvqa.runner.Adb") as adb_cls, patch("tvqa.runner.AgentDevice") as dev_cls, \
         patch("tvqa.runner.ProxyHarness"):
        dev_cls.return_value.snapshot.return_value = '@e1 [heading] "Home"'
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is True
    adb_cls.return_value.keyevent.assert_not_called()


def test_run_flow_wait_log_dict_syntax_returns_match(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "logdict",
        "steps": [
            {"wait_log": {"pattern": "hello", "timeout": 5}},
        ],
    })
    with patch("tvqa.runner.Adb"), patch("tvqa.runner.AgentDevice"), \
         patch("tvqa.runner.ProxyHarness"), \
         patch("tvqa.runner.wait_for_line") as wait_mock:
        from tvqa.logwait import LogWaitResult
        wait_mock.return_value = LogWaitResult(matched=True, line="hello world", elapsed_s=2.5)
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is True
    assert result.log_line == "hello world"
    assert result.log_elapsed_s == 2.5
    wait_mock.assert_called_once_with("hello", 5, serial="emulator-5554", clear_buffer=True, min_s=0.0)


def test_run_flow_wait_log_min_s_catches_too_fast(tmp_path):
    flow_path = _write_flow(tmp_path, {
        "name": "logmins",
        "steps": [
            {"wait_log": {"pattern": "hello", "timeout": 5, "min_s": 2.0}},
        ],
    })
    with patch("tvqa.runner.Adb"), patch("tvqa.runner.AgentDevice"), \
         patch("tvqa.runner.ProxyHarness"), \
         patch("tvqa.runner.wait_for_line") as wait_mock:
        from tvqa.logwait import LogWaitTimeout
        wait_mock.side_effect = LogWaitTimeout("matched too fast (0.1s < 2.0s min)")
        result = run_flow(flow_path, project_dir=_project(tmp_path), serial="emulator-5554")

    assert result.passed is False
    assert "too fast" in result.detail
    wait_mock.assert_called_once_with("hello", 5, serial="emulator-5554", clear_buffer=True, min_s=2.0)
