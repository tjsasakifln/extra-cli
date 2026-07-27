# Revisão de concorrentes / vencedores — CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01

- run_id: `cmi-20260727T231157Z`
- as_of: `2026-07-27T23:11:57Z`
- period: `2023-01-01` → `2026-07-27`
- source: `pncp_supplier_contracts`
- code_sha: `1f395831d24bd19dfef7a8dcdfde8ee90f38e3d0`
- population_count: **7** contratos elegíveis
- complete_population_aggregated: `True`

## O que é conhecido

- Fornecedores **vencedores identificados** a partir de contratos com CNPJ de fornecedor.
- Ranking por valor contratado válido e quantidade de contratos.
- Distribuições observáveis por município, natureza do ente e setor lexical do objeto.

## O que não é conhecido

- Participantes/perdedores do certame: a fonte de contratos **não expõe** propostas.
- Win rate real: denominador de propostas ausente → `NOT_COMPUTABLE`.
- Capacidade ociosa ou técnica: **não inferida** a partir de n_contratos.

## Ranking (vencedores observados)

| rank | CNPJ | nome | n_contratos | valor_contratado | ticket | entes | última |
|-----:|------|------|------------:|-----------------:|-------:|------:|--------|
| 1 | 55555555000177 | Construtora Beta SA | 2 | 620000.0 | 310000.0 | 1 | 2024-11-01 |
| 2 | 22222222000191 | Fornecedor Alfa Eng | 3 | 430000.0 | 143333.33 | 2 | 2025-01-15 |
| 3 | 77777777000199 | Servicos Gama Ltda | 2 | 45000.0 | 45000.0 | 1 | 2025-02-01 |

## Market share e HHI

- status: `READY`
- HHI: `4764.9132` (escala 0_10000)
- denominador valor: `1095000.0`
- população: all active pncp_supplier_contracts with identifiable supplier CNPJ; uf=SC; period_start>=2023-01-01; period_end<=2026-07-27; value_type=valor_contratado; complete_population_aggregated=true

Concentração elevada **não** é irregularidade automática; concentração baixa **não** prova competição saudável.

## Semântica de valores

- **valor_estimado**: Valor de referência ou estimativa anterior ao resultado, conforme a fonte (ex.: valor_total_estimado do edital).
- **valor_homologado**: Valor do resultado homologado ou adjudicado quando a fonte assim o representar.
- **valor_contratado**: Valor formal do contrato ou instrumento equivalente (ex.: pncp_supplier_contracts.valor_total).
- **valor_pago**: Desembolso, pagamento ou execução financeira oficialmente registrada — não intercambiável com contratado.

Os quatro campos **não são intercambiáveis**.
Valor ausente permanece nulo (nunca zero fabricado).
Percentis de contratos globais heterogêneos **não** são rotulados como «preço real praticado».

## Confiabilidade por métrica

- `ranking_vencedores`: **READY** — vencedores com CNPJ a partir de contratos
- `participantes`: **SOURCE_UNAVAILABLE** — fonte de contratos não expõe participantes
- `win_rate`: **NOT_COMPUTABLE** — sem denominador de propostas
- `desagio`: **NOT_COMPUTABLE** — sem par estimado/homologado encadeado no recorte
- `market_share`: **READY** — all active pncp_supplier_contracts with identifiable supplier CNPJ; uf=SC; period_start>=2023-01-01; period_end<=2026-07-27; value_type=valor_contratado; complete_population_aggregated=true
- `hhi`: **READY** — mesma população do market share
- `valor_contratado`: **PARTIAL** — nulos preservados; ticket usa apenas válidos
- `capacidade`: **NOT_APPLICABLE** — não inferida; n_contratos ≠ capacidade
- `value_references`: **OK** — percentis só em grupos comparáveis; globais heterogêneos sinalizados

## Limitações

- Pacote de inteligência contratual comparativa — não cobertura operacional 95%.
- Participantes do certame não são conhecidos quando a fonte só expõe o vencedor contratado.
- Win rate e deságio fail-closed sem denominador/par comparável.
- Market share/HHI usam valor_contratado no recorte declarado; não são 'preço real praticado'.
- n_contratos e recorrência são observáveis — não capacidade técnica/ociosa.
- Órgão contratante nunca é apresentado como concorrente.
- Fixture seed only when isolated DB empty — labeled as non-live market.
- seed_applied: {'ok': True, 'seeded_contracts': 8, 'schema': {'table': 'pncp_supplier_contracts', 'columns_ok': ['contrato_id', 'orgao_cnpj', 'orgao_nome', 'fornecedor_cnpj', 'fornecedor_nome', 'objeto_contrato', 'valor_total', 'data_inicio', 'data_fim', 'uf', 'municipio', 'source', 'is_active'], 'present_count': 31}, 'note': 'fixture for isolated CMI proof — not live market coverage'}
