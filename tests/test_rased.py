"""
Unit & HTTP endpoint tests for Rased (راصد).
"""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

import pytest

from dashboard.server import create_server
from rased import PageFetchConfig, RasedConfig, __version__
from rased.cli import parse_config
from rased.logger import PageFetchLogger, RasedLogger
from rased.storage import StorageHandler
from rased.utils import format_bytes, get_host, get_origin, incremental_path, sanitise_filename, url_to_local_path


# ── Config validation & filtering ──────────────────────────────────


def test_config_normalises_and_deduplicates_urls():
    cfg = RasedConfig(urls=["example.com", "https://example.com", "http://sub.example.com/a", "  "])
    cfg.validate()
    assert cfg.urls == ["https://example.com", "http://sub.example.com/a"]
    assert PageFetchConfig is RasedConfig
    assert PageFetchLogger is RasedLogger


def test_config_rejects_invalid_values():
    with pytest.raises(ValueError, match="concurrency"):
        RasedConfig(urls=["https://example.com"], concurrency=0).validate()

    with pytest.raises(ValueError, match="delay"):
        RasedConfig(urls=["https://example.com"], delay_ms=-1).validate()

    with pytest.raises(ValueError, match="timeout"):
        RasedConfig(urls=["https://example.com"], timeout_ms=500).validate()

    with pytest.raises(ValueError, match="mutually exclusive"):
        RasedConfig(urls=["https://example.com"], no_third_party=True, third_party=True).validate()


def test_config_scope_and_mime_filtering():
    cfg = RasedConfig(
        urls=["https://target.com"],
        include=["javascript", ".json"],
        exclude=["vendor"],
        no_third_party=True,
    )
    cfg.validate()

    # Matching same-site JS passes
    ok, _ = cfg.should_save("application/javascript .js https://api.target.com/app.js", "api.target.com", "target.com")
    assert ok is True

    # Excluded substring blocked
    ok, reason = cfg.should_save(
        "application/javascript .js https://target.com/vendor.js", "target.com", "target.com"
    )
    assert ok is False and "exclude" in reason

    # Non-whitelisted MIME blocked
    ok, reason = cfg.should_save("image/png .png https://target.com/logo.png", "target.com", "target.com")
    assert ok is False and "include" in reason

    # External CDN blocked under --no-third-party
    ok, reason = cfg.should_save(
        "application/javascript .js https://cdn.other.io/app.js", "cdn.other.io", "target.com"
    )
    assert ok is False and "no-third-party" in reason

    # --third-party inverse check
    tp_cfg = RasedConfig(urls=["https://target.com"], third_party=True)
    ok_same, _ = tp_cfg.should_save("text/javascript https://target.com/a.js", "target.com", "target.com")
    ok_ext, _ = tp_cfg.should_save("text/javascript https://cdn.other.io/a.js", "cdn.other.io", "target.com")
    assert ok_same is False
    assert ok_ext is True


# ── URL mirroring & path sanitisation ──────────────────────────────


def test_url_to_local_path_mirroring_and_traversal_safety(tmp_path: Path):
    p_root = url_to_local_path("https://example.com/", tmp_path)
    assert p_root == tmp_path / "example.com" / "index.html"

    p_asset = url_to_local_path("https://example.com:8443/assets/app.3a7f.js?v=1&env=prod", tmp_path)
    assert p_asset == tmp_path / "example.com_8443" / "assets" / "app.3a7f_v_1_env_prod.js"

    p_trav = url_to_local_path("https://example.com/../../etc/passwd", tmp_path)
    assert tmp_path in p_trav.parents
    assert ".." not in p_trav.parts


def test_utils_helpers(tmp_path: Path):
    assert get_host("https://Sub.Example.COM:8080/test") == "sub.example.com"
    assert get_origin("https://example.com:8080/test") == "https://example.com"
    assert sanitise_filename("../../../weird name?!.js") == "weird_name_.js"
    assert format_bytes(512) == "512 B"
    assert format_bytes(2048) == "2.0 KB"

    f = tmp_path / "script.js"
    assert incremental_path(f) == f
    f.write_text("1", encoding="utf-8")
    f1 = incremental_path(f)
    assert f1 == tmp_path / "script.1.js"
    f1.write_text("2", encoding="utf-8")
    assert incremental_path(f) == tmp_path / "script.2.js"


# ── Async StorageHandler + .meta sidecar ───────────────────────────


@pytest.mark.asyncio
async def test_storage_handler_writes_body_and_meta(tmp_path: Path):
    cfg = RasedConfig(urls=["https://example.com"], output=tmp_path, overwrite=False)
    cfg.validate()
    logger = RasedLogger(verbose=False, use_color=False)
    storage = StorageHandler(cfg, logger)
    await storage.ensure_output_dir()

    saved1 = await storage.save(
        url="https://example.com/assets/main.js",
        method="GET",
        request_headers={"user-agent": f"Rased/{__version__}"},
        status=200,
        response_headers={"content-type": "application/javascript"},
        body=b"console.log('ok');",
        target_url="https://example.com",
        latency_ms=42,
    )
    assert saved1 is not None and saved1.exists()
    meta1 = Path(str(saved1) + ".meta")
    assert meta1.exists()
    meta_json = json.loads(meta1.read_text(encoding="utf-8"))
    assert meta_json["status"] if "status" in meta_json else meta_json["response"]["status"] == 200
    assert meta_json["latency_ms"] == 42
    assert meta_json["size_bytes"] == 18

    # Second save without overwrite creates incremental main.1.js
    saved2 = await storage.save(
        url="https://example.com/assets/main.js",
        method="GET",
        request_headers={},
        status=200,
        response_headers={"content-type": "application/javascript"},
        body=b"console.log('v2');",
        target_url="https://example.com",
    )
    assert saved2 == tmp_path / "example.com" / "assets" / "main.1.js"
    assert storage.summary()["saved"] == 2


# ── CLI parser ─────────────────────────────────────────────────────


def test_cli_parse_config_flags(tmp_path: Path):
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text("# comment\nexample.org\nhttps://sub.example.org/login\n", encoding="utf-8")

    cfg = parse_config(
        [
            "-f",
            str(urls_file),
            "https://extra.example.org",
            "-c",
            "5",
            "-d",
            "250",
            "-t",
            "15000",
            "--exclude",
            "image/",
            "-j",
            "document.title",
            "-p",
            "http://127.0.0.1:8080",
            "-k",
            "-o",
            str(tmp_path / "recon"),
            "-w",
            "-v",
        ]
    )
    assert len(cfg.urls) == 3
    assert cfg.concurrency == 5
    assert cfg.delay_ms == 250
    assert cfg.timeout_ms == 15000
    assert cfg.exclude == ["image/"]
    assert cfg.javascript == "document.title"
    assert cfg.proxy == "http://127.0.0.1:8080"
    assert cfg.ignore_ssl is True
    assert cfg.overwrite is True
    assert cfg.verbose is True


# ── Dashboard HTTP server endpoints ────────────────────────────────


def test_dashboard_health_and_static_ui():
    server = create_server("127.0.0.1", 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "ok"
            assert data["name"] == "rased"
            assert data["version"] == __version__

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:
            html = resp.read().decode("utf-8")
            assert "Rased (راصد)" in html
            assert "RASED" in html
    finally:
        server.shutdown()
        server.server_close()
