# Metodologia — reajuste 14.133 v3.1 (regime-safe)

## Correção

- Ano de assinatura e PNCP **não** elevam `legal_confidence` nem `LIKELY_14133`.
- Ano só como contexto de transição / prioridade documental.

## Hierarquia R-A…R-X

| Nível | Regime | proven | legal_confidence | Exige |
|-------|--------|--------|------------------|-------|
| R-A | LEI_14133 | true | high | citação oficial vinculada ou campo estruturado |
| R-B | LIKELY_14133 | false | medium | **sinal normativo positivo 14.133** + vínculo + pós-transição + sem legado |
| R-C | TRANSITIONAL_REGIME_UNRESOLVED | false | unresolved | janela de transição sem fundamento |
| R-D | UNKNOWN | false | none | sem sinais suficientes |
| R-X | LEGAL_REGIME_CONFLICT | false | conflict | citações incompatíveis |

**R-B não aceita:** ano pós-transição + documentos genéricos + ausência de legado.

## Demotions (reprodutível)

Ver `run_manifest.json` → `demotion_replay` e transcript em scratch implementer:
- input sha256 do export 1800
- before LIKELY via regra antiga `signature_year>=2021`
- after via `classify_row` shipped

## Live national

`pncp_datalake.pncp_supplier_contracts` sem `--max-source-rows`.
