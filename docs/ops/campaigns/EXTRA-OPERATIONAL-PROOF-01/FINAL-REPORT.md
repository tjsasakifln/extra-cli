# FINAL-REPORT — EXTRA-OPERATIONAL-PROOF-01

## Veredito

**`PARTIAL`**

Motivo: ciclo semanal real e produtos consultivos existem e foram executados com exit code 0, mas o aceite humano de Tiago permanece `PENDING_HUMAN` (AC10). Full suite CI continua fora do gate automático de PR (dívida residual honesta).

Não se declara `DONE`, `LOCAL_READY`, `PROJECT_DONE` nem cobertura 95%.

## Resultado operacional

| Campo | Valor |
|-------|--------|
| Comando canônico | `make extra-weekly` (`python -m scripts.ops.weekly_cycle --strict`) |
| Última execução canônica | `weekly-20260719T192008Z-853988a39f` |
| Exit code | **0** |
| Collections | `col-extra-weekly-20260719T192008Z-0142869a` |
| Fontes | `pncp_opportunities` (reused_fresh), `pncp_contracts` (reused_fresh) |
| Freshness | opps ~fresh SLA 48h; contracts ~fresh SLA 168h |
| Produtos | `executive_summary.md`, `extra_weekly_pack.xlsx`, CSVs, `manifest.json` |
| Tempo total | ~2 s (reuse) / ~5 s (force-collect window) |
| Limitações | PDF residual; GO=0; recall não provado; contratos sem re-crawl completo; aceites humanos pendentes |

Checksums: `evidence/product_checksums.json`.

## Delta funcional

**Antes:** Tiago precisava orquestrar mentalmente `workspace`, `opportunity_intel`, freshness, exports e pacotes fixture-oriented.

**Agora:** um comando gera pacote semanal com:

1. oportunidades abertas/upcoming  
2. contratos recentes/relevantes  
3. órgãos e fornecedores  
4. concorrentes observáveis  
5. valores com semântica explícita (estimado ≠ contratado ≠ pago)  
6. source health / freshness  
7. gaps conhecidos  
8. proveniência (claims → run/collection)  
9. resumo executivo Markdown  
10. Excel + CSV  

## Delta arquitetural

Fronteiras reforçadas (sem reescrita):

```text
collect   → scripts/collect/run_contract.py
process   → crawlers/normalizers existentes (orquestrados)
quality   → scripts/quality/indicator_catalog.py + gates no ciclo
intelligence → queries em weekly_cycle (opportunity_intel + contracts)
delivery  → MD/Excel/CSV/manifest no mesmo run
```

## Benchmark aplicado

Ver `DECISIONS.md`. Resumo: **ADAPT** collection/run tracking + metric catalog + stage separation; **REJECT** stack Kingfisher/OCDS full e Scrapy rewrite.

## CI

| Check | Resultado local |
|-------|-----------------|
| Unit weekly cycle | 15 passed |
| Operational expanded (lista explícita) | 141 passed, 4 skipped, cov total módulos 38.4% (≥35%) |
| Full suite PR gate | **ainda não** — workflow_dispatch |
| continue-on-error / `\|\| true` | não introduzidos |

## Claims permitidos

- Existe entry point canônico `make extra-weekly` que produz pacote semanal auditável.
- O pacote inclui freshness por fonte, gaps, limitações e proveniência de afirmações.
- Universo 200 km no lake local = 1093 entidades (medido).
- Identidade CNPJ não promove match cross-root só por nome (teste unitário).
- Valores de contrato no pacote são rotulados como contratados, não pagos.

## Claims proibidos

- `LOCAL_READY` / `PRE_VPS_FINAL_READY` / `VPS_OPERATIONAL` / `PROJECT_DONE`
- Cobertura operacional 95% (editais ou 7 estágios)
- Proxy de contratos = cobertura completa
- Recall independente ≥95%
- Score = probabilidade de vitória
- PDF fixture/real como produto operacional desta campanha
- Aceite humano implícito

## Próxima decisão (única)

**Prioridade:** Tiago revisa o pacote em `output/weekly/PROOF-01-canonical/` (ou reexecuta `make extra-weekly`) e registra `ACCEPTED` / `ACCEPTED_WITH_LIMITATIONS` / `REJECTED`.  
Em paralelo técnico, o gargalo observado é **qualidade de ranking (GO=0)** e **coleta PNCP com janelas 204/429** — não falta de entry point. A próxima evolução de produto deve calibrar triagem Extra e robustecer coleta sob rate-limit, não criar mais governança.

## Arquivos principais entregues

- `scripts/ops/weekly_cycle.py`
- `scripts/collect/run_contract.py`
- `scripts/quality/indicator_catalog.py`
- `tests/test_weekly_cycle.py`
- `Makefile` (`extra-weekly`)
- `.github/workflows/ci.yml`
- `docs/canonical-entry-points.yaml`, `docs/DEVELOPMENT.md`
- `docs/ops/campaigns/EXTRA-OPERATIONAL-PROOF-01/*`
