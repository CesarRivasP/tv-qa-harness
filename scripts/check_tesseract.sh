#!/usr/bin/env bash
# scripts/check_tesseract.sh — verify the OCR fallback tier is operational.
set -euo pipefail

if ! command -v tesseract >/dev/null; then
  echo "tesseract not found. Install: brew install tesseract (macOS) / apt install tesseract-ocr (Debian)" >&2
  exit 1
fi
tesseract --version | head -1
# spa+eng is the default OCR lang pair (see verify.ocr_text_of_region / _facts.yml: infra.ocr_languages); warn if spa missing.
if ! tesseract --list-langs 2>&1 | grep -qx spa; then
  echo "warning: 'spa' language data absent; Spanish-screen OCR will be weak (install tesseract-lang / tesseract-ocr-spa)" >&2
fi
