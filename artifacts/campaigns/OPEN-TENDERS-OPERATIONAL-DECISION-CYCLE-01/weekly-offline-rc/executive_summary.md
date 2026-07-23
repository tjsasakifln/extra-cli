# Pacote semanal Extra Construtora — weekly-20260723T234219Z-b1c82d43ce

- **Gerado em:** 2026-07-23T23:42:19Z
- **Collection ID:** `col-extra-weekly-20260723T234219Z-d1868440`
- **Git:** `6db0a6987c425bcd3bdcdeb97bc0230ddfb3c41b`
- **Exit code previsto:** ver manifest

## Resumo executivo

Este pacote lista **4** oportunidades abertas/upcoming, **0** contratos recentes/relevantes, **0** concorrentes observáveis (top) e **4** órgãos associados nas oportunidades.

Ranking efetivo: **GO=0**, **REVIEW=4**, **NO_GO=0**.

> Scores **não** são probabilidades de vitória.
>
> Valores de contrato são **contratados**, não pagos.

## Freshness / saúde das fontes

- `pncp_opportunities`: **unreliable** (age_h=0.62, SLA=24h)
- `pncp_contracts`: **fresh** (age_h=3.53, SLA=168h) — freshness by max(ingested_at); not a full re-collect this cycle

## Coletas deste ciclo

- `pncp_opportunities` run `collect-pncp_opportunities-20260723T234221Z-10d16aeb86` → **reused_fresh** (obtidos=0, persistidos=0)
  - nota: offline test mode — no network
- `pncp_contracts` run `collect-pncp_contracts-20260723T234221Z-c3b8118c1b` → **reused_fresh** (obtidos=4438345, persistidos=4438345)
  - nota: contracts not re-crawled; lake rows reused with explicit freshness
  - nota: age_hours=3.53

## Top oportunidades (até 15)

| id | ranking | órgão | objeto | valor_estimado | prazo | fonte |
|---:|---|---|---|---:|---|---|
| 1 | REVIEW | FUNDO MUNICIPAL DE SAUDE DE SANTA TEREZI | AQUISIÇÃO DE LENÇÓIS E MANTAS DESTINADOS AOS LEITOS DA UNIDADE BÁSICA DE SAÚDE D | 2562.60 | 2026-07-23 00:00:00+00:00 | pncp |
| 2 | REVIEW | CONSORCIO INTERMUNICIPAL DE SAUDE DO ALT | Aquisição de 01 (um) computador do tipo All in One, novo, de primeiro uso, conte | 4922.50 | 2026-07-23 00:00:00+00:00 | pncp |
| 3 | REVIEW | FUNDO MUNICIPAL DE SAUDE | CREDENCIAMENTO DE EMPRESA ESPECIALIZADA PARA EXECUÇÃO DE SERVIÇOS DE FORMA COMPL | 1500000.00 | 2026-07-23 00:00:00+00:00 | pncp |
| 4 | REVIEW | MUNICIPIO DE PORTO UNIAO | Credenciamento de empresa para prestação de serviços de manutenção da frota muni | 2571000.00 | 2026-07-23 00:00:00+00:00 | pncp |

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
- Campos críticos PENDING no perfil Extra forçam REVIEW (nunca PARTICIPAR definitivo).
- valor_estimado ≠ valor_homologado ≠ valor pago/medido.
- PDF multi-página real permanece residual nesta campanha.
- Open tenders: coleta canônica via run_pncp_open_monitoring; reconciliação só em run completo + scope_complete.
- Freshness de editais: SLA 24h (DOD prevalece).
- Contratos no ciclo semanal reutilizam o lake com declaração de freshness (re-coleta completa de 499k+ linhas está fora do orçamento do ciclo).
- Universo canônico = entidades raio 200 km (meta 1093).
- Fonte pncp_opportunities reutilizada dentro do SLA (sem nova chamada oficial).
- Fonte pncp_contracts reutilizada dentro do SLA (sem nova chamada oficial).
- Freshness pncp_opportunities=unreliable.

## Aceite humano

Status: **PENDING_HUMAN** (Tiago). Ausência de manifestação **não** é aceite.

Revisar no mínimo: resumo, oportunidades, amostra de contratos, concorrentes, valores e limitações.

## PDF

**RESIDUAL:** PDF operacional multi-página real não é gate deste ciclo. Produto canônico: Markdown + Excel + CSV.

