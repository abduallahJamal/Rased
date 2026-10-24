# Rased (`rased`) — Recon & AppSec Usage Examples

**[🇪🇬 النسخة العربية](usage-examples.md)** · **[⬅ Back to README](../README.md)**

---

## 1. Subdomain Pipeline (`subfinder` → `httpx` → `rased`)

Pipe live hosts directly from discovery tools into `rased` to capture full SPA assets and security headers:

```bash
subfinder -d example.com -silent \
  | httpx -silent \
  | rased -c 5 -d 250 --no-third-party --exclude "image/" --exclude "font/" -o recon-example -v
```

---

## 2. JavaScript Bundle Harvesting for Endpoint & Secret Analysis

Collect only first-party JavaScript bundles across a list of targets, then scan locally with `ripgrep` or `semgrep`:

```bash
rased -f targets.txt --no-third-party --include ".js" --include "javascript" -o js-mirror
rg -n "(api/v[0-9]+|graphql|Bearer |NEXT_PUBLIC_)" js-mirror/
```

---

## 3. Content-Security-Policy (CSP) & Header Audit via `.meta` Sidecars

Every saved resource includes a `.meta` JSON file containing full response headers:

```bash
echo "https://example.com" | rased -o audit --no-third-party
jq -r 'select(.response.headers["content-security-policy"] == null) | .url' audit/**/*.meta
```

---

## 4. Feeding Burp Suite / OWASP ZAP Site Maps Automatically

Populate Burp Suite's Target Site Map with real headless Chromium traffic (including lazy XHR requests):

```bash
rased -f scope-urls.txt -c 3 -d 400 -p http://127.0.0.1:8080 -k -o burp-session
```

---

## 5. Third-Party Supply-Chain & Tracker Inventory

Map all external CDNs, analytics scripts, and third-party iframes loaded by your web properties:

```bash
rased -f production-apps.txt --third-party -o thirdparty-audit -v
```

---

## 6. Interactive Web Playground (`rased-dashboard`)

Start the visual Recon Playground locally on port `8787` (or a custom `PORT`):

```bash
PORT=8787 rased-dashboard
```

Open `http://localhost:8787` to run sandboxed Chromium fetches, inspect the asset tree, view `.meta` JSON telemetry, and test `-j` JavaScript expressions interactively.
