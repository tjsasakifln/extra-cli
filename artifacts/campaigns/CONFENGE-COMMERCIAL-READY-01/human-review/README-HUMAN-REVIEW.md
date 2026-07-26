# CONFENGE — Pacote de Revisão Humana

## Como preencher

1. Abra as planilhas `.xlsx` (preferencial) ou o HTML correspondente.
2. Cada linha é um objeto de revisão. **Não altere** `contract_id` / `cnpj14` / hashes.
3. Preencha os campos humanos listados abaixo. Agentes de IA **não** preenchem labels.

## Labels permitidas (relevância contratual)

| Label | Significado |
|-------|-------------|
| `RELEVANT_ENGINEERING` | Objeto claramente de engenharia/obras/infra |
| `AMBIGUOUS` | Ambíguo — requer adjudicação |
| `NOT_RELEVANT` | Fora de escopo (limpeza, merenda, TI genérica, etc.) |
| `INSUFFICIENT_TEXT` | Texto insuficiente para decidir |

## Labels permitidas (comercial top-20 / eval-200)

| Label | Significado |
|-------|-------------|
| `ACCEPT_OFFER` | Oferta sugerida aceitável para abordagem humana |
| `REJECT_OFFER` | Oferta inadequada |
| `WRONG_SECTOR` | Fornecedor fora do setor engenharia |
| `NEEDS_MORE_EVIDENCE` | Evidência insuficiente |

## Campos obrigatórios por revisor

- `reviewer_1_label`, `reviewer_1_reason`
- `reviewer_2_label`, `reviewer_2_reason`

## Identificar revisor 1 e revisor 2

- **Reviewer 1**: primeiro revisor humano designado (ex.: Tiago)
- **Reviewer 2**: segundo revisor independente
- Use nomes consistentes no campo `adjudicator` apenas na fase de adjudicação

## Adjudicar divergências

Quando `reviewer_1_label != reviewer_2_label`:

1. Terceiro revisor (adjudicator) preenche `adjudicated_label`
2. Registra `adjudicator` (nome) e `reviewed_at` (ISO-8601)
3. Não sobrescreva labels originais dos revisores 1/2

## Reimportar resultados

```bash
# Exemplo: copiar planilha preenchida para inbox e rodar avaliação
cp contract-relevance-human-review-filled.xlsx \
  artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/human-review/inbox/
make evaluate-confenge-real-contract-holdout
```

## Executar a avaliação

```bash
make evaluate-confenge-real-contract-holdout
make verify-confenge-real-corpus-provenance
```

## Checksums

Consulte `checksums.json` neste pacote. O pacote é gerado localmente e
publicado como artefato de workflow `confenge-human-review-packages`
(não precisa ser commitado no Git).
