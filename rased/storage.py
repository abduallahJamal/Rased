"""
Storage handler — mirrors remote URL tree locally and writes .meta sidecars.

Responsibilities:
  • Reconstruct URL → local Path (origin + path segments)
  • Apply filtering rules (include / exclude / scope)
  • Write raw response body + JSON .meta file
  • Handle overwrite vs incremental naming atomically
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import aiofiles

from .config import RasedConfig
from .logger import RasedLogger
from .utils import get_host, incremental_path, url_to_local_path


class StorageHandler:
    """
    Async file-system writer. One instance shared across workers
    (internal lock serialises incremental naming).
    """

    def __init__(self, config: RasedConfig, logger: RasedLogger) -> None:
        self.config = config
        self.logger = logger
        self._lock = asyncio.Lock()
        self.saved_count = 0  # global counter

    async def save(
        self,
        url: str,
        method: str,
        request_headers: dict,
        status: int,
        response_headers: dict,
        body: bytes,
        target_url: str,
        latency_ms: Optional[int] = None,
        timestamp: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Persist a single intercepted response.

        Returns the local Path if saved, None if skipped by filters.
        """
        mime = response_headers.get("content-type", "") or response_headers.get("Content-Type", "")
        ext_token = Path(urlparse(url).path).suffix.lower()
        haystack = f"{mime} {ext_token} {url}"

        target_host = get_host(target_url)
        request_host = get_host(url)

        should, reason = self.config.should_save(haystack, request_host, target_host)
        if not should:
            self.logger.asset_skipped(url, reason)
            return None

        local_path = url_to_local_path(url, self.config.output)

        async with self._lock:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.config.overwrite and local_path.exists():
                local_path = incremental_path(local_path)

            try:
                async with aiofiles.open(local_path, "wb") as fh:
                    await fh.write(body)
            except OSError as exc:
                self.logger.error(f"Failed to write {local_path}: {exc}")
                return None

            meta_path = Path(str(local_path) + ".meta")

            if timestamp is None:
                timestamp = datetime.now(timezone.utc).isoformat()

            meta = {
                "url": url,
                "method": method.upper(),
                "request_headers": request_headers,
                "response": {
                    "status": status,
                    "headers": response_headers,
                },
                "timestamp": timestamp,
                "latency_ms": latency_ms,
                "saved_to": str(local_path),
                "size_bytes": len(body),
                "target_url": target_url,
            }

            try:
                async with aiofiles.open(meta_path, "w", encoding="utf-8") as fh:
                    await fh.write(json.dumps(meta, indent=2, ensure_ascii=False))
            except OSError as exc:
                self.logger.error(f"Failed to write meta {meta_path}: {exc}")

        self.saved_count += 1
        self.logger.asset_saved(str(local_path.relative_to(self.config.output)), status, mime or "unknown")
        return local_path

    async def ensure_output_dir(self) -> None:
        """Create base output directory."""
        self.config.output.mkdir(parents=True, exist_ok=True)
        self.logger.debug(f"Output directory: {self.config.output.resolve()}")

    def summary(self) -> dict:
        return {"saved": self.saved_count, "output": str(self.config.output.resolve())}
