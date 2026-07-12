---
name: story-cover1.11-geocoding
description: Story COVERAGE-1.11 — Geocoding 604 entities sem coordenadas via IBGE API + Nominatim — 30 tests, ruff clean
metadata:
  type: project
---

**Story COVERAGE-1.11 (Geocoding)** implemented 2026-07-11. Created `scripts/lib/geocode.py` (Geocoder class with 3-level geocoding: cache/IBGE/Nominatim, corrected Haversine with radians, SC bounding box), `scripts/fix/geocode_missing_entities.py` (executable fix script with --dry-run/--commit/--report-only, ALTER TABLE ADD geocode_method, entity report), and `tests/test_geocode.py` (30 tests). Legacy cache format in `data/geocode_cache.json` auto-migrated. Status: InReview.

**Why:** 604 of 2,085 SC public entities had NULL coordinates, making `raio_200km=FALSE` for all of them (incorrectly excluding them from 200km radius filters).

**How to apply:** Run `python scripts/fix/geocode_missing_entities.py --dry-run` to simulate, then `--commit` to persist. The cache groups by municipio (295 max Nominatim calls, not 604).
