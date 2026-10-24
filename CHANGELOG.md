# Changelog

All notable changes to **Rased (`rased`)** are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-10-24

### Added
- Rebranded core package and CLI as **`rased`** (`Rased — راصد`) while retaining `page-fetch` and `pfetch` CLI aliases and `PageFetchConfig`/`PageFetchLogger` imports for backward compatibility.
- Added `rased-dashboard` entry point and `create_server()` helper in `dashboard/server.py` for the interactive Recon Playground UI.
- Added full bilingual documentation (`README.md` + `README.ar.md` + `docs/usage-examples.en.md` + `docs/usage-examples.md`) and custom `assets/banner.svg`.
- Added automated `pytest` suite (`tests/test_rased.py`), repository validator (`scripts/validate.py`), and GitHub Actions CI workflow (`.github/workflows/validate.yml`).

### Fixed
- Hardened `url_to_local_path()` in `rased/utils.py` to strip `..` segments and sanitise hostnames strictly against path traversal.
- Eliminated duplicate per-URL console lines in `dashboard/server.py` when streaming logs to the Playground UI.
