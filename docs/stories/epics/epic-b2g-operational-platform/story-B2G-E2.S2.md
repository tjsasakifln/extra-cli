---
story_id: B2G-E2.S2
title: "Source discovery + aquisição pública PNCP/CIGA/DOE-SC → ESR"
status: InProgress
priority: P0
risk_level: STANDARD
effort: L
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E2
depends_on: [B2G-E2.S1]
blocks: [B2G-E2.S4, B2G-E1.S2]
adr: [ADR-019, ADR-021, ADR-020]
---

# Story B2G-E2.S2: Discovery PNCP/CIGA + escrita ESR

## Contexto

Sessões manuais já provaram ingestão CIGA DOM, SC Compras e PNCP SC. Falta **pipeline de discovery** que atualize o ESR com `evidence_ref`, `external_org_id` e confidence — sem inflar M1/M2 indevidamente.

## Valor de negócio

Converte unknown→applicable com prova; alimenta M2 e coletas target-set.

## Escopo

**IN:** Jobs de discovery para PNCP (org/CNPJ match) e CIGA (publicações/órgãos); writers ESR; raw em output/; fail-closed se fetch rate_limited.

**OUT:** Todos os portais residuais; M2≥95%. A API autenticada de publicação
do DOE não é dependência da leitura pública.

## Acceptance Criteria

1. **AC1**  
   **Given** ESR bootstrap,  
   **When** discovery PNCP roda em modo sample ou full SC,  
   **Then** atualiza bindings `pncp` com external_org_id/confidence e `evidence_ref` de run_id.

2. **AC2**  
   **Given** artefatos/publicações CIGA,  
   **When** discovery CIGA roda,  
   **Then** bindings `ciga_dom` ou fonte canônica CIGA marcados applicable onde match entidade ≥ threshold.

3. **AC3**  
   **Given** HTTP 429 no discovery,  
   **When** job termina,  
   **Then** status `rate_limited`, **sem** marcar success coverage para fatia afetada (ADR-021).

4. **AC4**  
   **Given** raw JSONL,  
   **When** job grava,  
   **Then** path sob `output/` gitignored (ADR-020); summary opcional stamp.

5. **AC5**  
   **Given** match ambíguo,  
   **When** binding escrito,  
   **Then** confidence=low e não promove sozinho a “covered” sem evidence success de crawl.

6. **AC6 — DOE-SC público sem credencial**
   **Given** os datasets oficiais `Diário Oficial SC - Publicações/Edições`,
   **When** o adapter CKAN público executa,
   **Then** descobre e baixa CSV sem login, preserva raw+SHA-256, normaliza atos
   relevantes e marca freshness como gap quando o recurso estiver fora do SLA.

7. **AC7 — identidade segura**
   **Given** CNPJ raiz associado a múltiplas entidades,
   **When** promoção por evidência executa,
   **Then** nenhuma entidade é promovida sem identificador adicional inequívoco.

## Fontes de dados

- PNCP API (consulta)
- CIGA DOM publications / CKAN se aplicável
- ESR (E2.S1)
- Universo 1093

## Dependências

B2G-E2.S1 (ESR)

## Riscos

| Risco | Mitigação |
|-------|-----------|
| False positive match nome | Preferir CNPJ; threshold |
| Rate limit PNCP | Pacing + fail-closed |
| Confundir discovery com commercial signal | Só toca ESR/applicability |

## Testes

- Unit: matcher + writer
- Integration smoke: 1 página PNCP → ≥0 updates com evidence_ref
- Contract: 429 fixture → não success

## Evidência

- `docs/ops/session-b2g-platform-2026-07-17/LIVE-SOURCE-EVIDENCE.json`
- CIGA run `ciga-dom-20260717T125842Z-cf9890803b`
- DOE run `doe-public-20260717T125621Z-45de2aa780`
- Persistência: `output/session-evidence/official-acts-load-20260717.json`

## Definition of Done

- [ ] AC1–3 PNCP/CIGA binding completo (parcial; promoção estrita ainda 0)
- [x] AC4–7: política raw, match ambíguo fail-closed, DOE público e identidade segura
- [x] Documentado comando Tiago/ops
- [x] File list

## Comandos de validação

```bash
pytest tests/ -k "discovery or esr_pncp or esr_ciga" -v
# Exemplos operacionais (ajustar ao entrypoint real):
# python scripts/crawl/monitor.py --source pncp --mode incremental
# python -m scripts.registry.esr discover --source pncp --uf SC
# python -m scripts.registry.esr discover --source ciga_dom
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | InProgress |
| 2026-07-17 | River (SM) | AC6–7 refinados; DOE público e identidade fail-closed |
| 2026-07-17 | Dex (Dev) | DOE/DOM públicos executados; story permanece InProgress pelos AC1–3 |

## File List

- `scripts/crawl/doe_sc_publications.py`
- `scripts/crawl/ciga_dom_publications.py`
- `scripts/crawl/ingestion/load_official_acts_session.py`
- `scripts/source_registry/acquisition/promote_from_evidence.py`
- `scripts/source_registry/persistence.py`
- `db/migrations/052_official_acts.sql`
- `db/migrations/053_entity_source_registry.sql`
- `tests/test_doe_sc_publications.py`
- `tests/test_load_official_acts_session.py`
- `tests/unit/source_registry/test_promote_from_evidence.py`
