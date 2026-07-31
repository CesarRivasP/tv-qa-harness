from pathlib import Path

from PIL import Image
from tvqa.verify import region_matches, phash_of_region, region_contains_text

FIXTURES = Path(__file__).parent / "fixtures"


def _make_image(path, color):
    img = Image.new("RGB", (200, 100), color=color)
    img.save(path)
    return path


def test_phash_of_region_is_stable_for_same_image(tmp_path):
    img_path = _make_image(tmp_path / "a.png", (255, 0, 0))
    h1 = phash_of_region(img_path, box=(0, 0, 200, 100))
    h2 = phash_of_region(img_path, box=(0, 0, 200, 100))
    assert h1 == h2


def test_region_matches_true_for_identical_color(tmp_path):
    reference = _make_image(tmp_path / "ref.png", (10, 20, 30))
    candidate = _make_image(tmp_path / "cand.png", (10, 20, 30))
    ref_hash = phash_of_region(reference, box=(0, 0, 200, 100))
    assert region_matches(candidate, box=(0, 0, 200, 100), expected_hash=ref_hash, max_distance=5)


def test_region_matches_false_for_very_different_pattern(tmp_path):
    # Solid-color images hash identically regardless of color, so use a pattern.
    ref = Image.new("RGB", (200, 100), color=(10, 20, 30))
    for x in range(0, 200, 10):
        for y in range(0, 100, 10):
            ref.putpixel((x, y), (255, 0, 0))
    ref.save(tmp_path / "ref.png")

    cand = Image.new("RGB", (200, 100), color=(250, 240, 230))
    for x in range(0, 200, 20):
        for y in range(0, 100, 20):
            cand.putpixel((x, y), (0, 255, 0))
    cand.save(tmp_path / "cand.png")

    ref_hash = phash_of_region(tmp_path / "ref.png", box=(0, 0, 200, 100))
    assert not region_matches(tmp_path / "cand.png", box=(0, 0, 200, 100), expected_hash=ref_hash, max_distance=5)


def test_region_contains_text_finds_expected_string():
    fixture = FIXTURES / "channel_unavailable.png"
    assert region_contains_text(fixture, box=(0, 0, 400, 120), expected_substring="Channel")


def test_region_contains_text_false_for_missing_string():
    fixture = FIXTURES / "channel_unavailable.png"
    assert not region_contains_text(fixture, box=(0, 0, 400, 120), expected_substring="Iniciar sesión")
