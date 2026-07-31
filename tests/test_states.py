from pathlib import Path
import yaml
from tvqa.states import StateRegistry, StateResult


def test_load_states_from_yaml(tmp_path):
    config = {
        "states": {
            "channel_unavailable": {
                "method": "ocr",
                "box": [0, 0, 400, 120],
                "expected_substring": "Channel",
            },
            "home_screen": {
                "method": "phash",
                "box": [0, 380, 150, 420],
                "expected_hash": "8f8f8f8f8f8f8f8f",
                "max_distance": 8,
            },
            "login_form": {
                "method": "a11y",
                "expected_text": "Inicia sesión",
            },
        }
    }
    config_path = tmp_path / "states.yaml"
    config_path.write_text(yaml.safe_dump(config))
    registry = StateRegistry.load(config_path)
    assert set(registry.names()) == {"channel_unavailable", "home_screen", "login_form"}
    assert registry.method_of("login_form") == "a11y"


def test_check_returns_ocr_match(tmp_path):
    fixtures = Path(__file__).parent / "fixtures"
    config = {
        "states": {
            "channel_unavailable": {
                "method": "ocr",
                "box": [0, 0, 400, 120],
                "expected_substring": "Channel",
            }
        }
    }
    config_path = tmp_path / "states.yaml"
    config_path.write_text(yaml.safe_dump(config))
    registry = StateRegistry.load(config_path)

    result = registry.check("channel_unavailable", screenshot_path=fixtures / "channel_unavailable.png")
    assert isinstance(result, StateResult)
    assert result.matched is True
    assert result.state == "channel_unavailable"


def test_check_a11y_matches_snapshot_text(tmp_path):
    config = {
        "states": {
            "login_form": {"method": "a11y", "expected_text": "Inicia sesión"},
        }
    }
    config_path = tmp_path / "states.yaml"
    config_path.write_text(yaml.safe_dump(config))
    registry = StateRegistry.load(config_path)

    snapshot = '@e1 [heading] "Bienvenido"\n@e2 [button] "Inicia sesión"\n'
    result = registry.check("login_form", snapshot_text=snapshot)
    assert result.matched is True

    result = registry.check("login_form", snapshot_text='@e1 [heading] "Home"\n')
    assert result.matched is False


def test_check_a11y_without_snapshot_raises(tmp_path):
    config_path = tmp_path / "states.yaml"
    config_path.write_text(yaml.safe_dump({"states": {"s": {"method": "a11y", "expected_text": "x"}}}))
    registry = StateRegistry.load(config_path)
    try:
        registry.check("s")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_check_unknown_state_raises(tmp_path):
    config_path = tmp_path / "states.yaml"
    config_path.write_text(yaml.safe_dump({"states": {}}))
    registry = StateRegistry.load(config_path)
    try:
        registry.check("nope", screenshot_path=Path("irrelevant.png"))
        assert False, "expected KeyError"
    except KeyError:
        pass
