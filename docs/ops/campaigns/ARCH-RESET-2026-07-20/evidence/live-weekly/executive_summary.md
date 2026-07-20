# Pacote semanal Extra Construtora — weekly-20260720T123255Z-2bd96bbea3

- **Gerado em:** 2026-07-20T12:32:55Z
- **Collection ID:** `col-extra-weekly-20260720T123255Z-11535c15`
- **Git:** `d6d9e1984e348d64a669546613e192e4ebf610cd`
- **Exit code previsto:** ver manifest

## Resumo executivo

Este pacote lista **0** oportunidades abertas/upcoming, **0** contratos recentes/relevantes, **0** concorrentes observáveis (top) e **0** órgãos associados nas oportunidades.

Ranking efetivo: **GO=0**, **REVIEW=0**, **NO_GO=0**.

> Scores **não** são probabilidades de vitória.
>
> Valores de contrato são **contratados**, não pagos.

## Freshness / saúde das fontes

- `pncp_opportunities`: **never** (age_h=None, SLA=48h)
- `pncp_contracts`: **never** (age_h=None, SLA=168h)

## Coletas deste ciclo

- `pncp_opportunities` run `collect-pncp_opportunities-20260720T123255Z-e771831fa9` → **reused_fresh** (obtidos=0, persistidos=0)
  - nota: offline test mode — no network
- `pncp_contracts` run `collect-pncp_contracts-20260720T123255Z-1ffa9ff606` → **failure** (obtidos=0, persistidos=0)
  - erro: no contracts in lake

## Top oportunidades (até 15)

| id | ranking | órgão | objeto | valor_estimado | prazo | fonte |
|---:|---|---|---|---:|---|---|

## Contratos (amostra)

| órgão | fornecedor | valor_contratado | fim |
|---|---|---:|---|

## Gaps conhecidos

- no_GO_rankings: Nenhuma oportunidade com ranking efetivo GO — revisar perfil Extra / fatores
- editais_coverage_below_95: Cobertura de editais permanece abaixo de 95% — não claim nesta campanha
- recall_independent_unproven: Recall independente estratificado não comprovado
- official_acts_empty: Tabela official_acts vazia no lake local

## Limitações

- Este pacote não declara LOCAL_READY, cobertura operacional 95% nem recall independente.
- Ranking GO/REVIEW/NO_GO é triagem interna, não probabilidade calibrada.
- valor_estimado ≠ valor_homologado ≠ valor pago/medido.
- PDF multi-página real permanece residual nesta campanha.
- Contratos no ciclo semanal reutilizam o lake com declaração de freshness (re-coleta completa de 499k+ linhas está fora do orçamento do ciclo).
- Universo canônico = entidades raio 200 km (meta 1093).
- Fonte pncp_opportunities reutilizada dentro do SLA (sem nova chamada oficial).
- Fonte pncp_contracts em estado failure.
- Freshness pncp_opportunities=never.
- Freshness pncp_contracts=never.

## Aceite humano

Status: **PENDING_HUMAN** (Tiago). Ausência de manifestação **não** é aceite.

Revisar no mínimo: resumo, oportunidades, amostra de contratos, concorrentes, valores e limitações.

## PDF

**RESIDUAL:** PDF operacional multi-página real não é gate deste ciclo. Produto canônico: Markdown + Excel + CSV.

