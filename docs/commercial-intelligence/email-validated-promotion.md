# EMAIL_VALIDATED — definição operacional (v1)

**Policy:** `dui.email-validated-promotion.v1`  
**Gold set:** `email-validated-gold.v1`  
**Pergunta que a política responde:** este email está associado à pessoa certa, na empresa certa, com evidência suficiente para entrar na lane de revisão humana?

Não é autorização de envio. Não é `HUMAN_REVIEW_APPROVED`. `auto_send` permanece false.

## Quando um contato pode virar `EMAIL_VALIDATED`

Todas as condições abaixo, simultaneamente:

1. **Pessoa real conhecida** — nome de pessoa, não cargo, não marca, não cidade.
2. **Vínculo pessoa↔empresa defensável** — afiliação `DEFENSIBLE`, não holding opaca, não escritório terceiro.
3. **Email observado** em fonte profissional pública (`company_website`, `official_document`, `administrative_process`, `public_gazette`, `pncp_document`) **ou** exceção nomeada na policy. A v1 não tem exceções aprovadas.
4. **Provenance** — URL da fonte ou snippet congelado, mais data da fonte.
5. **Freshness suficiente** — `FRESH` ou `AGING`. `STALE` (>18 meses sem corroboração) e `UNKNOWN` bloqueiam.
6. **Suppression clear** — `NONE`. DNC / opt-out / hard-bounce / blocked bloqueiam.
7. **Sem hard-fail técnico**.
8. **Identidade explicitamente associada** — não ambígua, não só local-part.
9. **Epistêmico `OBSERVED`**. `INFERRED` nunca vira `OBSERVED`.
10. **Não é caixa genérica, de papel, de marca ou de escritório.**

## O que nunca promove

| Sinal | Por quê |
|---|---|
| Score ≥ X | Score não é identidade. Sozinho nunca promove. |
| MX / DNS | Prova domínio, não pessoa nem mailbox. |
| Padrão first.last | Continua `INFERRED`. |
| Local-part = primeiro+último | Sinal, não prova. |
| `contato@`, `comercial@`, `licitacao1@`, `setep@`, `vitoria@`, `conduta@` | Não é pessoa. |
| Diretório terceiro (Casa dos Dados, Econodata) | Eco, não identidade. |
| `.adv.br` / contabilidade | Empresa errada. |

## Pacote mínimo para adjudicar em <60s

O revisor precisa ver, numa tela:

- pessoa, cargo, empresa
- email
- URL ou snippet congelado
- data da fonte
- pista de associação (card, `mailto:`, “e-mail de Nome”)
- pista de afiliação
- flags técnicos, suppression e freshness

Sem esse pacote, o veredito é `UNKNOWN` — não se inventa positivo.

## Classes humanas

`VALIDATED_DIRECT` · `OBSERVED_BUT_STALE` · `OBSERVED_BUT_IDENTITY_AMBIGUOUS` · `INFERRED_HIGH` · `INFERRED_UNVERIFIED` · `GENERIC_ROLE` · `WRONG_PERSON` · `WRONG_COMPANY` · `UNKNOWN`

Gold-set v1 declara skew: **0 `VALIDATED_DIRECT`** e **0 `INFERRED_HIGH`**. Não balancear com casos inventados.

## Métrica e stop-the-line

- Primária: precisão de `EMAIL_VALIDATED`.
- Secundária: coverage.
- Promover `WRONG_PERSON` ou `WRONG_COMPANY` a `EMAIL_VALIDATED` bloqueia a policy (regression gate).

Warmbly #72/#73 consome evidência fail-closed. extra-cli não edita Warmbly e não habilita envio.
