# Editorial brief — `tof-ticket-edificacao-sc`

**Schema:** `traffic-opportunity-frontier/1.0`
**State:** `READY`
**Score:** 80
**Funnel:** `tofu` · **Family:** `A`
**Authorization:** no_publication_authorization=true · no_index_authorization=true

## Question

Qual o ticket típico (P25/mediana/P75) de contratos de edificação pública em Santa Catarina, e por que esse valor não é custo unitário?

## Visitor job

Comparar o próprio contrato/proposta com uma referência de ticket integral no recorte SC, sem tratar o número como preço por m².

## Factual outline

No recorte edificações-públicas × SC × 2024-01-01 a 2026-07-01 (n=24 contratos, 9 órgãos, 12 fornecedores, fonte pncp_supplier_contracts) o ticket integral nominal é P25 R$ 180 mil, mediana R$ 420 mil, P75 R$ 910 mil. Isso é valor do instrumento, não preço praticado por m² nem censo do Brasil.

## Unique insight

O P75 (~2,2× a mediana) no recorte SC já mostra cauda longa: usar a média como 'preço de mercado' enviesa proposta.

## Calculations

- `buyer_count`: 9
- `n`: 24
- `p25_brl`: 180000.0
- `p50_brl`: 420000.0
- `p75_brl`: 910000.0
- `p75_over_p50`: 2.167
- `supplier_count`: 12
- `value_semantics`: valor_contratado integral nominal BRL

## Limitations

- Amostra regional SC; não é censo nacional.
- Valor integral do instrumento; sem deflação e sem unidade física.
- n=24 é suficiente para percentis do recorte, não para órgãos individuais.

## Prohibited claims

- Ticket nacional de obras públicas.
- Preço praticado por m² ou 'custo real' da obra.
- 4,5 milhões de contratos como denominador desta página.
- Extra 1093 como universo Brasil.

## Suggested visuals

- Box-plot P25/mediana/P75 do recorte SC
- Nota de escopo geográfico (SC, não BR)

## Internal links

- `/metodologia-inteligencia/`
- `/auditoria-orcamento-licitacao/`
- `/radar/edificacoes-publicas-sc/`

## CTA

Ver metodologia e limites da inteligência de mercado

## Offer bridge

`/metodologia-inteligencia/` — A leitura do recorte e dos limites é o serviço de inteligência, não um preço mágico.

This brief is an outline. It is not published HTML and does not authorize index.
