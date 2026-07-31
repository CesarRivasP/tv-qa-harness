from pathlib import Path
import yaml
from unittest.mock import MagicMock

from tvqa.wait import poll_until, state_check_fn
from tvqa.states import StateRegistry


def test_poll_until_true_on_third_attempt():
    calls = {"n": 0}

    def check():
        calls["n"] += 1
        return calls["n"] >= 3

    assert poll_until(check, timeout_s=2, interval_s=0.01) is True
    assert calls["n"] == 3


def test_poll_until_false_on_timeout():
    assert poll_until(lambda: False, timeout_s=0.05, interval_s=0.01) is False


def test_state_check_fn_uses_snapshot_for_a11y(tmp_path):
    config_path = tmp_path / "states.yaml"
    config_path.write_text(yaml.safe_dump({
        "states": {"login": {"method": "a11y", "expected_text": "Sign In"}}
    }))
    registry = StateRegistry.load(config_path)

    device = MagicMock()
    device.snapshot.return_value = '@e2 [button] "Sign In"'
    adb = MagicMock()
    check = state_check_fn(registry, "login", adb=adb, device=device, work_dir=tmp_path)
    assert check() is True
    device.snapshot.assert_called_once()
    adb.screenshot.assert_not_called()


def test_state_check_fn_uses_screenshot_for_ocr(tmp_path):
    config_path = tmp_path / "states.yaml"
    config_path.write_text(yaml.safe_dump({
        "states": {
            "chan": {"method": "ocr", "box": [0, 0, 400, 120], "expected_substring": "Channel"}
        }
    }))
    registry = StateRegistry.load(config_path)
    fixtures = Path(__file__).parent / "fixtures"

    adb = MagicMock()
    adb.screenshot.side_effect = lambda p: Path(p).write_bytes(
        (fixtures / "channel_unavailable.png").read_bytes()
    )
    device = MagicMock()
    check = state_check_fn(registry, "chan", adb=adb, device=device, work_dir=tmp_path)
    assert check() is True
    adb.screenshot.assert_called_once()
