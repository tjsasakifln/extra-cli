# Pacote semanal Extra Construtora — weekly-20260724T214052Z-5d7fc91e7c

- **Gerado em:** 2026-07-24T21:40:52Z
- **Collection ID:** `col-extra-weekly-20260724T214052Z-8da20af7`
- **Git:** `4d3cfadc19a8563317d3ddcf63ee63c4551685df`
- **Exit code previsto:** ver manifest

## Resumo executivo

Este pacote lista **7** oportunidades abertas/upcoming, **30** contratos recentes/relevantes, **30** concorrentes observáveis (top) e **7** órgãos associados nas oportunidades.

Ranking efetivo: **GO=0**, **REVIEW=7**, **NO_GO=0**.

> Scores **não** são probabilidades de vitória.
>
> Valores de contrato são **contratados**, não pagos.

## Freshness / saúde das fontes

- `pncp_opportunities`: **never** (age_h=None, SLA=24h)
- `pncp_contracts`: **fresh** (age_h=25.86, SLA=168h) — freshness by max(ingested_at); not a full re-collect this cycle

## Coletas deste ciclo

- `pncp_opportunities` run `collect-pncp_opportunities-20260724T214053Z-f8742a1bfd` → **partial** (obtidos=0, persistidos=0)
  - nota: skip_collect with freshness level=never — not promoted to reused_fresh
  - nota: partial: lake reused without complete in-SLA collection proof
- `pncp_contracts` run `collect-pncp_contracts-20260724T214053Z-978b39a746` → **reused_fresh** (obtidos=4437142, persistidos=4437142)
  - nota: contracts not re-crawled; lake rows reused with explicit freshness
  - nota: age_hours=25.86

## Top oportunidades (até 15)

| id | ranking | órgão | objeto | valor_estimado | prazo | fonte |
|---:|---|---|---|---:|---|---|
| 9 | REVIEW | CEFOR | [SNAPSHOT-SEED open] (ZMES) - CONTRATAÇÃO DE ATÉ 02 (DUAS) EMPRESAS ESPECIALIZAD | None | — | pncp |
| 10 | REVIEW | SECRETARIA GERAL DO EXERCITO/MEX/DF | [SNAPSHOT-SEED open] НHOSPITAL GERAL DE MÉDIA E ALTA COMPLEXIDADE COM ATENDIMENT | None | — | pncp |
| 11 | REVIEW | SUPERINTENDENCIA ESTADUAL DO MS/TO | [SNAPSHOT-SEED open] VISTO À AQUISIÇÃO EMERGENCIAL DE EQUIPAMENTOS NÁUTICOS PARA | None | — | pncp |
| 1 | REVIEW | FUNDO MUNICIPAL DE SAUDE DE SANTA TEREZI | AQUISIÇÃO DE LENÇÓIS E MANTAS DESTINADOS AOS LEITOS DA UNIDADE BÁSICA DE SAÚDE D | None | — | pncp |
| 2 | REVIEW | CONSORCIO INTERMUNICIPAL DE SAUDE DO ALT | Aquisição de 01 (um) computador do tipo All in One, novo, de primeiro uso, conte | None | — | pncp |
| 3 | REVIEW | FUNDO MUNICIPAL DE SAUDE | CREDENCIAMENTO DE EMPRESA ESPECIALIZADA PARA EXECUÇÃO DE SERVIÇOS DE FORMA COMPL | None | — | pncp |
| 4 | REVIEW | MUNICIPIO DE PORTO UNIAO | Credenciamento de empresa para prestação de serviços de manutenção da frota muni | None | — | pncp |

## Contratos (amostra)

| órgão | fornecedor | valor_contratado | fim |
|---|---|---:|---|
| MUNICÍPIO DE GAROPABA | CEPALAB LABORATORIOS S.A | 13320.00 | 2026-08-07 |
| MUNICÍPIO DE BRUSQUE | SK MATERIAIS PARA ESCRITORIO LTDA | 135.90 | 2026-08-07 |
| MUNICÍPIO DE GAROPABA | NUTRIPORT COMERCIAL LTDA | 23223.80 | 2026-08-07 |
| MUNICÍPIO DE GAROPABA | SEBOLD INDÚSTRIA DE COSMÉTICOS LTDA | 176.32 | 2026-08-07 |
| MUNICÍPIO DE BOMBINHAS | MYR COMERCIO DE ARTIGOS PEDAGOGICOS LTDA | 440.00 | 2026-08-22 |
| MUNICÍPIO DE BRUSQUE | MEDILAR IMPORTACAO E DISTRIBUICAO DE PRO | 5279.94 | 2026-08-07 |
| Servico Autonomo Municipal de Agua e Esg | CIEE/SC-CENTRO DE INT. EMPRESA-ESCOLA DE | 1847.40 | 2027-07-23 |
| MUNICÍPIO DE GAROPABA | NUTRIPORT COMERCIAL LTDA | 1713.00 | 2026-08-07 |
| MUNICÍPIO DE GAROPABA | NUTRIPORT COMERCIAL LTDA | 1142.00 | 2026-08-07 |
| MUNICÍPIO DE GAROPABA | REIFLEX INDUSTRIA E COMERCIO DE MOVEIS L | 1408.00 | 2026-08-22 |

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

