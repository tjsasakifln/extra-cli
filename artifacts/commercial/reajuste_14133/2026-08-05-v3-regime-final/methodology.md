# Metodologia — reajuste 14.133 commercial funnel v3.1 (regime fix)

## Correção central

Removida qualquer elevação de `legal_confidence` / `LIKELY_14133` por:

- ano de assinatura (`signature_year >= 2021`);
- publicação no PNCP.

O ano permanece apenas como **contexto cronológico** (período de transição, prioridade documental, inconsistências).

## Hierarquia de evidências (R-A…R-X)

| Nível | Regime | Proven | legal_confidence |
|-------|--------|--------|------------------|
| R-A | LEI_14133_2021 (export: LEI_14133_PROVEN) | true | high |
| R-B | LIKELY_14133 | false | medium |
| R-C | TRANSITIONAL_REGIME_UNRESOLVED | false | unresolved |
| R-D | UNKNOWN | false | none |
| R-X | LEGAL_REGIME_CONFLICT | false | conflict |

Legado comprovado (8.666 / RDC / 10.520) exclui do funil específico 14.133.
Processo/edital originário prevalece sobre ano de assinatura do contrato.

## Estágios comerciais

- `POTENTIAL_ADJUSTMENT_SIGNAL` / `DOCUMENT_REQUEST_READY`: regime desconhecido ou transição sem prova — linguagem **sem** afirmar Lei 14.133 aplicável.
- `LIKELY` / `DIAGNOSTIC` (específico 14.133): somente R-A ou R-B + maturidade + obrigação aberta.
- `VERIFIED`: regime **comprovado** (R-A) + pack documental + revisão humana completa.
- `CALCULABLE`: único estágio com `valor_potencial`.

## Validação empírica desta pasta

Replay integral do export nacional prévio (`contratos_analisados.json`, n=1800) via `classify_row` com a lógica v3.1.
O DSN local de testes **não** contém o universo nacional completo de contratos PNCP; a varredura live sem `--max-source-rows` fica bloqueada por ambiente, não por amostragem silenciosa no código.

## Revisão humana

`human_review_completed=true` exige reviewer, reviewed_at, decision, documento lido, locus (página/cláusula/seção/célula), decisão de regime, confidence e nota técnica.
Registros incompletos → `human_review_incomplete` (nunca descarte silencioso).
