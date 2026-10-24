#!/usr/bin/env bash
set -euo pipefail

# Helper script to validate, test, and push Rased to GitHub.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> Running repository validator..."
python3 scripts/validate.py

echo "==> Running pytest suite..."
pytest -v

echo "==> Ready to push to origin main:"
echo "    git push -u origin main"
