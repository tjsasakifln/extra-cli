# official-contract-observation/1.1

Camada canônica, append-only e fail-closed de observações semânticas extraídas de fontes oficiais de contratos públicos.

Esta camada **não** classifica editorialmente, **não** publica e **não** promove candidato. Ela observa.

## Taxonomia epistemológica

O `status` de reconciliação (`observed` / `conflicted` / `superseded_by_official_evidence` / `unknown`) não é a taxonomia de certeza. A certeza vive em `epistemic_class` e `field_epistemics`.

| Classe | Significado | Quando ocorre |
|---|---|---|
| `FACT_OFFICIAL` | Campo ou observação explicitamente sustentado em fonte oficial | campo estruturado ou rótulo oficial presente |
| `OBSERVATION_DERIVED` | Transformação determinística de fatos oficiais | export `#415` mapeia `valor_global`/`valor_contratado` → `valor_integral_nominal` com `derivation_method` |
| `UNKNOWN` | Campo necessário não demonstrado | valor `null` sem marca oficial de inaplicabilidade |
| `HOLD_FOR_DATA` | Consumo bloqueado por campo(s) `UNKNOWN` ou conflito | `hold_report` / `reason_codes` |
| `NOT_APPLICABLE` | Inaplicabilidade demonstrável na fonte | `not_applicable_fields` ou token oficial `não se aplica` / `n/a` |
| `NOT_FOUND` | Busca delimitada (URL oficial específica) devolveu 404/vazio | `SourceUnavailability.epistemic_class` |
| `UNAVAILABLE` | Transporte/DSN/timeout | não é resultado de busca |
| `ABSENT` | Alias de busca delimitada com 410 | nunca significa inexistência no mundo |

`asserts_world_absence` é sempre `false`. Ausência de texto, tabela, processo ou campo **não** vira fato negativo.

## Diagrama

```
JSON/JSONL | HTML/texto | documentos processados | janela live-readonly
        → extract (determinístico, sem LLM)
        → validate (fail-closed)
        → reconcile (append-only; conflito preservado)
        → export-comparables     → scripts.contract_comparables (#415)
        → export-publication-evidence → scripts.contract_publication (#414)
```

## Status

`observed` | `conflicted` | `superseded_by_official_evidence` | `unknown`

Ausência permanece `null`/`unknown`. Silêncio de fonte não é fato negativo.

## Validação fail-closed

- observação sem documento/registro oficial identificável
- valor sem `value_semantic`
- unidade/quantidade inferidas só por contexto genérico
- vigência ou aditivo presumidos pela ausência de publicação
- inferência por ausência
- merge de CNPJ raiz com estabelecimento

## Reconciliação

Conflitos oficiais são agrupados (`conflict_group_id`) e ambos os lados permanecem. Supersessão exige relação oficial explícita (`supersedes_document_id` / `supersedes_observation_id`). Hash de documento diferente gera nova observação.

## Exportadores

`export-comparables` projeta `valor_global` / `valor_contratado` / `valor_integral_nominal` para o semantic canônico do engine #415. Demais semânticas passam intactas. Conflito e unknown permanecem unknown.

`export-publication-evidence` emite snapshot consumível por `python3 -m scripts.contract_publication rank` mais matriz de cobertura e motivos de `HOLD_FOR_DATA`. Não emite `PUBLISHABLE_*` / `INDEX`.

## Live

`live-readonly` consulta somente fontes oficiais, com timeout, retry limitado, rate limit, cache e User-Agent identificável. Indisponibilidade é registrada como indisponibilidade.

Declaração: **no publication, no production write, no inferred fact from absence**.
