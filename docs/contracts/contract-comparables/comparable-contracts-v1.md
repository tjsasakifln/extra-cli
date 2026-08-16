# comparable-contracts/1.0 — inbound canary (#415)

Documento de saída versionado do engine `scripts.contract_comparables`.

## Pergunta única deste canário

Como o valor integral nominal de um contrato público de pavimentação se posiciona frente a contratos comparáveis?

Isso **não** é custo por km, custo por m², preço unitário, benchmark de produtividade, diagnóstico de sobrepreço ou ranking nacional.

## Estados

Exatamente um de `COMPARABLE` | `HOLD_FOR_DATA` | `NOT_COMPARABLE`.

O documento oficial **não** emite o campo `valid`. Alias de schema aceito: `public-read-comparable-contracts/1.0`.

## Semântica do valor

`valor_integral_nominal` em `BRL_TOTAL`. `UNKNOWN` nunca vira 0 e nunca entra no denominador.

## Gates (fail-closed)

Unidade incompatível, tipologia ambígua ou distinta, escopo materialmente distinto, regime incompatível, período/geografia sem comparabilidade, amostra fraca, coverage insuficiente, semântica de valor diferente, duplicata/retificação sem resolução, mistura original vs atualizado sem método, e preço por unidade física sem quantidade/unidade/escopo/normalização/amostra verificáveis.

## Consumo

#400 adapta `COMPARABLE` → `PEER_VALID`, `HOLD_FOR_DATA` → `PEER_WEAK`, `NOT_COMPARABLE` permanece. #414 pode anexar o documento; este producer não edita publication candidates.
