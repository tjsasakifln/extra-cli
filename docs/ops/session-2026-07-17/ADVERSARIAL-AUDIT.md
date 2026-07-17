# Auditoria adversarial — sessão cobertura 200 km (2026-07-17)

**Auditor:** QA Lead adversarial (pós-integração)  
**Branch:** `epic/coverage-200km-operational`  
**Baseline histórico:** 52 / 1.093 (4,76%)  
**Headline comercial auditada:** **116 / 1.093 (10,61%)**  
**Data:** 2026-07-17  

## Método

Tentativa de **destruir** claims da sessão. Cada item: PASS / FAIL / CONCERNS com evidência.

---

## 1. Live vs atestação

| Claim | Veredito | Evidência |
|-------|----------|-----------|
| CIGA live | **PASS** | `output/ciga_dom/ciga-dom-20260717T104504Z-a04e1e294b/` · live CKAN downloads · raw zone |
| Compras SC live | **PASS** | `api_total_elementos_reported=2602` · `records_normalized=2602` · artifact full |
| PNCP SC live | **PASS com ressalvas** | 330→541 registros; 1–6 janelas com 429/JSON decode; **não** 14d completo |

## 2. Contagens de banco

| Query | Resultado | Match claim? |
|-------|-----------|--------------|
| `COUNT(*) official_acts` | **15.738** | PASS vs claim pós-load |
| por source | ciga 12636, sc_compras 2602, doe 500 | PASS |
| dups `(source,record_hash)` | **0** | PASS |
| `is_covered` raio 200km | **116** | PASS = commercial_numerator |
| migrations 051/052 | applied | PASS |

## 3. Arquivos e hashes

| Artefato | Existe? |
|----------|---------|
| `coverage_canonical.json` | SIM |
| `entities_covered.jsonl` / `entities_uncovered.jsonl` | SIM |
| `radar_opportunities.jsonl` + `.csv` | SIM |
| `baseline.json` com quality gates | SIM |
| DOD §43 / HTML cards | SIM (revisados) |

## 4. Numerador reproduzível

- **Headline:** `commercial_opportunity_any` = entidades com ≥1 registro OPEN/UPCOMING/RECENT matched ao universo 1.093.
- **Não** usa RESULT/CONTRACT/Homologado.
- **Não** usa ato genérico `nao_relacionado`.
- Recompute: `python3 -m scripts.coverage.session_coverage_pipeline` → 116.
- Denominador fixo **1093** (`sc_public_entities.is_active AND raio_200km`).

## 5. Classificador OPEN (regressão)

| Caso | Esperado | Obtido | Veredito |
|------|----------|--------|----------|
| `Publicado Resultado da Licitação` | RESULT | RESULT | **PASS** (corrigido; era OPEN) |
| `Homologado` | RESULT | RESULT | PASS |
| `Em Recebimento de Proposta` | OPEN | OPEN | PASS |
| Prazo `data_encerramento` passado | CLOSED | CLOSED | PASS |
| Testes | 10 passed | `tests/test_commercial_status.py` | PASS |

## 6. Compras SC prazos

| Fato | Valor |
|------|-------|
| List-only sem deadline | 2602/2602 `data_encerramento` empty |
| Detail enrich 200 opens | `dataEntrega` mapeado como prazo |
| OPEN com deadline no radar | **438** / 757 OPEN |
| Claim “todas abertas com prazo validado” | **PROIBIDO** — só subset enriquecido |

## 7. PNCP oficial

| Claim | Veredito |
|-------|----------|
| Match massivo por nº controle PNCP | **FAIL se alegado** — reconciliação sample ainda `compras_sc_id_crosswalk` |
| `sc-*` como PNCP | **não** feito |
| PNCP SC 14d completo | **não** — 429 residual documentado |

## 8. Escopo geográfico

- Universo só `raio_200km=TRUE` (1093).
- Muni SC CIGA não entra no denominador de editais (métrica separada).

## 9. Documentação antes da prova

- DOD/HTML da rodada inicial usaram 138 (is_covered loose).  
- **Correção adversarial:** headline **116 comercial**; 138 marcado como loose/não-claim.  
- Esta auditoria **precede** o fechamento documental final revisado.

## 10. CI remota

| Item | Status |
|------|--------|
| Testes locais commercial | 10 PASS |
| Ruff novos módulos | exit 0 |
| mypy commercial/sector | Success |
| pip-audit | No known vulnerabilities |
| Bandit | B310 medium urllib HTTPS (documentado nosec) |
| PR + GitHub Actions | **a ser aberto no push** — sem claim verde até log remoto |

## 11. Segunda execução incremental

| Fonte | 2ª rodada | Veredito |
|-------|-----------|----------|
| CIGA | processou recursos mid-month; load dups=0 | PASS |
| Compras SC | incremental 0 novos; reload 2602 dups=0 | PASS |
| PNCP SC | 2ª com delay 2.5s → 541 records, 1 erro | **PASS parcial** (ainda incompleto vs 14d ideal) |

## 12. Claims destruídos / removidos

1. ~~138 como cobertura comercial canônica~~ → **116 commercial_opportunity_any**.  
2. ~~Todas OPEN com prazo~~ → 438/757 com deadline conhecido.  
3. ~~PNCP SC completo~~ → 429 documentado.  
4. ~~CI verde remota~~ → só local até Actions.  
5. ~~95% / LOCAL_READY / VPS~~ → proibidos.

## 13. Claims que sobrevivem

1. Baseline 52/1093 preservado.  
2. Headline comercial **116/1093 (10,61%)**, Δ **+64** vs baseline, listas nominais.  
3. CIGA >> smoke (10k+ pubs; 12.636 atos).  
4. Compras SC **2602/2602** ano 2026 list.  
5. Radar com ranking + GO/REVIEW/NO_GO + CSV.  
6. 0 dups hash em official_acts.  
7. Classificador não marca “Publicado Resultado” como aberto.

## 14. Constatações críticas abertas?

| ID | Severidade | Status |
|----|------------|--------|
| C1 OPEN false positive | HIGH | **FECHADO** (fix+test) |
| C2 headline loose 138 | HIGH | **FECHADO** (116 commercial) |
| C3 radar sem ranking/CSV | MED | **FECHADO** |
| C4 baseline sem gates | MED | **FECHADO** |
| C5 ADVERSARIAL-AUDIT missing | HIGH | **FECHADO** (este doc) |
| C6 CI remota | HIGH | **ABERTO** até PR verde |
| C7 PNCP 14d incompleto | MED | **ACEITO** com claim proibido |
| C8 Compras deadline partial | MED | **ACEITO** com claim qualificado |

**Gate documental local:** PASS com ressalvas C6–C8.  
**Gate publicação remota:** bloqueado até CI Actions verde.

---

*Fim da auditoria adversarial.*
