from unittest.mock import patch, MagicMock
from tvqa.hygiene import check, HygieneReport


def _run_side_effect(args, **kwargs):
    joined = " ".join(args)
    if "settings get global http_proxy" in joined:
        return MagicMock(stdout="null\n", returncode=0)
    if "settings get global global_http_proxy_host" in joined:
        return MagicMock(stdout="null\n", returncode=0)
    if "settings get global global_http_proxy_port" in joined:
        return MagicMock(stdout="null\n", returncode=0)
    if "wm density" in joined:
        return MagicMock(stdout="Physical density: 320\n", returncode=0)
    if "wm size" in joined:
        # → _facts.yml: infra.default_resolution
        return MagicMock(stdout="Physical size: 1920x1080\n", returncode=0)
    return MagicMock(stdout="", returncode=0)


def test_check_reports_clean_when_no_overrides():
    with patch("subprocess.run", side_effect=_run_side_effect):
        report = check(serial="emulator-5554")  # → _facts.yml: infra.default_serial
    assert isinstance(report, HygieneReport)
    assert report.clean is True
    assert report.issues == []


def test_check_flags_proxy_left_configured():
    def side_effect(args, **kwargs):
        joined = " ".join(args)
        if "settings get global http_proxy" in joined:
            # → _facts.yml: proxy_host_ip / proxy_port
            return MagicMock(stdout="10.0.2.2:8080\n", returncode=0)
        return _run_side_effect(args, **kwargs)

    with patch("subprocess.run", side_effect=side_effect):
        report = check(serial="emulator-5554")  # → _facts.yml: infra.default_serial
    assert report.clean is False
    assert any("proxy" in issue for issue in report.issues)


def test_cli_hygiene_check_prints_json(monkeypatch):
    from click.testing import CliRunner
    from tvqa import cli as cli_module
    from tvqa.cli import main

    monkeypatch.setattr(cli_module._hygiene, "check",
                        lambda serial: HygieneReport(clean=True, issues=[]))
    monkeypatch.setattr(cli_module, "_resolve_serial", lambda s: "emulator-5554")

    result = CliRunner().invoke(main, ["hygiene", "check", "--serial", "emulator-5554"])
    assert result.exit_code == 0
    assert '"clean": true' in result.output
