# Final report — CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01

**Status de campanha:** `READY_FOR_TIAGO_REVIEW_PUBLIC_AGENCY_VERTICAL`  
**Não declarar:** `PROJECT_DONE`, `COMMERCIAL_VERTICAL_ACCEPTED`, `DOD_ACCEPTED`, `LEGAL_COMPLIANCE_GUARANTEED`, `PRODUCTION_ACCEPTED`

**Atualizado (UTC):** 2026-07-30T23:33:04Z

---

## 1. Resumo executivo

Vertical B2G de órgãos públicos no ciclo canônico (`CONFENGE_COMMERCIAL_TARGET=public-agencies`).  
Rodada real SC com **populações oficiais IBGE Censo 2022**, **modo proativo** (histórico contratual ≠ oportunidade aberta), **sem contatos institucionais inventados**, fracionamento com indicadores de amostra sem claim de ledger anual completo.

## 2. Correções pós-skeptic (honestidade)

| Issue | Fix |
|-------|-----|
| Populações sintéticas | YAML reescrito via API IBGE agregado 4714 var 93 |
| `has_institutional_contact=True` | Sempre false sem e-mail/telefone real; research_actions apenas |
| Fracionamento desligado | `same_nature` alimenta indicadores; `complete_annual_ledger=False` |
| REACTIVE em histórico | Só REACTIVE com `active_direct_contracting_notice`; senão PROACTIVE |
| Testes teatro | `evidence.record_document_lookup` + honesty tests |

## 3. Execução real SC (dual launch)

| Campo | Launch 1 / 2 |
|-------|----------------|
| git_sha | `5f33ee00fbb59715d20d978cac301b38b637213d` (match HEAD da implementação honesty) |
| status | PASS |
| evaluated | 275 |
| publishable | 20 |
| top_n | 20 |
| outreach_sent | False |
| dual agreement | same Top 20 names, same SHA |

### Top 20

| # | Órgão | Pop (IBGE 2022) | Mode | Score | Oferta |
|---|-------|-----------------|------|-------|--------|
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

## 4. Testes

- `tests/public_agency/`: 35+ passed (legal, pipeline, honesty, separation)
- `tests/commercial_leads` subset + supplier TARGET fail-closed: supplier regression log
- Dual launches: `/tmp/grok-goal-.../implementer/pag-launch-{1,2}/`

## 5. Artefatos

- `output/confenge-commercial/public-agencies/`
- `artifacts/campaigns/CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01/`
- PR: https://github.com/tjsasakifln/extra-cli/pull/185

## 6. Ação humana

**Tiago deve revisar a fila de órgãos, os conflitos de interesses, as classificações jurídicas preliminares, os dossiers e os materiais de abordagem antes de autorizar qualquer contato.**
