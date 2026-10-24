"""
Shared utility helpers for Rased.
"""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

# ── URL helpers ────────────────────────────────────────────────────


def get_host(url: str) -> str:
    """Extract hostname without port."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
        return host.lower()
    except Exception:
        return ""


def get_origin(url: str) -> str:
    """Return scheme + host (e.g. https://example.com)."""
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.hostname}" if parsed.hostname else ""


def sanitise_filename(name: str, max_len: int = 200) -> str:
    """
    Make a string safe for filesystem use.
    Keeps alphanumerics, dash, underscore, dot.
    """
    safe = re.sub(r"[^A-Za-z0-9._\-]", "_", name)
    safe = re.sub(r"_+", "_", safe)
    safe = safe.strip("._")
    if len(safe) > max_len:
        if "." in safe:
            stem, ext = safe.rsplit(".", 1)
            safe = stem[: max_len - len(ext) - 1] + "." + ext
        else:
            safe = safe[:max_len]
    return safe or "index"


def url_to_local_path(url: str, output_base: Path) -> Path:
    """
    Mirror URL path into local filesystem.

    Examples:
        https://example.com/                -> out/example.com/index.html
        https://example.com/assets/app.js   -> out/example.com/assets/app.js
        https://example.com/search?q=test   -> out/example.com/search_q_test
        https://example.com/api/data.json   -> out/example.com/api/data.json

    Mirrors Detectify page-fetch behaviour: origin becomes top-level folder,
    path segments become subdirectories, query strings are folded into filename.
    """
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "unknown-host"
    if parsed.port:
        host = f"{host}_{parsed.port}"

    path = parsed.path or "/"
    path = path.lstrip("/")

    query = parsed.query
    if query:
        qs_safe = re.sub(r"[^A-Za-z0-9]", "_", query)
        qs_safe = re.sub(r"_+", "_", qs_safe).strip("_")
        if path.endswith("/") or not path:
            path = (path.rstrip("/") + f"/index_{qs_safe}") if path else f"index_{qs_safe}"
        else:
            if "." in Path(path).name:
                p = Path(path)
                new_name = f"{p.stem}_{qs_safe}{p.suffix}"
                path = str(p.parent / new_name) if str(p.parent) != "." else new_name
            else:
                path = f"{path}_{qs_safe}"

    if not path or path.endswith("/"):
        path = path + "index.html" if path else "index.html"

    parts = Path(path).parts
    safe_parts = []
    for part in parts:
        if part in (".", ".."):
            continue
        if "." in part:
            name, ext = part.rsplit(".", 1)
            safe_parts.append(sanitise_filename(name) + "." + sanitise_filename(ext, 20))
        else:
            safe_parts.append(sanitise_filename(part))

    if not safe_parts:
        safe_parts = ["index.html"]

    local = output_base / sanitise_filename(host) / Path(*safe_parts)
    return local


def incremental_path(path: Path) -> Path:
    """
    If file exists and overwrite is False, generate incremental name:
      script.js -> script.1.js -> script.2.js
    """
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}.{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
        if counter > 9999:
            raise RuntimeError(f"Too many incremental files for {path}")


def format_bytes(n: int) -> str:
    """Human-readable byte size."""
    val = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(val) < 1024:
            return f"{val:.1f} {unit}" if unit != "B" else f"{int(val)} {unit}"
        val /= 1024
    return f"{val:.1f} TB"
