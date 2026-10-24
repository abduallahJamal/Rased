"""
Headless browser manager — Playwright Chromium lifecycle + network interception.

Each page navigation:
  1. Creates isolated BrowserContext (proxy, UA, ignore certs)
  2. Attaches response handler that captures raw bodies
  3. Navigates with timeout + wait_until
  4. Optionally evaluates custom JS
  5. Waits briefly for late XHR / lazy loads
  6. Closes context

Designed to be instantiated once and reused across the worker pool
via a shared Playwright instance + Browser.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

from playwright.async_api import Browser, Playwright, TimeoutError as PlaywrightTimeout, async_playwright

from .config import RasedConfig
from .logger import RasedLogger
from .storage import StorageHandler


class BrowserManager:
    """
    Manages the global Playwright + Chromium browser lifetime.

    Usage:
        mgr = BrowserManager(config, logger, storage)
        await mgr.start()
        try:
            await mgr.fetch(url, worker_id=0)
        finally:
            await mgr.stop()
    """

    def __init__(self, config: RasedConfig, logger: RasedLogger, storage: StorageHandler) -> None:
        self.config = config
        self.logger = logger
        self.storage = storage

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._lock = asyncio.Lock()
        self._started = False

    # ── lifecycle ──────────────────────────────────────────────────

    async def start(self) -> None:
        """Launch Playwright & Chromium."""
        if self._started:
            return
        async with self._lock:
            if self._started:
                return

            self.logger.info("Launching Chromium (headless=%s)..." % self.config.headless)
            self._playwright = await async_playwright().start()

            launch_args = [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-timer-throttling",
            ]

            if self.config.proxy:
                self.logger.info(f"Proxy configured: {self.config.proxy}")
                if self.config.ignore_ssl:
                    self.logger.info("Ignoring TLS errors (proxy mode)")

            launch_kwargs: dict = {
                "headless": self.config.headless,
                "args": launch_args,
            }

            chrome_path = os.environ.get("CHROME_PATH") or os.environ.get("CHROMIUM_PATH")
            if chrome_path:
                launch_kwargs["executable_path"] = chrome_path

            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            self._started = True
            self.logger.success("Chromium launched (Playwright headless engine ready)")

    async def stop(self) -> None:
        """Gracefully close browser & playwright."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._started = False
        self.logger.debug("BrowserManager stopped — Chromium terminated")

    # ── core fetch ─────────────────────────────────────────────────

    async def fetch(self, url: str, worker_id: int = 0) -> dict:
        """
        Fetch a single URL and intercept all network resources.

        Returns dict: {url, ok, status, elapsed_ms, assets, error, js_output}
        """
        if not self._browser:
            await self.start()
        assert self._browser is not None

        start_ts = time.monotonic()
        iso_ts = datetime.now(timezone.utc).isoformat()
        assets_captured = 0
        main_status: Optional[int] = None
        request_timings: dict[str, float] = {}

        context_kwargs: dict = {
            "ignore_https_errors": self.config.ignore_ssl,
            "user_agent": self.config.user_agent
            or (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Rased/1.2.0"
            ),
        }
        if self.config.proxy:
            context_kwargs["proxy"] = {"server": self.config.proxy}
        if self.config.extra_headers:
            context_kwargs["extra_http_headers"] = self.config.extra_headers

        context_kwargs["viewport"] = {"width": 1920, "height": 1080}
        context_kwargs["locale"] = "en-US"

        context = await self._browser.new_context(**context_kwargs)
        context.set_default_navigation_timeout(self.config.timeout_ms)
        context.set_default_timeout(self.config.timeout_ms)

        page = await context.new_page()

        def on_request(request):  # type: ignore
            try:
                request_timings[request.url] = time.monotonic()
            except Exception:
                pass

        page.on("request", on_request)

        async def on_response(response):  # type: ignore
            nonlocal assets_captured
            try:
                req = response.request
                resp_url = response.url
                method = req.method
                status = response.status
                req_headers = req.headers
                resp_headers = response.headers

                t0 = request_timings.get(resp_url)
                latency_ms = int((time.monotonic() - t0) * 1000) if t0 else None

                body: bytes = b""
                try:
                    body = await response.body()
                except Exception as body_err:
                    self.logger.debug(f"Could not read body for {resp_url}: {body_err}")
                    body = b""

                saved = await self.storage.save(
                    url=resp_url,
                    method=method,
                    request_headers=dict(req_headers),
                    status=status,
                    response_headers=dict(resp_headers),
                    body=body,
                    target_url=url,
                    latency_ms=latency_ms,
                    timestamp=iso_ts,
                )
                if saved:
                    assets_captured += 1
            except Exception as exc:
                self.logger.debug(f"Response handler error for {getattr(response, 'url', '?')}: {exc}")

        page.on("response", on_response)

        result: dict = {
            "url": url,
            "ok": False,
            "status": None,
            "elapsed_ms": 0,
            "assets": 0,
            "error": None,
            "js_output": None,
        }

        try:
            self.logger.url_start(url, worker_id)

            response = await page.goto(
                url,
                wait_until=self.config.wait_until,  # type: ignore
                timeout=self.config.timeout_ms,
            )

            if response:
                main_status = response.status
                result["status"] = main_status

            await asyncio.sleep(1.2)

            try:
                await page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass

            if self.config.javascript:
                js_result = await self._evaluate_js(page, url)
                result["js_output"] = js_result

            if main_status is not None and main_status >= 400:
                self.logger.url_done(
                    url,
                    str(main_status),
                    int((time.monotonic() - start_ts) * 1000),
                    assets_captured,
                    worker_id,
                )
                result["ok"] = True
            else:
                result["ok"] = True
                result["status"] = main_status or 200
                self.logger.url_done(
                    url,
                    str(result["status"]),
                    int((time.monotonic() - start_ts) * 1000),
                    assets_captured,
                    worker_id,
                )

        except PlaywrightTimeout:
            err = f"Navigation timeout after {self.config.timeout_ms}ms"
            self.logger.url_fail(url, err, worker_id)
            result["error"] = err
            result["ok"] = False
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            self.logger.url_fail(url, err, worker_id)
            result["error"] = err
            result["ok"] = False
        finally:
            elapsed = int((time.monotonic() - start_ts) * 1000)
            result["elapsed_ms"] = elapsed
            result["assets"] = assets_captured
            try:
                await context.close()
            except Exception:
                pass

        return result

    # ── JS evaluation ──────────────────────────────────────────────

    async def _evaluate_js(self, page, url: str) -> Optional[str]:
        """
        Evaluate user-supplied JS expression in page context.

        Safely serialises return values and catches exceptions.
        Output is routed through logger.js_output (stdout).
        """
        expr = self.config.javascript
        if not expr:
            return None

        wrapped = expr.strip()

        js_wrapper = f"""
        (() => {{
            try {{
                const __rased_result = (async () => {{ return ({wrapped}); }})();
                return __rased_result.then(
                    v => {{
                        try {{
                            if (v === undefined) return '__RASED_UNDEFINED__';
                            if (v === null) return 'null';
                            if (typeof v === 'object') {{
                                try {{ return JSON.stringify(v, null, 2); }}
                                catch(e) {{ return String(v); }}
                            }}
                            return String(v);
                        }} catch(e) {{ return 'Serialization error: ' + e.message; }}
                    }},
                    e => {{ throw e; }}
                );
            }} catch(e) {{
                throw e;
            }}
        }})()
        """

        try:
            raw = await page.evaluate(wrapped)
            if raw is None:
                output = "null"
            elif isinstance(raw, (dict, list)):
                try:
                    output = json.dumps(raw, indent=2, ensure_ascii=False)
                except Exception:
                    output = str(raw)
            else:
                output = str(raw)

            self.logger.js_output(url, f"Output: {output}")
            return output

        except Exception as first_err:
            try:
                raw2 = await page.evaluate(js_wrapper)
                if raw2 == "__RASED_UNDEFINED__":
                    output = "undefined"
                else:
                    output = str(raw2)
                self.logger.js_output(url, f"Output: {output}")
                return output
            except Exception as second_err:
                err_msg = str(second_err) or str(first_err)
                self.logger.js_error(url, err_msg)
                return None
