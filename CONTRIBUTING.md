# Contributing to Rased (`راصد`)

Thank you for your interest in improving **Rased**!

## Development Setup

```bash
git clone https://github.com/abduallahJamal/rased.git
cd rased
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

## Quality Checks

Before opening a pull request, ensure all validation checks and tests pass cleanly:

```bash
# 1. Validate AST syntax, banner SVG, placeholders, and Markdown links
python3 scripts/validate.py

# 2. Run the automated pytest suite
pytest -v

# 3. Verify CLI entry points
rased --version
page-fetch --version
```

## Pull Request Guidelines

- Keep `rased/config.py` typed and deterministic; add unit tests in `tests/test_rased.py` for any new CLI flags or filter rules.
- Maintain bilingual parity across [README.md](README.md) and [README.ar.md](README.ar.md) when adding user-facing features.
- Never commit captured target output (`out/`, `*.meta`) or credentials.
