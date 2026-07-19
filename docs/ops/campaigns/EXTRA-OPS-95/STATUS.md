# EXTRA-OPS-95-FOUNDATION — Status operacional

**Atualizado:** 2026-07-19T07:56Z  
**HEAD:** `9082b9d`+  
**Status global:** **PARTIAL**

## Métricas honestas

| Métrica | Valor | Meta |
|---------|------:|-----:|
| DOD checked | **245/1352 (18.12%)** | ≥746 (55%) |
| Denominador 200km | **1093** | fixo |
| Universe resolution | **100%** | 100% |
| Presença editais | **285 (26.075%)** | ≥1039 |
| Presença contratos | **368 (33.6688%)** | ≥1039 |
| success_zero contratos | **623** | — |
| Ops proxy contratos | **991 (90.6679%)** | 1039 (95%) gap **48** |
| Oportunidades | 401 (0 GO / ~397 REVIEW / 4 NO_GO) | fluxo útil |

## Marcos

| Marco | Status |
|-------|--------|
| M0 baseline | DONE |
| M0.5 OSS | DONE (0 ADOPT sem piloto) |
| M1 universo | DONE parcial (1093, 2ª import 0 inserts) |
| M2 cobertura | IN_PROGRESS — contratos ops 90.7%; editais 26% |
| M3 intel | PARTIAL — GO/REVIEW/NO_GO live |
| M4 packages | PARTIAL — PDF/Excel fixture |
| M5 backup/resume | PARTIAL — local proof |
| M6 recall | BLOCKED_SOURCE N09 |
| M7 HTML/DOD | PARTIAL — HTML+DOD atualizados |

## Correções adversariais

- Purge identidade falsa (token_containment cross-CNPJ): 48 cache + 39 SZ
- pick_match exige raiz CNPJ-8
- publicacao API não filtra cnpjOrgao (documentado)
- esfera_id M/E/F mapeado para 1/2/3 no transformer

## Claims proibidos

95% cobertura · 7 estágios · pré-purge 94% · either · DONE · LOCAL_READY · SmartLic operacional · SZ editais via publicacao
