# Pacote semanal Extra Construtora — weekly-20260724T151853Z-f36b5838f1

- **Gerado em:** 2026-07-24T15:18:53Z
- **Collection ID:** `col-extra-weekly-20260724T151853Z-397cf2e5`
- **Git:** `0f8ab480ed81af1ffc2f1188944a6af648b242ea`
- **Exit code previsto:** ver manifest

## Resumo executivo

Este pacote lista **0** oportunidades abertas/upcoming, **50** contratos recentes/relevantes, **50** concorrentes observáveis (top) e **0** órgãos associados nas oportunidades.

Ranking efetivo: **GO=0**, **REVIEW=0**, **NO_GO=0**.

> Scores **não** são probabilidades de vitória.
>
> Valores de contrato são **contratados**, não pagos.

## Freshness / saúde das fontes

- `pncp_opportunities`: **never** (age_h=None, SLA=24h)
- `pncp_contracts`: **fresh** (age_h=19.5, SLA=168h) — freshness by max(ingested_at); not a full re-collect this cycle

## Coletas deste ciclo

- `pncp_opportunities` run `collect-pncp_opportunities-20260724T151854Z-a680761dca` → **partial** (obtidos=0, persistidos=0)
  - nota: skip_collect with freshness level=never — not promoted to reused_fresh
  - nota: partial: lake reused without complete in-SLA collection proof
- `pncp_contracts` run `collect-pncp_contracts-20260724T151855Z-9cb3471b80` → **reused_fresh** (obtidos=4437142, persistidos=4437142)
  - nota: contracts not re-crawled; lake rows reused with explicit freshness
  - nota: age_hours=19.5

## Top oportunidades (até 15)

| id | ranking | órgão | objeto | valor_estimado | prazo | fonte |
|---:|---|---|---|---:|---|---|

## Contratos (amostra)

| órgão | fornecedor | valor_contratado | fim |
|---|---|---:|---|
| MUNICÍPIO DE BRUSQUE | ATTLAS SPORTS LTDA | 194.60 | 2026-08-22 |
| MUNICÍPIO DE BRUSQUE | OTHALA COMERCIO LTDA | 1766.75 | 2026-08-07 |
| MUNICÍPIO DE BRUSQUE | INOVA COMERCIAL & TRANSPORTES RODOVIARIO | 1350.00 | 2026-08-22 |
| MUNICÍPIO DE BRUSQUE | BLUSAFE EQUIPAMENTOS DE PROTECAO INDIVID | 231.00 | 2026-08-22 |
| MUNICÍPIO DE BRUSQUE | RAFAEL KUHN LTDA | 1075.00 | 2026-08-22 |
| MUNICÍPIO DE BRUSQUE | LICERI COMÉRCIO DE PRODUTOS EM GERAL LTD | 1135.80 | 2026-08-22 |
| MUNICÍPIO DE BRUSQUE | SK MATERIAIS PARA ESCRITORIO LTDA | 135.90 | 2026-08-07 |
| MUNICÍPIO DE BRUSQUE | GO VENDAS ELETRONICAS LTDA | 625.00 | 2026-08-22 |
| MUNICÍPIO DE BRUSQUE | EMMA INDÚSTRIA E COMÉRCIO DE MÓVEIS LTDA | 1400.00 | 2026-08-22 |
| MUNICÍPIO DE BRUSQUE | BLUSAFE EQUIPAMENTOS DE PROTECAO INDIVID | 604.00 | 2026-08-22 |

## Gaps conhecidos

- no_GO_rankings: Nenhuma oportunidade com ranking efetivo GO — revisar perfil Extra / fatores
- editais_coverage_below_95: Cobertura de editais permanece abaixo de 95% — não claim nesta campanha
- recall_independent_unproven: Recall independente estratificado não comprovado
- official_acts_empty: Tabela official_acts vazia no lake local

## Limitações

- Este pacote não declara LOCAL_READY, cobertura operacional 95% nem recall independente.
- Ranking GO/REVIEW/NO_GO é triagem interna, não probabilidade calibrada.
- Campos críticos PENDING no perfil Extra forçam REVIEW (nunca PARTICIPAR definitivo).
- valor_estimado ≠ valor_homologado ≠ valor pago/medido.
- PDF multi-página real permanece residual nesta campanha.
- Open tenders: coleta canônica via run_pncp_open_monitoring; reconciliação só em run completo + scope_complete.
- Freshness de editais: SLA 24h (DOD prevalece).
- Contratos no ciclo semanal reutilizam o lake com declaração de freshness (re-coleta completa de 499k+ linhas está fora do orçamento do ciclo).
- Universo canônico = entidades raio 200 km (meta 1093).
- Coleta parcial em pncp_opportunities: ['skip_collect with freshness level=never — not promoted to reused_fresh', 'partial: lake reused without complete in-SLA collection proof']
- Fonte pncp_contracts reutilizada dentro do SLA (sem nova chamada oficial).
- Freshness pncp_opportunities=never.

## Aceite humano

Status: **PENDING_HUMAN** (Tiago). Ausência de manifestação **não** é aceite.

Revisar no mínimo: resumo, oportunidades, amostra de contratos, concorrentes, valores e limitações.

## PDF

**RESIDUAL:** PDF operacional multi-página real não é gate deste ciclo. Produto canônico: Markdown + Excel + CSV.

