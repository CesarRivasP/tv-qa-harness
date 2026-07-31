from click.testing import CliRunner
from tvqa.cli import main


def test_devices_command_invokes_adb(monkeypatch):
    from tvqa import cli as cli_module

    class FakeAdb:
        def __init__(self, serial=None):
            pass

        def devices(self):
            return ["emulator-5554"]

    monkeypatch.setattr(cli_module, "Adb", FakeAdb)
    runner = CliRunner()
    result = runner.invoke(main, ["devices"])
    assert result.exit_code == 0
    assert "emulator-5554" in result.output


def test_state_check_prints_json(monkeypatch, tmp_path):
    from tvqa import cli as cli_module

    class FakeAdb:
        def __init__(self, serial=None):
            pass

        def screenshot(self, out_path):
            out_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
            return out_path

    class FakeRegistry:
        @classmethod
        def load(cls, path):
            return cls()

        def method_of(self, name):
            return "ocr"

        def check(self, name, screenshot_path=None, snapshot_text=None):
            from tvqa.states import StateResult
            return StateResult(state=name, matched=True, detail="fake match")

    monkeypatch.setattr(cli_module, "Adb", FakeAdb)
    monkeypatch.setattr(cli_module, "StateRegistry", FakeRegistry)

    states_yaml = tmp_path / "states.yaml"
    states_yaml.write_text("states: {}\n")

    runner = CliRunner()
    result = runner.invoke(
        main, ["state", "check", "--states-file", str(states_yaml), "--state", "home_screen"]
    )
    assert result.exit_code == 0
    assert '"matched": true' in result.output


def test_state_wait_prints_json(monkeypatch, tmp_path):
    from tvqa import cli as cli_module

    class FakeRegistry:
        @classmethod
        def load(cls, path):
            return cls()

    monkeypatch.setattr(cli_module, "StateRegistry", FakeRegistry)
    monkeypatch.setattr(cli_module, "state_check_fn", lambda *a, **k: lambda: True)

    states_yaml = tmp_path / "states.yaml"
    states_yaml.write_text("states: {}\n")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["state", "wait", "--states-file", str(states_yaml), "--state", "home", "--timeout", "5"],
    )
    assert result.exit_code == 0
    assert '"matched": true' in result.output
