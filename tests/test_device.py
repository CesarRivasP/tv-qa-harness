from unittest.mock import patch, MagicMock
from tvqa.device import AgentDevice


def test_open_app_invokes_agent_device_open():
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout="", returncode=0)
        dev = AgentDevice(platform="android")
        dev.open_app("EpicTV")  # → _facts.yml: dogfood.app_name
        args = run.call_args[0][0]
        assert args == ["agent-device", "open", "EpicTV", "--platform", "android"]


def test_snapshot_returns_text():
    snapshot_text = '@e1 [heading] "Settings"\n@e2 [button] "Sign In"\n'
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout=snapshot_text, returncode=0)
        dev = AgentDevice()
        assert dev.snapshot() == snapshot_text
        args = run.call_args[0][0]
        assert args == ["agent-device", "snapshot", "-i"]


def test_press_passes_ref_with_settle():
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout="", returncode=0)
        dev = AgentDevice()
        dev.press("@e2")
        args = run.call_args[0][0]
        assert args == ["agent-device", "press", "@e2", "--settle"]


def test_screenshot_goes_to_disk_not_stdout(tmp_path):
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout="", returncode=0)
        dev = AgentDevice()
        out = tmp_path / "evidence.png"
        dev.screenshot(out)
        args = run.call_args[0][0]
        assert args == ["agent-device", "screenshot", str(out)]
