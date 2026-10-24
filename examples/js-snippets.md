# JS Extraction Recipes — Rased (راصد)

Run any of these with `-j "<expr>"`:

## Basic

```bash
echo "https://target.com" | rased -j "document.title"
echo "https://target.com" | rased -j "document.documentElement.outerHTML.slice(0,2000)"
```

## Script & Asset Harvesting

```bash
# All script sources
echo "https://target.com" | rased -j "Array.from(document.scripts).map(s=>s.src)"

# All link hrefs
echo "https://target.com" | rased -j "Array.from(document.links).map(a=>a.href).slice(0,20)"

# All forms + HTTP methods
echo "https://target.com" | rased -j "Array.from(document.forms).map(f=>({action:f.action, method:f.method}))"
```

## Telemetry & Endpoints

```bash
# Performance entries (XHR, fetch, assets)
echo "https://target.com" | rased -j "JSON.stringify(performance.getEntries().map(e=>({name:e.name, type:e.entryType})).slice(0,10), null, 2)"

# localStorage / sessionStorage keys & values
echo "https://target.com" | rased -j "JSON.stringify(Object.entries(localStorage))"

# Inline secrets / token heuristics
echo "https://target.com" | rased -j "document.documentElement.innerHTML.match(/(api[_-]?key|secret|token)[^\\n]{0,40}/gi)"

# Accessible non-HttpOnly cookies
echo "https://target.com" | rased -j "document.cookie"
```

## Framework & Bundle Fingerprinting

```bash
echo "https://target.com" | rased -j "({react: !!window.React, vue: !!window.Vue, angular: !!window.angular, jquery: !!window.jQuery})"
echo "https://target.com" | rased -j "Object.keys(window).filter(k=>k.toLowerCase().includes('webpack')).slice(0,5)"
```
