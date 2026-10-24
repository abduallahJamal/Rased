"""
Rased (راصد) — Production-grade headless Chromium reconnaissance engine.

Inspired by Detectify's page-fetch, built with Playwright & asyncio.
"""

__version__ = "1.2.0"
__author__ = "Abduallah Jamal"

from .config import PageFetchConfig, RasedConfig

__all__ = ["RasedConfig", "PageFetchConfig", "__version__", "__author__"]
