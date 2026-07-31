"""Screen-state verification: perceptual-hash region matching (fast path) and
OCR text matching (fallback for dynamic text). Never returns raw image bytes
to the caller — only a hash, a distance, or extracted text.
"""
from __future__ import annotations

from pathlib import Path

import imagehash
import pytesseract
from PIL import Image

Box = tuple[int, int, int, int]  # left, top, right, bottom


def _load_region(image_path: Path, box: Box) -> Image.Image:
    img = Image.open(image_path)
    return img.crop(box)


def phash_of_region(image_path: Path, box: Box) -> str:
    region = _load_region(image_path, box)
    return str(imagehash.phash(region))


def region_matches(image_path: Path, box: Box, expected_hash: str, max_distance: int = 8) -> bool:
    region = _load_region(image_path, box)
    candidate_hash = imagehash.phash(region)
    expected = imagehash.hex_to_hash(expected_hash)
    return (candidate_hash - expected) <= max_distance


def ocr_text_of_region(image_path: Path, box: Box, lang: str = "spa+eng") -> str:
    # Default lang pair lives in _facts.yml: infra.ocr_languages
    region = _load_region(image_path, box)
    return pytesseract.image_to_string(region, lang=lang).strip()


def region_contains_text(image_path: Path, box: Box, expected_substring: str, lang: str = "spa+eng") -> bool:
    # Default lang pair lives in _facts.yml: infra.ocr_languages
    text = ocr_text_of_region(image_path, box, lang=lang)
    return expected_substring.lower() in text.lower()
