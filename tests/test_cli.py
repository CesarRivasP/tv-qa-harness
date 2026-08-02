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


def test_proxy_check_validates_addons(monkeypatch, tmp_path):
    from tvqa import cli as cli_module

    monkeypatch.setattr(cli_module, "_resolve_serial", lambda serial: "emulator-5554")
    monkeypatch.setattr(cli_module, "shutil", type("shutil", (), {"which": lambda *a, **k: "/usr/bin/mitmdump"})())
    class FakeResult:
        stdout = "null"
    monkeypatch.setattr(cli_module, "subprocess", type("subprocess", (), {
        "run": lambda *a, **k: FakeResult()
    })())

    project = tmp_path / "proj"
    project.mkdir()
    (project / "project.yaml").write_text("proxy:\n  addons:\n    epic_stall: 'stall.py'\n")
    (project / "stall.py").write_text("# stub")

    runner = CliRunner()
    result = runner.invoke(main, ["proxy", "check", "--project", str(project)])
    assert result.exit_code == 0
    payload = __import__("json").loads(result.output.strip())
    assert payload["proxy_installed"] is True
    assert payload["addons_found"]["epic_stall"] is True
    assert payload["clean"] is True


def test_proxy_check_missing_addon_exits_1(monkeypatch, tmp_path):
    from tvqa import cli as cli_module

    monkeypatch.setattr(cli_module, "_resolve_serial", lambda serial: "emulator-5554")
    monkeypatch.setattr(cli_module, "shutil", type("shutil", (), {"which": lambda *a, **k: "/usr/bin/mitmdump"})())
    class FakeResult2:
        stdout = "null"
    monkeypatch.setattr(cli_module, "subprocess", type("subprocess", (), {
        "run": lambda *a, **k: FakeResult2()
    })())

    project = tmp_path / "proj"
    project.mkdir()
    (project / "project.yaml").write_text("proxy:\n  addons:\n    epic_stall: 'missing.py'\n")

    runner = CliRunner()
    result = runner.invoke(main, ["proxy", "check", "--project", str(project)])
    assert result.exit_code == 1
    payload = __import__("json").loads(result.output.strip())
    assert payload["addons_found"]["epic_stall"] is False
    assert payload["clean"] is False


def test_hygiene_check_with_project_validates_addons(monkeypatch, tmp_path):
    from tvqa import cli as cli_module

    class FakeAdb:
        def __init__(self, serial=None):
            pass
        def shell(self, cmd):
            return "null"
        def devices(self):
            return ["emulator-5554"]

    monkeypatch.setattr(cli_module, "Adb", FakeAdb)
    # Mock hygiene.check
    monkeypatch.setattr(cli_module, "_hygiene", type("H", (), {
        "check": lambda *a, **k: type("R", (), {"clean": True, "issues": []})()
    })())

    project = tmp_path / "proj"
    project.mkdir()
    (project / "project.yaml").write_text("proxy:\n  addons:\n    epic_stall: 'stall.py'\n")
    (project / "stall.py").write_text("# stub")

    runner = CliRunner()
    result = runner.invoke(main, ["hygiene", "check", "--project", str(project)])
    assert result.exit_code == 0
    payload = __import__("json").loads(result.output.strip())
    assert payload["clean"] is True


def test_hygiene_check_with_project_missing_addon_is_dirty(monkeypatch, tmp_path):
    from tvqa import cli as cli_module

    class FakeAdb:
        def __init__(self, serial=None):
            pass
        def shell(self, cmd):
            return "null"
        def devices(self):
            return ["emulator-5554"]

    monkeypatch.setattr(cli_module, "Adb", FakeAdb)
    monkeypatch.setattr(cli_module, "_hygiene", type("H", (), {
        "check": lambda *a, **k: type("R", (), {"clean": True, "issues": []})()
    })())

    project = tmp_path / "proj"
    project.mkdir()
    (project / "project.yaml").write_text("proxy:\n  addons:\n    epic_stall: 'missing.py'\n")

    runner = CliRunner()
    result = runner.invoke(main, ["hygiene", "check", "--project", str(project)])
    assert result.exit_code == 1
    payload = __import__("json").loads(result.output.strip())
    assert payload["clean"] is False
    assert "missing" in payload["issues"][0]
