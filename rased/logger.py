"""
Structured, colour-aware logging for Rased.

Uses Rich for pretty terminal output when available, falls back to plain prints.
All JS evaluation outputs are prefixed with [JS] for easy grepping.
"""

from __future__ import annotations

import sys
import time

try:
    from rich.console import Console
    from rich.theme import Theme

    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False
    Console = None  # type: ignore


_THEME = Theme(
    {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "bold red",
        "js": "magenta",
        "dimmed": "dim",
        "highlight": "bold white",
    }
) if _HAS_RICH else None


class RasedLogger:
    """
    Central logger — thread-safe for asyncio workers.
    All methods write to stderr except JS output which goes to stdout (per spec).
    """

    def __init__(self, verbose: bool = False, use_color: bool = True) -> None:
        self.verbose = verbose
        self.use_color = use_color and _HAS_RICH and sys.stderr.isatty()
        if _HAS_RICH:
            self.console = Console(theme=_THEME, stderr=True, highlight=False)  # type: ignore
            self.console_stdout = Console(theme=_THEME, stderr=False, highlight=False)  # type: ignore
        else:
            self.console = None  # type: ignore
            self.console_stdout = None  # type: ignore
        self._start = time.monotonic()

    # ── low-level ──────────────────────────────────────────────────

    def _write_stderr(self, msg: str, style: str = "") -> None:
        if self.console and self.use_color:
            self.console.print(msg, style=style, markup=False)
        else:
            print(msg, file=sys.stderr, flush=True)

    def _write_stdout(self, msg: str, style: str = "") -> None:
        if self.console_stdout and self.use_color:
            self.console_stdout.print(msg, style=style, markup=False)
        else:
            print(msg, file=sys.stdout, flush=True)

    # ── public API ─────────────────────────────────────────────────

    def banner(self) -> None:
        """Print startup banner."""
        banner_text = r"""
 ╔══════════════════════════════════════════════════════╗
 ║  RASED  v1.2.0  —  Headless Recon Engine             ║
 ║  Chromium  •  Playwright  •  asyncio  •  Python      ║
 ╚══════════════════════════════════════════════════════╝
"""
        if self.console and self.use_color:
            self.console.print(banner_text, style="info")
        else:
            print(banner_text, file=sys.stderr)

    def info(self, msg: str) -> None:
        self._write_stderr(msg, style="info")

    def success(self, msg: str) -> None:
        self._write_stderr(f"✔ {msg}", style="success")

    def warn(self, msg: str) -> None:
        self._write_stderr(f"⚠ {msg}", style="warning")

    def error(self, msg: str) -> None:
        self._write_stderr(f"✖ {msg}", style="error")

    def debug(self, msg: str) -> None:
        if self.verbose:
            self._write_stderr(f"  [debug] {msg}", style="dimmed")

    def url_start(self, url: str, worker_id: int) -> None:
        self._write_stderr(f"[W{worker_id}] → Fetching {url}", style="info")

    def url_done(self, url: str, status: str, elapsed_ms: int, assets: int, worker_id: int) -> None:
        self._write_stderr(
            f"[W{worker_id}] ✓ {url}  [{status}]  {elapsed_ms}ms  ({assets} assets)",
            style="success",
        )

    def url_fail(self, url: str, reason: str, worker_id: int) -> None:
        self._write_stderr(f"[W{worker_id}] ✖ {url}  —  {reason}", style="error")

    def asset_saved(self, local_path: str, status: int, mime: str) -> None:
        if self.verbose:
            self._write_stderr(f"  ↳ [{status}] {mime:25s} → {local_path}", style="dimmed")

    def asset_skipped(self, url: str, reason: str) -> None:
        if self.verbose:
            self._write_stderr(f"  ⊘ SKIP {url}  ({reason})", style="dimmed")

    def js_output(self, url: str, output: str) -> None:
        """
        JS evaluation output — MUST go to stdout per spec:
          [JS] [https://target.com] Output: ...
        """
        line = f"[JS] [{url}] {output}"
        self._write_stdout(line, style="js")

    def js_error(self, url: str, err: str) -> None:
        line = f"[JS] [{url}] ERROR: {err}"
        self._write_stdout(line, style="error")

    def summary(self, total: int, ok: int, failed: int, total_assets: int, elapsed_s: float) -> None:
        msg = (
            f"\n{'─'*60}\n"
            f"  Done — {total} URLs  •  {ok} ok  •  {failed} failed  •  {total_assets} assets  •  {elapsed_s:.1f}s\n"
            f"{'─'*60}"
        )
        if self.console and self.use_color:
            self.console.print(msg, style="highlight")
        else:
            print(msg, file=sys.stderr)


# Backward-compatible alias
PageFetchLogger = RasedLogger
