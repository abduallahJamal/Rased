"""
CLI flags & configuration parser for Rased.

Implements full argument surface:
  stdin piping, -f/--file, -c/--concurrency, -d/--delay,
  --exclude/--include, --no-third-party/--third-party,
  -j/--javascript, -p/--proxy, -o/--output, -w/--overwrite
plus production flags: timeout, user-agent, wait-until, headed, verbose.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List

from . import __version__
from .browser import BrowserManager
from .config import RasedConfig
from .logger import RasedLogger
from .storage import StorageHandler
from .worker import WorkerPool


# ── helpers for input handling ─────────────────────────────────────


def _read_stdin_urls() -> List[str]:
    """Read piped stdin line-by-line, ignoring empty lines & comments."""
    if sys.stdin.isatty():
        return []
    urls: List[str] = []
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for token in line.split():
                token = token.strip().strip(",").strip()
                if token:
                    urls.append(token)
    except Exception:
        pass
    return urls


def _read_file_urls(path: Path) -> List[str]:
    """Read URLs from a file (one per line)."""
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    urls: List[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for token in line.split():
                token = token.strip().strip(",")
                if token:
                    urls.append(token)
    except Exception as exc:
        print(f"error: failed to read {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    return urls


def _build_parser() -> argparse.ArgumentParser:
    """Construct the full argparse parser."""
    parser = argparse.ArgumentParser(
        prog="rased",
        description="Rased (راصد) — headless Chromium reconnaissance engine. Fetch pages, mirror assets, execute JS.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
examples:
  # Pipe URLs from stdin
  cat urls.txt | rased -o out --no-third-party
  echo "https://example.com" | rased -j "document.title"

  # File input with concurrency & rate limiting
  rased -f urls.txt -c 5 -d 500 -o recon

  # Filter by MIME / proxy through Burp Suite or OWASP ZAP
  rased -f urls.txt --exclude "image/" --exclude "font/" -p http://127.0.0.1:8080 -k

  # JavaScript telemetry extraction
  echo "https://target.com" | rased -j "JSON.stringify(performance.getEntries().map(e=>e.name))"
  echo "https://target.com" | rased -j "Array.from(document.scripts).map(s=>s.src)"

  # Third-party only collection
  rased -f urls.txt --third-party -o thirdparty

  # Verbose + overwrite
  rased -f urls.txt -v -w --timeout 15000

aliases:
  `page-fetch` and `pfetch` are installed alongside `rased` for drop-in pipeline compatibility.

input:
  URLs are read from stdin (pipe), -f/--file, and/or positional args. Deduplication is automatic.
  Bare domains (example.com) are normalised to https://example.com.

output:
  Each response is saved under <output>/<host>/<path> mirroring origin structure.
  Every file gets an accompanying .meta JSON with request/response telemetry.
        """,
    )

    # ── Input ──────────────────────────────────────────────────────
    inp = parser.add_argument_group("input")
    inp.add_argument(
        "-f", "--file", type=Path, metavar="PATH", help="File containing URLs (one per line, # comments ignored)"
    )
    inp.add_argument("urls", nargs="*", metavar="URL", help="Target URLs (also accepted via stdin pipe)")

    # ── Concurrency ────────────────────────────────────────────────
    conc = parser.add_argument_group("concurrency & timing")
    conc.add_argument(
        "-c", "--concurrency", type=int, default=3, metavar="N", help="Number of concurrent workers (default: 3)"
    )
    conc.add_argument(
        "-d",
        "--delay",
        type=int,
        default=0,
        metavar="MS",
        help="Delay between page requests per worker in milliseconds (default: 0)",
    )
    conc.add_argument(
        "-t",
        "--timeout",
        type=int,
        default=30000,
        metavar="MS",
        help="Page navigation timeout in milliseconds (default: 30000)",
    )
    conc.add_argument(
        "--wait-until",
        choices=["load", "domcontentloaded", "networkidle", "commit"],
        default="networkidle",
        help="Playwright waitUntil condition (default: networkidle)",
    )

    # ── Filtering & Scope ──────────────────────────────────────────
    filt = parser.add_argument_group("filtering & scope")
    filt.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="STR",
        help="Exclude responses whose Content-Type/URL contains STR (repeatable)",
    )
    filt.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="STR",
        help="Only save responses matching STR (MIME or extension, repeatable)",
    )
    filt.add_argument(
        "--no-third-party",
        action="store_true",
        dest="no_third_party",
        help="Only save requests where hostname matches target or its subdomains",
    )
    filt.add_argument(
        "--third-party",
        action="store_true",
        help="Only save external third-party requests (inverse of --no-third-party)",
    )

    # ── JS Engine ──────────────────────────────────────────────────
    js = parser.add_argument_group("javascript execution")
    js.add_argument(
        "-j",
        "--javascript",
        type=str,
        default=None,
        metavar="EXPR",
        help='JavaScript expression to evaluate in page context (e.g. "document.title")',
    )

    # ── Network ────────────────────────────────────────────────────
    net = parser.add_argument_group("network & proxy")
    net.add_argument(
        "-p",
        "--proxy",
        type=str,
        default=None,
        metavar="URL",
        help="Upstream proxy URL (http://127.0.0.1:8080 or socks5://host:port)",
    )
    net.add_argument(
        "-k",
        "--insecure",
        action="store_true",
        help="Ignore TLS/SSL certificate errors (useful with intercepting proxies)",
    )
    net.add_argument("--ignore-ssl", action="store_true", dest="insecure", help=argparse.SUPPRESS)
    net.add_argument("-A", "--user-agent", type=str, default=None, metavar="UA", help="Custom User-Agent string")

    # ── Output ─────────────────────────────────────────────────────
    out = parser.add_argument_group("output")
    out.add_argument("-o", "--output", type=Path, default=Path("out"), metavar="DIR", help="Output directory (default: ./out)")
    out.add_argument(
        "-w",
        "--overwrite",
        action="store_true",
        help="Overwrite existing files instead of incremental naming (script.1.js)",
    )
    out.add_argument("-v", "--verbose", action="store_true", help="Verbose output (show each saved asset)")

    # ── Misc ───────────────────────────────────────────────────────
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode (for debugging)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    return parser


def parse_config(argv: List[str] | None = None, *, read_stdin: bool = True) -> RasedConfig:
    """Parse CLI args + stdin/file into a validated RasedConfig."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    urls: List[str] = []

    if args.urls:
        urls.extend(args.urls)

    if read_stdin and argv is None:
        stdin_urls = _read_stdin_urls()
        if stdin_urls:
            urls.extend(stdin_urls)

    if args.file:
        file_urls = _read_file_urls(args.file)
        urls.extend(file_urls)

    if not urls:
        parser.print_usage(sys.stderr)
        print("\nerror: no URLs provided — pipe via stdin, use -f/--file, or pass as arguments", file=sys.stderr)
        print('  example: echo "https://example.com" | rased', file=sys.stderr)
        print("  example: rased -f urls.txt", file=sys.stderr)
        sys.exit(2)

    config = RasedConfig(
        urls=urls,
        file=args.file,
        concurrency=args.concurrency,
        delay_ms=args.delay,
        timeout_ms=args.timeout,
        exclude=args.exclude or [],
        include=args.include or [],
        no_third_party=args.no_third_party,
        third_party=args.third_party,
        javascript=args.javascript,
        proxy=args.proxy,
        ignore_ssl=args.insecure,
        user_agent=args.user_agent,
        output=args.output,
        overwrite=args.overwrite,
        verbose=args.verbose,
        headless=not args.headed,
        wait_until=args.wait_until,
    )

    try:
        config.validate()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    if not config.urls:
        print("error: no valid URLs after normalisation/deduplication", file=sys.stderr)
        sys.exit(2)

    return config


# ── async entry point ──────────────────────────────────────────────


async def async_main(config: RasedConfig) -> int:
    """
    Orchestrate: logger → storage → browser → worker-pool.

    Returns exit code (0 = success, 1 = total failure).
    """
    logger = RasedLogger(verbose=config.verbose)
    logger.banner()
    logger.info(f"Targets  : {len(config.urls)} unique URL(s)")
    logger.info(f"Workers  : {config.concurrency}  |  Delay: {config.delay_ms}ms  |  Timeout: {config.timeout_ms}ms")
    logger.info(f"Output   : {config.output.resolve()}")
    if config.exclude:
        logger.info(f"Exclude  : {', '.join(config.exclude)}")
    if config.include:
        logger.info(f"Include  : {', '.join(config.include)}")
    if config.no_third_party:
        logger.info("Scope    : same-site only (--no-third-party)")
    if config.third_party:
        logger.info("Scope    : third-party only (--third-party)")
    if config.javascript:
        logger.info(f"JS expr  : {config.javascript[:120]}")
    if config.proxy:
        logger.info(f"Proxy    : {config.proxy}  (ignore-ssl={config.ignore_ssl})")
    logger.info("")

    if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
        for candidate in ["/opt/playwright/browsers", "/ms-playwright", os.path.expanduser("~/.cache/ms-playwright")]:
            if Path(candidate).exists():
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = candidate
                break

    storage = StorageHandler(config, logger)
    await storage.ensure_output_dir()

    browser = BrowserManager(config, logger, storage)
    pool = WorkerPool(config, logger, browser)

    try:
        results = await pool.run()
        if not results:
            return 1
        ok = sum(1 for r in results if r.get("ok"))
        if ok == 0:
            return 1
        return 0
    except KeyboardInterrupt:
        logger.warn("Interrupted — cleaning up...")
        return 130
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


def main(argv: List[str] | None = None) -> None:
    """
    Synchronous CLI entry point — parses args and runs asyncio loop.
    Handles SIGINT/SIGTERM gracefully.
    """
    config = parse_config(argv)

    try:
        exit_code = asyncio.run(async_main(config))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        exit_code = 130

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
