from unittest.mock import patch, MagicMock
from tvqa.adb import Adb


def test_devices_parses_serials():
    # → _facts.yml: infra.default_serial
    fake_output = "List of devices attached\nemulator-5554\tdevice\n\n"
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout=fake_output, returncode=0)
        adb = Adb()
        assert adb.devices() == ["emulator-5554"]


def test_shell_passes_serial_flag():
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout="ok\n", returncode=0)
        adb = Adb(serial="emulator-5554")  # → _facts.yml: infra.default_serial
        adb.shell("echo hi")
        args = run.call_args[0][0]
        assert args[:4] == ["adb", "-s", "emulator-5554", "shell"]


def test_tap_sends_keyevent():
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout="", returncode=0)
        adb = Adb(serial="emulator-5554")  # → _facts.yml: infra.default_serial
        adb.keyevent(23)
        args = run.call_args[0][0]
        assert args == ["adb", "-s", "emulator-5554", "shell", "input", "keyevent", "23"]


def test_screenshot_writes_png(tmp_path):
    png_bytes = b"\x89PNG\r\n\x1a\nrest-of-fake-png"
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout=png_bytes, returncode=0)
        adb = Adb(serial="emulator-5554")  # → _facts.yml: infra.default_serial
        out = tmp_path / "shot.png"
        adb.screenshot(out)
        assert out.read_bytes() == png_bytes
