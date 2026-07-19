# HANDOFF — EXTRA-OPS-95-FOUNDATION (PARTIAL)

**UTC:** 2026-07-19T08:00Z  
**Branch:** `campaign/extra-ops-95-20260719`  
**HEAD:** `760ce38+` (see `git log -1`)  
**Status:** PARTIAL — not DONE

## First command for next agent

```bash
cd "/mnt/d/extra consultoria"
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
git checkout campaign/extra-ops-95-20260719
cat docs/ops/campaigns/EXTRA-OPS-95/STATUS.md
cat docs/ops/campaigns/EXTRA-OPS-95/evidence/session-metrics.json
```

## Must-read documents

1. `docs/ops/campaigns/EXTRA-OPS-95/STATUS.md`
2. `docs/ops/campaigns/EXTRA-OPS-95/evidence/session-metrics.json`
3. `docs/ops/campaigns/EXTRA-OPS-95/evidence/M2-cnpj14/residual-identity-classification.json`
4. `docs/ops/campaigns/EXTRA-OPS-95/evidence/M2-cnpj14/purge-token-mismatch.json`
5. `DOD.md` (current checkboxes)
6. `extra-consultoria-plano-executivo.html` (panel `#metric-lineage-ops95`)

## Honest metrics

| Metric | Value |
|--------|------:|
| DOD | 270/1352 (~20%) |
| Editais presence | 285/1093 (26.1%) |
| Contracts presence | 368/1093 (33.7%) |
| Contracts SZ entities | 623 |
| Ops proxy contracts | 991/1093 (90.67%) |
| Gap to 95% ops proxy | 48 |
| Residual without ops | 102 (identity blocker) |

## Do NOT repeat

1. **Do not** use `token_containment` without cnpj8 root match (purged false SZ).
2. **Do not** claim publicacao `cnpjOrgao` filters correctly — it ignores filter.
3. **Do not** auto-write success_zero without verified cnpj14 root == entity cnpj8.
4. **Do not** invent CNPJ branch digits beyond verified matriz 0001+DV + PNCP 200.
5. **Do not** treat ops proxy as 7-stage operational coverage.
6. **Do not** re-open N01; N09 remains BLOCKED_SOURCE.
7. **Do not** merge PR #28 as campaign success.

## Tools that work

```bash
python3 -m scripts.ops.resolve_cnpj14_matriz --limit 100 --write --delay 0.6
python3 -m scripts.ops.probe_entity_success_zero --data-type contracts --limit 50 --write --delay 1.3
python3 -m scripts.crawl.monitor --source contracts --mode full --dsn "$LOCAL_DATALAKE_DSN"
```

## Next high-value fronts (extra-roi)

1. **Residual 102 identity:** official CNPJ resolution (Receita/OpenCNPJ with full cnpj if found) or formal NOT_APPLICABLE policy with human owner for banks/SAs not on PNCP.
2. **Editais presence:** multi-source TCE/DOM/historical SC; fix content_hash uniqueness in upsert; longer windows under rate limit.
3. **DOD → 55%:** only evidence-backed flips; many NFR/CI/VPS items remain open legitimately.
4. **N09 gold sample** independent or keep BLOCKED_SOURCE.
5. Independent QA + skeptic pass before any DONE claim.

## Active processes

- Contracts monitor may be running (`/tmp/extra-ops-contracts.pid`) — check before starting another.

## Veredito

**PARTIAL** — material progress (ops proxy 90.7%, identity hygiene, DOD ~20%), gates 55%/95% editais/recall/N09 not met.
