from unittest.mock import patch, MagicMock
from tvqa.adb import Adb, resolve_serial, lan_ip


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


def test_wifi_disable_sends_svc_command():
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout="", returncode=0)
        adb = Adb(serial="26251HFDD6RBL8")  # physical device, USB transport
        adb.wifi_disable()
        args = run.call_args[0][0]
        assert args == ["adb", "-s", "26251HFDD6RBL8", "shell", "svc", "wifi", "disable"]


def test_wifi_enable_sends_svc_command():
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout="", returncode=0)
        adb = Adb(serial="26251HFDD6RBL8")
        adb.wifi_enable()
        args = run.call_args[0][0]
        assert args == ["adb", "-s", "26251HFDD6RBL8", "shell", "svc", "wifi", "enable"]


def test_resolve_serial_prefers_explicit():
    # Explicit serial short-circuits before ever calling `adb devices`.
    with patch("subprocess.run") as run:
        assert resolve_serial("emulator-5554") == "emulator-5554"
        run.assert_not_called()


def test_resolve_serial_autodetects_sole_device():
    fake_output = "List of devices attached\n26251HFDD6RBL8\tdevice\n\n"
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout=fake_output, returncode=0)
        assert resolve_serial(None) == "26251HFDD6RBL8"


def test_resolve_serial_falls_back_when_ambiguous():
    fake_output = "List of devices attached\nemulator-5554\tdevice\n26251HFDD6RBL8\tdevice\n\n"
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout=fake_output, returncode=0)
        assert resolve_serial(None, fallback="emulator-5554") == "emulator-5554"


def test_resolve_serial_falls_back_when_none_attached():
    fake_output = "List of devices attached\n\n"
    with patch("subprocess.run") as run:
        run.return_value = MagicMock(stdout=fake_output, returncode=0)
        assert resolve_serial(None, fallback="emulator-5554") == "emulator-5554"


def test_lan_ip_returns_socket_name():
    with patch("socket.socket") as sock_cls:
        sock = MagicMock()
        sock.getsockname.return_value = ("192.168.1.50", 0)
        sock_cls.return_value = sock
        assert lan_ip() == "192.168.1.50"
        sock.connect.assert_called_once_with(("8.8.8.8", 80))
        sock.close.assert_called_once()
