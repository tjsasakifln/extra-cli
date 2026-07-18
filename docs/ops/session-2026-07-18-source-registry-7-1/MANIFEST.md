# Evidence DoD §7.1 registry (first 8 items)

**Story:** ROI-cand-dyn-slice-6c08d1a1d808
**Module:** scripts/crawl/registry.py

| Item | Proof |
|------|-------|
| registry canônico | scripts/crawl/registry.py + export |
| id estável | SourceInfo.name unique |
| URL canônica | canonical_url per source |
| capacidades | capabilities list |
| cobertura geográfica | geo_coverage |
| credenciais | needs_credentials + credential_names |
| paginação | pagination_limits |
| rate limits | rate_limits |

```bash
python3 -m scripts.crawl.registry --validate --json
python3 -m pytest tests/test_source_registry_dod71.py -q --no-cov -o addopts=
```
