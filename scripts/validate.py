#!/usr/bin/env python3
"""
Repository validator for Rased (راصد).

Checks:
1. Python AST syntax of every .py file under rased/, dashboard/, scripts/, and tests/.
2. Required repository metadata & documentation files exist and are non-empty.
3. SVG validity of assets/banner.svg and absence of raw Arabic <text> inside SVG.
4. Absence of accidental artifacts (.sudo_as_admin_successful, pagefetch.dev, github.com/pagefetch).
5. Relative Markdown links across README.md, README.ar.md, docs/, examples/, CONTRIBUTING.md, CHANGELOG.md.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FILES = [
    "pyproject.toml",
    "requirements.txt",
    "Makefile",
    "LICENSE",
    "README.md",
    "README.ar.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "docs/usage-examples.md",
    "docs/usage-examples.en.md",
    "examples/js-snippets.md",
    "examples/urls.txt",
    "assets/banner.svg",
    "dashboard/index.html",
    "dashboard/server.py",
    "rased/__init__.py",
    "rased/__main__.py",
    "rased/cli.py",
    "rased/config.py",
    "rased/logger.py",
    "rased/utils.py",
    "rased/storage.py",
    "rased/browser.py",
    "rased/worker.py",
    "tests/test_rased.py",
    ".github/workflows/validate.yml",
]

FORBIDDEN_PATTERNS = [
    "pagefetch.dev",
    "github.com/pagefetch",
]

MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")


def strip_fenced_code(md_text: str) -> str:
    return re.sub(r"```.*?```", "", md_text, flags=re.DOTALL)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate Rased repository structure, code, and docs.")
    ap.add_argument("--github-annotations", action="store_true", help="Emit GitHub Actions error annotations")
    args = ap.parse_args()

    errors: list[tuple[str, str]] = []

    def fail(rel_path: str, msg: str) -> None:
        errors.append((rel_path, msg))
        if args.github_annotations:
            print(f"::error file={rel_path}::{msg}")
        else:
            print(f"[ERROR] {rel_path}: {msg}", file=sys.stderr)

    # 1. Required files
    for rel in REQUIRED_FILES:
        p = ROOT / rel
        if not p.exists():
            fail(rel, "Missing required file")
        elif p.stat().st_size == 0:
            fail(rel, "File is empty")

    if (ROOT / ".sudo_as_admin_successful").exists():
        fail(".sudo_as_admin_successful", "Accidental home-directory dotfile must not exist in repository")

    # 2. Python AST check
    py_files = sorted(
        p
        for folder in ("rased", "dashboard", "scripts", "tests")
        for p in (ROOT / folder).rglob("*.py")
    )
    for py in py_files:
        rel = str(py.relative_to(ROOT))
        src = py.read_text(encoding="utf-8")
        try:
            ast.parse(src, filename=rel)
        except SyntaxError as exc:
            fail(rel, f"SyntaxError: {exc}")

    # 3. SVG banner validation (valid XML + crisp English-only SVG <text>)
    banner = ROOT / "assets/banner.svg"
    if banner.exists():
        svg_text = banner.read_text(encoding="utf-8")
        try:
            tree = ET.fromstring(svg_text)
            for elem in tree.iter():
                if elem.tag.endswith("text"):
                    txt = "".join(elem.itertext())
                    if ARABIC_CHAR_RE.search(txt):
                        fail("assets/banner.svg", f"SVG <text> contains Arabic glyphs (causes fallback bidi issues): {txt!r}")
        except ET.ParseError as exc:
            fail("assets/banner.svg", f"Invalid SVG XML: {exc}")

    # 4. Forbidden leftover placeholders across tracked source/docs
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(ROOT))
        if any(part.startswith(".") and part not in (".github", ".gitignore", ".gitattributes") for part in p.parts):
            continue
        if any(part in ("__pycache__", "build", "dist", "out") for part in p.parts) or rel.endswith(".egg-info"):
            continue
        if rel == "scripts/validate.py":
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pat in FORBIDDEN_PATTERNS:
            if pat in content:
                fail(rel, f"Contains leftover placeholder '{pat}'")

    # 5. Markdown relative links
    md_files = [
        ROOT / "README.md",
        ROOT / "README.ar.md",
        ROOT / "CHANGELOG.md",
        ROOT / "CONTRIBUTING.md",
        *sorted((ROOT / "docs").glob("*.md")),
        *sorted((ROOT / "examples").glob("*.md")),
    ]
    for md in md_files:
        if not md.exists():
            continue
        rel_md = str(md.relative_to(ROOT))
        body = strip_fenced_code(md.read_text(encoding="utf-8"))
        for m in MD_LINK_RE.finditer(body):
            target = m.group(1).strip().split()[0]
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            clean = target.split("#", 1)[0]
            if not clean:
                continue
            resolved = (md.parent / clean).resolve()
            if not resolved.exists():
                fail(rel_md, f"Broken relative link -> {target}")

    if errors:
        print(f"\nValidation FAILED with {len(errors)} error(s).", file=sys.stderr)
        return 1

    print(
        f"Validation PASSED: {len(py_files)} Python files, {len(md_files)} Markdown docs, "
        f"SVG banner, and zero leftover placeholders."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
