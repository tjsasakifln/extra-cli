# Story: Higiene de identidade e determinismo do loader — guard `\bbanco\b` morto e `razao_social` não determinístico

## Status

**Draft**

## Risk Level

**STANDARD** (a confirmar na validação). Nenhuma escrita em produção; duas correções localizadas com efeito medível em recall de exclusão e em estabilidade de fingerprint.

## Story-mãe (origem destas dívidas)

`docs/stories/story-outbound-sector-classifier-false-positive-01.md` — dívidas `MNT-001` e `MNT-004`, registradas pelo @dev (T9.8), ratificadas pelo @po (Ratificação nº 5) e confirmadas pelo @qa na iteração 2 (severidade **low** ambas). Nenhuma foi corrigida na story-mãe, por decisão correta: estão fora dos ACs e alteram comportamento sem medição própria.

## Escopo — duas dívidas independentes, mesma família

### `MNT-001` — guard `\bbanco\b` morto em `identity.py`

`scripts/confenge_universe/identity.py`, em `_looks_like_non_construction_supplier`: `normalize_name` devolve o nome em **MAIÚSCULAS** e a regex do guard não usa `re.IGNORECASE`. O guard portanto **nunca casa** — está morto. Corrigir altera o recall da exclusão de bancos e **exige medição do delta** antes e depois, na população real, para não introduzir supressão nova sem blast radius conhecido.

### `MNT-004` — `razao_social` não determinístico → `input_fingerprint` instável

`scripts/confenge_target_fit/loader.py:143-146,170` seleciona `razao_social` **sem `ORDER BY`**, logo a variante escolhida entre múltiplos `fornecedor_nome` é sorteio do plano de execução. Isso torna `input_fingerprint` (`scripts/confenge_target_fit/fingerprint.py:128`) instável, o que pode causar **reprocessamento espúrio** ou, pior, **ausência de reprocessamento devido**.

**Mitigado, não resolvido, pela story-mãe:** a superfície C4 do gate parafiscal (`razao_social` + `nome_fantasia` + todo `fornecedor_nome` distinto) torna a **decisão do gate** independente do sorteio — medição do @dev mostrou 68 raízes suprimidas de forma estável contra 58 se dependesse do primeiro nome sorteado. A instabilidade de fingerprint permanece.

## Scope

**IN:**
- Adicionar `ORDER BY` determinístico na seleção de `razao_social` em `loader.py`; teste que prova estabilidade do `input_fingerprint` em execuções repetidas.
- Corrigir o guard `\bbanco\b` (case-insensitive ou normalização coerente), **com medição do delta de exclusão** na população real antes/depois.

**OUT:**
- Alterar a taxonomia parafiscal ou o gate C3 (entregues pela story-mãe).

## Owner e prazo

| Campo | Valor |
|---|---|
| Owner | @po (Pax) — refinar com @sm |
| Origem | `MNT-001` e `MNT-004` (severidade low) — gate `docs/qa/gates/outbound-sector-classifier-false-positive-01.yml` |
| Prazo de refinamento | até 2026-09-15 (14 dias do fechamento da story-mãe) |
| Bloqueada por | Nada. Pode ser feita após a publicação da story-mãe. |

## Change Log

| Date | Version | Description | Author |
|---|---|---|---|
| 2026-09-01 | 0.1.0 | Draft criado no fechamento da story-mãe para materializar `MNT-001` e `MNT-004` como itens rastreáveis com owner e prazo | Pax (@po) |
