# Compliance — contratação direta / dispensa por valor

## Premissa

O sistema **não** afirma que a CONFENGE tem direito à contratação direta nem que o órgão pode contratá-la automaticamente.

Estado permitido: `POTENTIALLY_ELIGIBLE_FOR_DIRECT_CONTRACTING`

Estados proibidos: `DISPENSA_GARANTIDA`, `CONTRATAÇÃO_DIRETA_AUTORIZADA`, `ÓRGÃO_PODE_CONTRATAR`, `SEM_LICITAÇÃO`, `CONTRATAÇÃO_ASSEGURADA`.

## Tetos 2026 (federais)

Config: `config/legal/direct_contracting_thresholds.yaml`

| Artigo | Object class | Valor (estritamente inferior) |
|--------|--------------|-------------------------------|
| 75, I | ENGINEERING_SERVICE | R$ 130.984,20 |
| 75, II | OTHER_SERVICE | R$ 65.492,11 |

Vigência: Decreto nº 12.807/2025 a partir de 2026-01-01.  
**Igual ao teto não é elegível.**

Atualização anual: incluir nova linha YAML com `effective_from` — sem alterar código.

## Classificação de objeto

Não se presume engenharia só porque a prestadora é de engenharia. Classes:

- `ENGINEERING_SERVICE`
- `OTHER_SERVICE`
- `REQUIRES_HUMAN_LEGAL_CLASSIFICATION`

Sem alegação comercial de teto se ambíguo.

## Fracionamento

- Teto ≠ meta de preço
- `DIRECT_CONTRACTING_SUM_UNKNOWN` quando somatório anual da UG/mesma natureza for desconhecido
- Sem claim de aderência ao limite agregado nesse caso

## Art. 117

CONFENGE pode assistir/subsidiar; **não** aplicar sanções, autorizar pagamentos, homologar, adjudicar, assinar como autoridade, substituir o fiscal.
