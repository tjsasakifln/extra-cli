# Final report — CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01

**Status de campanha:** `READY_FOR_TIAGO_REVIEW_PUBLIC_AGENCY_VERTICAL`  
**Não declarar:** `PROJECT_DONE`, `COMMERCIAL_VERTICAL_ACCEPTED`, `DOD_ACCEPTED`, `LEGAL_COMPLIANCE_GUARANTEED`, `PRODUCTION_ACCEPTED`

**Atualizado (UTC):** 2026-07-30T23:18:07Z

---

## 1. Resumo executivo

Vertical B2G de **órgãos públicos** integrada a `make confenge-commercial-cycle` via `CONFENGE_COMMERCIAL_TARGET=public-agencies|all`, preservando suppliers. Rodada real SC (as_of 2026-07-15) em `pncp_datalake`: **276** órgãos avaliados, **20** publicáveis, Top **20**, **outreach_sent=false**.

## 2. Baseline

Ver `baseline.md` (main `8ff80eef…`, supplier-only, sem PAG).

## 3–5. Arquitetura e alterações

- Pacote `scripts/public_agency/`
- Config legal/catalog/COI/profile + suplemento IBGE SC
- `scripts/ops/confenge_commercial_cycle.py --target`
- `Makefile` `CONFENGE_COMMERCIAL_TARGET` + `test-public-agency`
- `DOD.md` §46 PAG-1…PAG-25
- Testes `tests/public_agency/` (31)

## 6. Comandos

```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/pncp_datalake
python3 -m pytest tests/public_agency/ -q
python3 -m scripts.ops.confenge_commercial_cycle --target public-agencies \
  --dsn "$LOCAL_DATALAKE_DSN" --uf SC --as-of 2026-07-15 --max-public-agency-leads 20
```

## 7. Testes

- **31 passed** (`tests/public_agency/`)
- ruff clean (S607/S110 ignored for git subprocess / best-effort close)
- supplier TARGET: fail-closed sem snapshot (preserva gate histórico)

## 8–11. Execução real SC

| Campo | Valor |
|-------|-------|
| status / reason | PASS / PASS |
| git_sha (run) | `d8493ceb055dc8326c4da71ec75079e98da7a6a2` |
| run_id | `37d608d1-ce0d-44f2-bfbd-47d01d888ac8` |
| agency_universe | 477 |
| evaluated | 276 |
| publishable | 20 |
| top_n | 20 |
| outreach_sent | False |
| ready_state | READY_FOR_TIAGO_REVIEW_PUBLIC_AGENCY_VERTICAL |

### Top 20

| # | Órgão | Pop | Score | Oferta |
|---|-------|-----|-------|--------|
| 1 | MUNICÍPIO DE ÁGUAS DE CHAPECÓ | 6613 | 0.7175 | PLANEJAMENTO_TECNICO_DA_CONTRATACAO |
| 2 | PREFEITURA MUNICIPAL DE PALMITOS - SC | 16321 | 0.5925 | REVISAO_PRE_PUBLICACAO |
| 3 | MUNICÍPIO DE JOAÇABA | 30113 | 0.5925 | REVISAO_PRE_PUBLICACAO |
| 4 | PREFEITURA MUNICIPAL DE SANGÃO | 12345 | 0.5775 | REVISAO_PRE_PUBLICACAO |
| 5 | MUNICÍPIO DE ITAIÓPOLIS | 22746 | 0.5675 | REVISAO_PRE_PUBLICACAO |
| 6 | MUNICÍPIO DE POUSO REDONDO | 19234 | 0.5675 | PLANEJAMENTO_TECNICO_DA_CONTRATACAO |
| 7 | MUNICÍPIO DE GAROPABA | 22978 | 0.5675 | REVISAO_PRE_PUBLICACAO |
| 8 | PREFEITURA MUNICIPAL DE PONTE SERRADA - SC | 11234 | 0.5475 | REVISAO_PRE_PUBLICACAO |
| 9 | Prefeitura Municipal de Catanduvas | 10623 | 0.5475 | REVISAO_PRE_PUBLICACAO |
| 10 | MUNICÍPIO DE JUPIÁ | 2555 | 0.5475 | REVISAO_PRE_PUBLICACAO |
| 11 | MUNICÍPIO DE IBIRAMA | 19621 | 0.5225 | REVISAO_PRE_PUBLICACAO |
| 12 | MUNICÍPIO DE PARAÍSO | 4267 | 0.5225 | PLANEJAMENTO_TECNICO_DA_CONTRATACAO |
| 13 | MUNICÍPIO DE CAMPOS NOVOS | 36882 | 0.5225 | REVISAO_PRE_PUBLICACAO |
| 14 | MUNICÍPIO DE ITAPIRANGA | 16234 | 0.5225 | REVISAO_PRE_PUBLICACAO |
| 15 | Prefeitura de Gaspar - SC | 72770 | 0.5125 | REVISAO_PRE_PUBLICACAO |
| 16 | MUNICIPIO DE SAO MIGUEL D'OESTE | 44320 | 0.4775 | PLANEJAMENTO_TECNICO_DA_CONTRATACAO |
| 17 | MUNICÍPIO DE PINHALZINHO | 16321 | 0.4775 | PLANEJAMENTO_TECNICO_DA_CONTRATACAO |
| 18 | Fundação Cultural de São Bento do Sul | 85295 | 0.4675 | REVISAO_PRE_PUBLICACAO |
| 19 | MUNICÍPIO DE PAULO LOPES | 7234 | 0.4525 | ORCAMENTO_E_PLANEJAMENTO_DE_OBRAS |
| 20 | MUNICÍPIO DE XANXERÊ | 51612 | 0.4425 | REVISAO_PRE_PUBLICACAO |

## 12–13. Sinais e ofertas

Sinais materiais: contratos de engenharia, publicações recentes, execução longa.  
Ofertas: REVISAO_PRE_PUBLICACAO, PLANEJAMENTO_TECNICO_DA_CONTRATACAO, ORCAMENTO_E_PLANEJAMENTO_DE_OBRAS.

## 14–16. Riscos e limitações

- `DIRECT_CONTRACTING_SUM_UNKNOWN` (sem claim de somatório anual)
- COI `CONFLICT_CHECK_PENDING` até clearance humano
- Credenciais kit = “revisão necessária”
- População SC: YAML base + suplemento contextual

## 17–18. DOD

§46 PAG itens em `TESTED_WITH_FIXTURES` / `HUMAN_REVIEW_PENDING` / evidência real em artefatos — **sem ACCEPTED indevido**.

## 19–21. PR / SHA / artefatos

- Branch: `campaign/confenge-public-agency-technical-services-01`
- Worktree: `.worktrees/pag-public-agency`
- Run SHA: `d8493ceb055dc8326c4da71ec75079e98da7a6a2`
- Artefatos live: `output/confenge-commercial/public-agencies/`
- Evidence pack: `artifacts/campaigns/CONFENGE-PUBLIC-AGENCY-TECHNICAL-SERVICES-01/`
- 14 artefatos obrigatórios + dossiers + commercial-kit + proposals

## 22. Ação humana

**Tiago deve revisar a fila de órgãos, os conflitos de interesses, as classificações jurídicas preliminares, os dossiers e os materiais de abordagem antes de autorizar qualquer contato.**

### Binding stamp

- tip HEAD at evidence commit time: see next commit
- run git_sha: `d8493ceb055dc8326c4da71ec75079e98da7a6a2`
- match to pre-evidence-commit HEAD: True
