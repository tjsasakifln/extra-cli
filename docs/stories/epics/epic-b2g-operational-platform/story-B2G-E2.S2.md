---
story_id: B2G-E2.S2
title: "Source discovery + aquisição PNCP/CIGA → ESR"
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

**OUT:** Todos os portais municipais; DOE auth; M2≥95%.

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

- run_id em output/pncp_sc ou output/ciga_dom
- Diff stats ESR before/after

## Definition of Done

- [ ] AC1–5
- [ ] Documentado comando Tiago/ops
- [ ] File list

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
