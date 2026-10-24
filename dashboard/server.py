"""
Rased Playground API server — bridges the web dashboard UI to the Rased engine.

Serves static files from ./dashboard + handles POST /api/fetch by running
Rased programmatically (asyncio) and returning structured JSON.

Run: python dashboard/server.py  (default port 8787)
Env: PLAYWRIGHT_BROWSERS_PATH=/opt/playwright/browsers
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rased import __version__
from rased.browser import BrowserManager
from rased.config import RasedConfig
from rased.logger import RasedLogger
from rased.storage import StorageHandler
from rased.worker import WorkerPool

# ── in-memory job history (for demo) ───────────────────────────────
HISTORY: list[dict] = []
MAX_HISTORY = 20


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent), **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[rased-dashboard] {self.client_address[0]} - - [{self.log_date_time_string()}] {fmt % args}\n")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/history":
            self.send_json({"history": HISTORY[-10:]})
            return
        if parsed.path == "/api/health":
            self.send_json(
                {
                    "status": "ok",
                    "name": "rased",
                    "version": __version__,
                    "engine": "Playwright Chromium",
                }
            )
            return
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/fetch":
            self.handle_fetch()
            return
        self.send_error(404, "Not found")

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_fetch(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            self.send_json({"error": f"Invalid JSON: {exc}"}, 400)
            return

        urls = payload.get("urls", [])
        if not urls:
            self.send_json({"error": "No URLs provided"}, 400)
            return
        if len(urls) > 5:
            urls = urls[:5]

        out_dir = Path(tempfile.mkdtemp(prefix="rased-play-", dir="/tmp"))

        config = RasedConfig(
            urls=urls,
            concurrency=min(int(payload.get("concurrency", 3)), 3),
            delay_ms=int(payload.get("delay", 0)),
            timeout_ms=int(payload.get("timeout", 15000)),
            exclude=payload.get("exclude", []) or [],
            include=payload.get("include", []) or [],
            no_third_party=bool(payload.get("no_third_party")),
            third_party=bool(payload.get("third_party")),
            javascript=payload.get("javascript") or None,
            output=out_dir,
            overwrite=True,
            verbose=bool(payload.get("verbose")),
            headless=True,
        )
        try:
            config.validate()
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
            return

        try:
            result = asyncio.run(run_fetch(config))
            HISTORY.append(
                {
                    "time": time.time(),
                    "urls": config.urls,
                    "assets": len(result.get("assets", [])),
                    "results": result.get("results", []),
                }
            )
            if len(HISTORY) > MAX_HISTORY:
                HISTORY.pop(0)
            self.send_json(result)
        except Exception as exc:
            import traceback

            traceback.print_exc()
            self.send_json({"error": f"Engine error: {exc}", "logs": [{"type": "error", "text": str(exc)}]}, 500)


async def run_fetch(config: RasedConfig) -> dict:
    """
    Programmatic fetch — returns JSON-serialisable dict:
      { results, assets, js_outputs, logs, elapsed_ms, output_dir }
    """
    if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
        for cand in ["/opt/playwright/browsers", "/ms-playwright", os.path.expanduser("~/.cache/ms-playwright")]:
            if Path(cand).exists():
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = cand
                break

    logs: list[dict] = []

    class CaptureLogger(RasedLogger):
        def __init__(self):
            super().__init__(verbose=config.verbose, use_color=False)
            self.captured = logs

        def _write_stderr(self, msg, style=""):
            self.captured.append({"type": "dim" if "debug" in style else "info", "text": msg})

        def url_start(self, url, worker_id):
            pass  # UI renders start/done summary per result to avoid duplicate lines

        def url_done(self, url, status, elapsed_ms, assets, worker_id):
            pass

        def url_fail(self, url, reason, worker_id):
            pass

        def asset_saved(self, local_path, status, mime):
            if self.verbose:
                self.captured.append({"type": "asset", "text": f"  ↳ [{status}] {mime} → {local_path}"})

        def asset_skipped(self, url, reason):
            if self.verbose:
                self.captured.append({"type": "warn", "text": f"  ⊘ SKIP {url}  ({reason})"})

        def js_output(self, url, output):
            self.captured.append({"type": "js", "url": url, "text": output})

        def js_error(self, url, err):
            self.captured.append({"type": "error", "url": url, "text": err})

        def success(self, msg):
            self.captured.append({"type": "success", "text": msg})

        def info(self, msg):
            self.captured.append({"type": "info", "text": msg})

        def warn(self, msg):
            self.captured.append({"type": "warn", "text": msg})

        def error(self, msg):
            self.captured.append({"type": "error", "text": msg})

        def debug(self, msg):
            if self.verbose:
                self.captured.append({"type": "dim", "text": f"[debug] {msg}"})

        def summary(self, total, ok, failed, total_assets, elapsed_s):
            pass

    logger = CaptureLogger()
    storage = StorageHandler(config, logger)
    await storage.ensure_output_dir()

    browser = BrowserManager(config, logger, storage)
    pool = WorkerPool(config, logger, browser)

    start = time.monotonic()
    js_outputs: list[dict] = []

    orig_js = logger.js_output
    orig_js_err = logger.js_error

    def capture_js(url, output):
        js_outputs.append({"url": url, "output": output})
        orig_js(url, output)

    def capture_js_err(url, err):
        js_outputs.append({"url": url, "error": err, "output": err})
        orig_js_err(url, err)

    logger.js_output = capture_js  # type: ignore
    logger.js_error = capture_js_err  # type: ignore

    try:
        await browser.start()
        results = await pool.run()
    finally:
        try:
            await browser.stop()
        except Exception:
            pass

    assets = []
    out_dir = config.output
    for meta_file in sorted(out_dir.rglob("*.meta")):
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            assets.append(
                {
                    "url": data.get("url"),
                    "method": data.get("method", "GET"),
                    "status": data.get("response", {}).get("status", 0),
                    "mime": data.get("response", {}).get("headers", {}).get("content-type", "")
                    or data.get("response", {}).get("headers", {}).get("Content-Type", ""),
                    "request_headers": data.get("request_headers", {}),
                    "response_headers": data.get("response", {}).get("headers", {}),
                    "timestamp": data.get("timestamp"),
                    "latency_ms": data.get("latency_ms"),
                    "size_bytes": data.get("size_bytes"),
                    "saved_to": data.get("saved_to"),
                }
            )
        except Exception:
            continue

    elapsed = int((time.monotonic() - start) * 1000)

    norm_results = [
        {
            "url": r.get("url"),
            "ok": r.get("ok"),
            "status": r.get("status"),
            "elapsed_ms": r.get("elapsed_ms"),
            "assets": r.get("assets"),
            "error": r.get("error"),
        }
        for r in results
    ]

    return {
        "results": norm_results,
        "assets": assets,
        "js_outputs": js_outputs,
        "logs": logs,
        "elapsed_ms": elapsed,
        "output_dir": str(out_dir),
    }


def create_server(host: str = "0.0.0.0", port: int = 8787) -> ThreadingHTTPServer:
    """Create (without blocking) an HTTP server instance for Rased Dashboard."""
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    port = int(os.environ.get("PORT", "8787"))
    host = os.environ.get("HOST", "0.0.0.0")
    server = create_server(host, port)
    print("╔══════════════════════════════════════════════════════╗")
    print(f"║  Rased Dashboard — http://{host}:{port:<20}║")
    print("║  API: POST /api/fetch  •  GET /api/health            ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"Serving dashboard from {Path(__file__).parent}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
