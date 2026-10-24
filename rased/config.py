"""
Configuration & data models for Rased.

Centralises all CLI options into a typed dataclass so every
module (worker, browser, storage) shares a single source of truth.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse


@dataclasses.dataclass(slots=True)
class RasedConfig:
    """Runtime configuration populated by the CLI parser."""

    # ── Input ──────────────────────────────────────────────────────
    urls: List[str] = dataclasses.field(default_factory=list)
    file: Optional[Path] = None

    # ── Concurrency & Timing ───────────────────────────────────────
    concurrency: int = 3
    delay_ms: int = 0
    timeout_ms: int = 30000  # page navigation timeout

    # ── Filtering & Scope ──────────────────────────────────────────
    exclude: List[str] = dataclasses.field(default_factory=list)  # MIME / substring
    include: List[str] = dataclasses.field(default_factory=list)  # whitelist
    no_third_party: bool = False  # only same-site
    third_party: bool = False  # only external

    # ── JS Engine ──────────────────────────────────────────────────
    javascript: Optional[str] = None  # JS expression to evaluate

    # ── Network ────────────────────────────────────────────────────
    proxy: Optional[str] = None  # http://127.0.0.1:8080  or socks5://
    ignore_ssl: bool = False
    user_agent: Optional[str] = None
    extra_headers: dict = dataclasses.field(default_factory=dict)

    # ── Output ─────────────────────────────────────────────────────
    output: Path = dataclasses.field(default_factory=lambda: Path("out"))
    overwrite: bool = False
    verbose: bool = False
    headless: bool = True

    # ── Internals ──────────────────────────────────────────────────
    wait_until: str = "networkidle"  # load | domcontentloaded | networkidle | commit

    # ── Validation ─────────────────────────────────────────────────
    def validate(self) -> None:
        if self.concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        if self.delay_ms < 0:
            raise ValueError("delay must be >= 0")
        if self.timeout_ms < 1000:
            raise ValueError("timeout must be >= 1000 ms")
        if self.no_third_party and self.third_party:
            raise ValueError("--no-third-party and --third-party are mutually exclusive")
        # Normalise URLs: ensure scheme
        normalised: List[str] = []
        for raw in self.urls:
            raw = raw.strip()
            if not raw:
                continue
            if not raw.startswith(("http://", "https://")):
                raw = "https://" + raw
            # basic URL validation
            parsed = urlparse(raw)
            if not parsed.netloc:
                continue
            normalised.append(raw)
        # deduplicate preserving order
        seen: set[str] = set()
        deduped: List[str] = []
        for u in normalised:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        self.urls = deduped

    # ── Helpers ────────────────────────────────────────────────────
    @property
    def has_filters(self) -> bool:
        return bool(self.exclude or self.include or self.no_third_party or self.third_party)

    def should_save(self, mime_or_url: str, request_host: str, target_host: str) -> tuple[bool, str]:
        """
        Apply include / exclude / scope rules.

        Returns (should_save, reason_if_skipped).
        """
        lower = mime_or_url.lower()

        # include whitelist — if set, *only* matching items pass
        if self.include:
            matched = any(token.lower() in lower for token in self.include)
            if not matched:
                return False, "not in --include list"

        # exclude blacklist
        if self.exclude:
            for token in self.exclude:
                if token.lower() in lower:
                    return False, f"matched --exclude '{token}'"

        # third-party scope rules
        req_host = request_host.lower()
        tgt_host = target_host.lower()

        def is_same_site(req: str, tgt: str) -> bool:
            return req == tgt or req.endswith("." + tgt)

        if self.no_third_party:
            if not is_same_site(req_host, tgt_host):
                return False, "filtered --no-third-party (external host)"
        if self.third_party:
            if is_same_site(req_host, tgt_host):
                return False, "filtered --third-party (same-site only)"

        return True, ""

    def __repr__(self) -> str:
        return (
            f"RasedConfig(urls={len(self.urls)}, concurrency={self.concurrency}, "
            f"delay={self.delay_ms}ms, output={self.output}, proxy={self.proxy})"
        )


# Backward-compatible alias
PageFetchConfig = RasedConfig
