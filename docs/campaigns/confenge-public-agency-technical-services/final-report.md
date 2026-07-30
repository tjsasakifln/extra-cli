# Final report — CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01

**Status de campanha:** `READY_FOR_TIAGO_REVIEW_PUBLIC_AGENCY_VERTICAL`  
**Não declarar:** `PROJECT_DONE`, `COMMERCIAL_VERTICAL_ACCEPTED`, `DOD_ACCEPTED`, `LEGAL_COMPLIANCE_GUARANTEED`, `PRODUCTION_ACCEPTED`

**Atualizado (UTC):** 2026-07-30T23:36:01Z

---

## Binding stamp (tip HEAD)

| Campo | Valor |
|-------|-------|
| tip HEAD | `6a5ce52a48d79cb9ccd697b94a8b6b930cdccde4` |
| run git_sha (launch 1 & 2) | `6a5ce52a48d79cb9ccd697b94a8b6b930cdccde4` |
| SHA match tip | **True** |
| dual Top 20 agreement | **True** |
| as_of | 2026-07-15 |
| PR | https://github.com/tjsasakifln/extra-cli/pull/185 |

## Dual launch evidence paths

- Launch 1: `{SCRATCH}/pag-launch-1/` (stdout, run-result, manifest, checksums)
- Launch 2: `{SCRATCH}/pag-launch-2/`
- Agreement: `{SCRATCH}/pag-real-run/dual-launch-agreement.json`
- Supplier regression: `{SCRATCH}/supplier-regression.log`

## Metrics

| Metric | Value |
|--------|-------|
| status | PASS |
| agency_universe | 477 |
| evaluated | 275 |
| publishable | 20 |
| top_n | 20 |
| outreach_sent | False |
| ready_state | READY_FOR_TIAGO_REVIEW_PUBLIC_AGENCY_VERTICAL |

## Honesty gates (verified on Top 20)

- mode = PROACTIVE_INSTITUTIONAL_PROSPECT for all published leads (historical contracts ≠ open opportunity)
- has_institutional = false; institutional_contact_available = NOT_FIRED
- research_actions present (not invented email/phone)
- annual_sum_state = DIRECT_CONTRACTING_SUM_UNKNOWN; annual_sum_known = false
- populations from IBGE Censo 2022 API (agregado 4714 var 93)

## Top 20

| # | Órgão | Pop IBGE 2022 | Mode | Score | Oferta |
|---|-------|---------------|------|-------|--------|
| 1 | MUNICÍPIO DE ÁGUAS DE CHAPECÓ | 6036 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.5975 | PLANEJAMENTO_TECNICO_DA_CONTRATACAO |
| 2 | PREFEITURA MUNICIPAL DE PALMITOS - SC | 15626 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.4725 | REVISAO_PRE_PUBLICACAO |
| 3 | MUNICÍPIO DE JOAÇABA | 30146 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.4725 | REVISAO_PRE_PUBLICACAO |
| 4 | PREFEITURA MUNICIPAL DE SANGÃO | 12882 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.4575 | REVISAO_PRE_PUBLICACAO |
| 5 | MUNICÍPIO DE ITAIÓPOLIS | 22051 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.4475 | REVISAO_PRE_PUBLICACAO |
| 6 | MUNICÍPIO DE POUSO REDONDO | 17123 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.4475 | PLANEJAMENTO_TECNICO_DA_CONTRATACAO |
| 7 | MUNICÍPIO DE GAROPABA | 29959 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.4475 | REVISAO_PRE_PUBLICACAO |
| 8 | PREFEITURA MUNICIPAL DE PONTE SERRADA - SC | 10649 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.4275 | REVISAO_PRE_PUBLICACAO |
| 9 | Prefeitura Municipal de Catanduvas | 10566 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.4275 | REVISAO_PRE_PUBLICACAO |
| 10 | MUNICÍPIO DE JUPIÁ | 2555 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.4275 | REVISAO_PRE_PUBLICACAO |
| 11 | MUNICÍPIO DE IBIRAMA | 19862 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.4025 | REVISAO_PRE_PUBLICACAO |
| 12 | MUNICÍPIO DE PARAÍSO | 4267 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.4025 | PLANEJAMENTO_TECNICO_DA_CONTRATACAO |
| 13 | MUNICÍPIO DE CAMPOS NOVOS | 36932 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.4025 | REVISAO_PRE_PUBLICACAO |
| 14 | MUNICÍPIO DE ITAPIRANGA | 16638 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.4025 | REVISAO_PRE_PUBLICACAO |
| 15 | Prefeitura de Gaspar - SC | 72570 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.3925 | REVISAO_PRE_PUBLICACAO |
| 16 | MUNICIPIO DE SAO MIGUEL D'OESTE | 44330 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.3575 | PLANEJAMENTO_TECNICO_DA_CONTRATACAO |
| 17 | MUNICÍPIO DE PINHALZINHO | 21972 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.3575 | PLANEJAMENTO_TECNICO_DA_CONTRATACAO |
| 18 | Fundação Cultural de São Bento do Sul | 83277 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.3475 | REVISAO_PRE_PUBLICACAO |
| 19 | MUNICÍPIO DE PAULO LOPES | 9063 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.3325 | ORCAMENTO_E_PLANEJAMENTO_DE_OBRAS |
| 20 | MUNICÍPIO DE XANXERÊ | 51607 | PROACTIVE_INSTITUTIONAL_PROSPECT | 0.3225 | REVISAO_PRE_PUBLICACAO |

## Tests

- `pytest tests/public_agency/` — 35 passed
- supplier unit subset + TARGET suppliers fail-closed without snapshot — captured in supplier-regression.log

## Artifacts

- Live: `output/confenge-commercial/public-agencies/`
- Pack: `artifacts/campaigns/CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01/`

## Human action

**Tiago deve revisar a fila de órgãos, os conflitos de interesses, as classificações jurídicas preliminares, os dossiers e os materiais de abordagem antes de autorizar qualquer contato.**
