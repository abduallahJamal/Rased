<div align="center">

<img src="assets/banner.svg" alt="Rased — Headless Chromium Reconnaissance Engine" width="100%"/>

<br/>

**Production-grade headless Chromium reconnaissance engine + interactive web playground — intercepting every network resource, mirroring origin trees with `.meta` telemetry, and executing JavaScript in page context.**

[![CI](https://github.com/abduallahJamal/rased/actions/workflows/validate.yml/badge.svg?label=CI)](https://github.com/abduallahJamal/rased/actions/workflows/validate.yml)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Playwright](https://img.shields.io/badge/Playwright-Chromium-2EAD33?logo=playwright&logoColor=white)](rased/browser.py)
[![CLI](https://img.shields.io/badge/CLI-rased%20%7C%20page--fetch-00E5FF?logoColor=white)](#cli-reference)
[![Dashboard](https://img.shields.io/badge/Web_UI-Interactive_Playground-818CF8)](dashboard/server.py)
[![Security](https://img.shields.io/badge/Domain-Recon%20%26%20AppSec-22C55E)](#security-notes)
[![License: MIT](https://img.shields.io/badge/License-MIT-F59E0B.svg)](LICENSE)
[![Arabic Docs](https://img.shields.io/badge/%D8%A7%D9%84%D8%AA%D9%88%D8%AB%D9%8A%D9%82-%D8%A7%D9%84%D8%B9%D8%B1%D8%A8%D9%8A%D8%A9-1E293B)](README.ar.md)

**🇬🇧 English** · **[🇪🇬 العربية](README.ar.md)**

</div>

---

## 📌 Why Rased (`راصد`)?

Plain HTTP fetchers (`curl`, `httpx`, `wget`) only see the initial HTML shell — missing **lazy-loaded JavaScript bundles, dynamic XHR/fetch API calls, runtime DOM state, and Content-Security-Policy telemetry** rendered by modern SPAs. Inspired by Detectify's `page-fetch`, **Rased (`rased`)** drives a real headless **Playwright Chromium** pool with `asyncio` concurrency and an optional **interactive Web Playground**.

| Capability | Plain HTTP Crawlers (`curl` / `httpx`) | With **`rased`** (`Rased` Recon Engine) |
| :--- | :--- | :--- |
| **SPA & dynamic JS bundles** | Misses runtime chunks & lazy XHR calls | Full headless **Chromium** execution + `page.on("response")` capture |
| **Asset & header telemetry** | Raw body only or manual flags | Automatic `out/<host>/<path>` tree + JSON **`.meta` sidecars** (headers, CSP, status, latency) |
| **In-page JS inspection** | Impossible without a browser | `-j "<expr>"` evaluated in live page context (`stdout` prefixed with `[JS]` for grepping) |
| **Scope & noise control** | Manual post-filtering | Built-in `--no-third-party`, `--third-party`, `--include`, and `--exclude` filters |
| **Proxy & Burp/ZAP routing** | Per-tool proxy quirks | Native `-p http://127.0.0.1:8080 -k` (HTTP & SOCKS5 + TLS ignore) |
| **Interactive exploration** | CLI only | Built-in **Web Playground & API** (`rased-dashboard` / `dashboard/server.py`) |

---

## 🧩 Core Subsystems

### ⚡ `rased/cli.py` & `rased/worker.py` — Asyncio Worker Pool & Unix Piping
Accepts targets via `stdin` pipe (`cat urls.txt | rased`), `-f urls.txt`, or positional arguments with automatic scheme normalisation and order-preserving deduplication. Coordinates `-c` concurrent workers with `-d` per-worker rate-limiting and clean `SIGINT`/`SIGTERM` Chromium teardown. Installs `rased` alongside drop-in aliases `page-fetch` and `pfetch`.

### 🌐 `rased/browser.py` — Isolated Chromium Contexts & Network Interception
Creates an isolated `BrowserContext` per target (custom User-Agent, HTTP/SOCKS5 proxy, TLS ignore), hooks every `request`/`response` lifecycle event to measure millisecond latency, waits for `networkidle`, and safely serialises synchronous or `Promise`-returning JavaScript expressions (`-j`).

### 🗂️ `rased/storage.py` & `rased/utils.py` — Sanitized Origin Mirroring + `.meta` Sidecars
Reconstructs remote paths safely under `out/<host>/<path>` (folding query strings cleanly and blocking path traversal), supports atomic incremental naming (`app.1.js`, `app.2.js`) or `--overwrite`, and writes a structured `.meta` JSON companion file for every captured asset.

### 🖥️ `dashboard/server.py` & `dashboard/index.html` — Interactive Recon Playground
Zero-dependency dark-mode web UI and REST bridge (`POST /api/fetch`, `GET /api/health`, `GET /api/history`) for running live sandboxed fetches, browsing captured asset trees, inspecting `.meta` headers/CSP, and testing JavaScript extraction snippets visually.

---

## 🔄 Architecture & Data Flow

```text
stdin / -f file / args  ──►  CLI Parser (cli.py)  ──►  RasedConfig (validated + deduped)
                                                               │
                                                ┌──────────────┴──────────────┐
                                                │     WorkerPool (-c N, -d)   │
                                                │   ┌──────┐ ┌──────┐ ┌─────┐ │
                                                └───┤  W1  ├─┤  W2  ├─┤ W3  ├─┘
                                                    └──┬───┘ └──┬───┘ └──┬──┘
                                                       │        │        │
                                              BrowserManager (Playwright Chromium)
                                                       │
                                      ┌────────────────┴────────────────┐
                                      ▼                                 ▼
                         page.on("response") hook             page.evaluate(-j expr)
                                      │                                 │
                              StorageHandler                   [JS] [URL] Output: ...
                                      │                              (stdout)
                         out/<host>/<path> + .meta
```

---

## 🚀 Installation

### 1. Clone & install package

```bash
git clone https://github.com/abduallahJamal/rased.git
cd rased

python3 -m venv .venv
source .venv/bin/activate

# Install rased CLI (+ page-fetch / pfetch aliases)
pip install -e .

# Install headless Chromium via Playwright
playwright install chromium
# On fresh Linux servers (installs OS libraries too):
playwright install --with-deps chromium
```

> **System Chrome fallback:** Set `CHROME_PATH=/usr/bin/google-chrome` (or `CHROMIUM_PATH`) to use an existing browser binary instead of Playwright's bundled Chromium.

---

## ⚡ Quick Start

### 1. Pipe from `stdin` (subfinder / httpx / waybackurls friendly)

```bash
echo "https://example.com" | rased
cat examples/urls.txt | rased -o recon -c 5 --no-third-party -v
```

### 2. Scope & MIME filtering

```bash
# Skip heavy media & fonts
cat urls.txt | rased --exclude "image/" --exclude "font/" -o recon

# Capture JavaScript bundles & sourcemaps only
cat urls.txt | rased --include ".js" --include "javascript" -o js-loot

# Collect external third-party CDNs & trackers only
cat urls.txt | rased --third-party -o thirdparty
```

### 3. In-page JavaScript telemetry (`-j`)

```bash
echo "https://example.com" | rased -j "document.title"
echo "https://example.com" | rased -j "Array.from(document.scripts).map(s=>s.src)"
echo "https://example.com" | rased -j "JSON.stringify(performance.getEntries().map(e=>e.name))"
```

`stdout` receives clean `[JS]` lines while progress logs stay on `stderr`, making piping into `grep` or `jq` effortless:

```text
[JS] [https://example.com] Output: Example Domain
```

### 4. Route through Burp Suite / OWASP ZAP

```bash
rased -f urls.txt -p http://127.0.0.1:8080 -k -o burp-mirror
```

### 5. Launch the Interactive Web Playground

```bash
rased-dashboard
# or: PORT=8787 python3 dashboard/server.py
```

Then open `http://localhost:8787` in your browser. See more workflows in **[English Usage Examples](docs/usage-examples.en.md)**, **[أمثلة الاستخدام بالعربية](docs/usage-examples.md)**, and **[JS Extraction Recipes](examples/js-snippets.md)**.

---

## 📖 CLI Reference

```text
usage: rased [-h] [-f PATH] [URL ...] [-c N] [-d MS] [-t MS]
             [--wait-until {load,domcontentloaded,networkidle,commit}]
             [--exclude STR] [--include STR]
             [--no-third-party] [--third-party]
             [-j EXPR] [-p URL] [-k] [-A UA]
             [-o DIR] [-w] [-v] [--headed] [--version]

input:
  -f, --file PATH          File containing URLs (one per line, # comments ignored)
  URL                      Target URLs (also accepted via stdin pipe)

concurrency & timing:
  -c, --concurrency N      Number of concurrent workers (default: 3)
  -d, --delay MS           Delay between requests per worker in ms (default: 0)
  -t, --timeout MS         Page navigation timeout in ms (default: 30000)
  --wait-until COND        load | domcontentloaded | networkidle | commit

filtering & scope:
  --exclude STR            Exclude by MIME/URL substring (repeatable)
  --include STR            Whitelist by MIME/extension (repeatable)
  --no-third-party         Save only target host & its subdomains
  --third-party            Save only external third-party hosts

javascript execution:
  -j, --javascript EXPR    Evaluate JS expression in page context -> stdout

network & proxy:
  -p, --proxy URL          Upstream proxy (http://host:port or socks5://host:port)
  -k, --insecure           Ignore TLS/SSL errors (for Burp/ZAP interception)
  -A, --user-agent UA      Custom User-Agent header

output & misc:
  -o, --output DIR         Output directory (default: ./out)
  -w, --overwrite          Overwrite existing files instead of script.1.js
  -v, --verbose            Log every saved/skipped asset
  --headed                 Run Chromium in visible headed mode
  --version                Print version
```

---

## 📂 Mirrored Output & `.meta` Telemetry Schema

```text
out/
└── example.com/
    ├── index.html
    ├── index.html.meta          # Request/response headers, status, latency, size
    ├── assets/
    │   ├── app.3a7f2.js
    │   └── app.3a7f2.js.meta
    └── api/
        ├── config.json
        └── config.json.meta
```

Example `.meta` sidecar:

```json
{
  "url": "https://example.com/assets/app.3a7f2.js",
  "method": "GET",
  "request_headers": {
    "user-agent": "Mozilla/5.0 ... Rased/1.2.0",
    "accept": "*/*"
  },
  "response": {
    "status": 200,
    "headers": {
      "content-type": "application/javascript",
      "content-security-policy": "default-src 'self'",
      "cache-control": "max-age=31536000"
    }
  },
  "timestamp": "2026-10-24T08:30:00.000Z",
  "latency_ms": 87,
  "saved_to": "out/example.com/assets/app.3a7f2.js",
  "size_bytes": 48291,
  "target_url": "https://example.com"
}
```

---

## 🔒 Security Notes

- **Authorized testing only:** Use `rased` strictly against targets you own or have explicit written permission to test (authorized assessments & bug-bounty scopes).
- **TLS verification (`-k`):** Enable `-k` / `--insecure` only when routing through trusted local intercepting proxies such as Burp Suite or OWASP ZAP.
- **Path-traversal protection:** Every mirrored host, path segment, and query string is sanitised via `rased/utils.py` (`..` segments stripped, unsafe characters collapsed) before writing to disk.
- **JavaScript evaluation (`-j`):** Expressions run inside the target page context — never interpolate untrusted shell input directly into `-j`.

---

## 📁 Repository Structure

```text
rased/
├── rased/
│   ├── __init__.py              # Package version & RasedConfig export
│   ├── __main__.py              # python -m rased entry point
│   ├── cli.py                   # CLI parser + async_main orchestration
│   ├── config.py                # RasedConfig dataclass, validation & scope filters
│   ├── logger.py                # Rich structured logger (stderr logs / stdout [JS])
│   ├── utils.py                 # URL -> path mirroring, sanitisation & incremental naming
│   ├── storage.py               # Async StorageHandler + .meta sidecar writer
│   ├── browser.py               # BrowserManager — Playwright Chromium + interception
│   └── worker.py                # WorkerPool — asyncio.Queue + graceful SIGINT/SIGTERM
├── dashboard/
│   ├── index.html               # Interactive dark-mode Recon Playground UI
│   └── server.py                # REST API bridge (/api/fetch, /api/health, /api/history)
├── examples/
│   ├── js-snippets.md           # Ready-to-run JS extraction & fingerprinting recipes
│   └── urls.txt                 # Demo target list
├── docs/
│   ├── usage-examples.en.md     # Recon & AppSec pipeline examples (English)
│   └── usage-examples.md        # أمثلة مسارات الاستطلاع والفحص الأمني (العربية)
├── tests/
│   └── test_rased.py            # Automated pytest suite (config, utils, storage, CLI, API)
├── scripts/
│   ├── validate.py              # CI repository & link validator
│   └── publish.sh               # Validation + test runner helper
├── assets/
│   └── banner.svg               # Repository header banner
├── pyproject.toml               # Hatchling build & CLI script entry points
├── Makefile                     # Common dev & demo shortcuts
└── LICENSE                      # MIT License
```

---

## 🤝 Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Before opening a pull request, run:

```bash
python3 scripts/validate.py
pytest -v
```

---

## 📄 License

Released under the [MIT License](LICENSE) © 2026 Abduallah Jamal.
