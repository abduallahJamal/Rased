"""
Worker pool & concurrency coordinator.

Implements a bounded worker-pool pattern using asyncio.Queue.
Workers pull URLs from the queue, respect delay, handle failures without
crashing the pool, and support graceful cancellation on SIGINT/SIGTERM.
"""

from __future__ import annotations

import asyncio
import signal
import time
from typing import List

from .browser import BrowserManager
from .config import RasedConfig
from .logger import RasedLogger


class WorkerPool:
    """
    Coordinates concurrent page fetches.

    Example:
        pool = WorkerPool(config, logger, browser_manager)
        results = await pool.run()
    """

    def __init__(self, config: RasedConfig, logger: RasedLogger, browser: BrowserManager) -> None:
        self.config = config
        self.logger = logger
        self.browser = browser

        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.results: List[dict] = []
        self._shutdown = asyncio.Event()
        self._total = 0

    # ── signal handling ────────────────────────────────────────────

    def _install_signal_handlers(self) -> None:
        """Register SIGINT/SIGTERM for graceful shutdown."""
        loop = asyncio.get_running_loop()

        def _handler(sig):  # type: ignore
            name = signal.Signals(sig).name if hasattr(signal.Signals(sig), "name") else str(sig)
            self.logger.warn(f"Received {name} — graceful shutdown initiated (press Ctrl+C again to force)...")
            self._shutdown.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handler, sig)
            except (ValueError, NotImplementedError, RuntimeError):
                try:
                    signal.signal(sig, lambda s, f: self._shutdown.set())  # type: ignore
                except Exception:
                    pass

    # ── single worker coroutine ────────────────────────────────────

    async def _worker(self, worker_id: int) -> None:
        """
        Worker loop: pull URL from queue, fetch, respect delay.
        Exits when queue is empty or shutdown is signalled.
        """
        while not self._shutdown.is_set():
            try:
                try:
                    url = await asyncio.wait_for(self.queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    if self.queue.empty():
                        if len(self.results) >= self._total and self._total > 0:
                            return
                        continue
                    continue
            except asyncio.CancelledError:
                return

            try:
                result = await self.browser.fetch(url, worker_id=worker_id)
                self.results.append(result)
            except asyncio.CancelledError:
                self.queue.task_done()
                raise
            except Exception as exc:
                self.logger.error(f"[W{worker_id}] Unhandled fetch error for {url}: {exc}")
                self.results.append({"url": url, "ok": False, "error": str(exc), "assets": 0})
            finally:
                self.queue.task_done()

            if self.config.delay_ms > 0:
                try:
                    await asyncio.wait_for(self._shutdown.wait(), timeout=self.config.delay_ms / 1000)
                    if self._shutdown.is_set():
                        return
                except asyncio.TimeoutError:
                    pass
                except asyncio.CancelledError:
                    return

    # ── public run ─────────────────────────────────────────────────

    async def run(self) -> List[dict]:
        """
        Enqueue all URLs and run the pool until drained or interrupted.

        Returns list of result dicts.
        """
        if not self.config.urls:
            self.logger.warn("No URLs to fetch — queue is empty")
            return []

        self._total = len(self.config.urls)
        self.logger.info(
            f"Enqueueing {self._total} URL(s) with concurrency={self.config.concurrency}, delay={self.config.delay_ms}ms"
        )

        for url in self.config.urls:
            await self.queue.put(url)

        self._install_signal_handlers()
        await self.browser.start()

        start = time.monotonic()

        workers = [
            asyncio.create_task(self._worker(i + 1), name=f"worker-{i + 1}")
            for i in range(self.config.concurrency)
        ]

        try:
            while not self._shutdown.is_set():
                if self.queue.empty() and len(self.results) >= self._total:
                    break
                if all(w.done() for w in workers):
                    break
                await asyncio.sleep(0.2)

            if self._shutdown.is_set():
                self.logger.warn("Cancelling remaining workers — finishing in-flight fetches...")
                try:
                    await asyncio.wait_for(self.queue.join(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass

            if not self._shutdown.is_set():
                try:
                    await asyncio.wait_for(self.queue.join(), timeout=self.config.timeout_ms / 1000 + 10)
                except asyncio.TimeoutError:
                    self.logger.warn("Queue join timed out — some tasks may not have completed")

        finally:
            for w in workers:
                if not w.done():
                    w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

        elapsed = time.monotonic() - start
        ok = sum(1 for r in self.results if r.get("ok"))
        failed = len(self.results) - ok
        total_assets = sum(r.get("assets", 0) for r in self.results)

        self.logger.summary(self._total, ok, failed, total_assets, elapsed)
        return self.results
