# Query yield report — query-policy.v2

Fonte: `python -m scripts.decision_unit_intelligence.query_planner` sobre o Track A de 30 contas reais. O pedido de 100 usou as 30 disponíveis — o índice de campanha neste workspace não tem CNPJs extras; nenhuma conta foi inventada.

Replay **só devolve URLs de `site`/`fonte` observados**. Não inventa `/equipe` nem `/documentos/ata.pdf`. E-mail no snippet só quando a observação registrou o endereço e a query pede email/`@`.

SearXNG/DDGS ao vivo falharam neste ambiente (URL SearXNG ausente; DDGS `ConnectTimeout`). Ranking por yield downstream (não SERP count). Duas corridas no mesmo entry: ranking idêntico.

## Famílias (replay honesto)

| família | searches | useful/s | observed email/s | identity-associated/s |
|---|---:|---:|---:|---:|
| COMPANY | 66 | 0.88 | **0.42** | 0.0 |
| PERSON | 6 | 1.67 | 0.0 | 0.0 |
| SITE_PATH | 3 | 0.0 | 0.0 | 0.0 |
| DOCUMENT | 0 | 0.0 | 0.0 | 0.0 |
| ROLE | 0 | 0.0 | 0.0 | 0.0 |

Fonte fraca em série separada. 75 buscas executadas, 106 early-stop.

## Top / bottom

- Top: `cnpj_email`, `company_legal_email` — 0.47 observed email/search (mailboxes genéricos no site/fonte observados).
- Bottom: SITE_PATH slugs (`contato`/`equipe`) sem path correspondente no URL observado; ROLE/DOCUMENT cortados pelo early-stop.

## SearXNG vs DDGS

- observed/search e identity/search: empate (0.0 uplift).
- **no_gain = true** para EMAIL OBSERVED / IDENTITY-ASSOCIATED.
- DDGS continua sem `filetype:`; skips não viram miss vazio.

Identidade associada = 0: e-mails observados são `contato@` / `adm@` / `rh@`.

## Policy default nova

`query-policy.v2`:

- family_order: COMPANY → PERSON → SITE_PATH → DOCUMENT → ROLE
- budgets: COMPANY 4, PERSON 3, SITE_PATH 1, DOCUMENT 1, ROLE 1
- adaptive: pessoa+domínio → COMPANY/PERSON/SITE_PATH; sem domínio → COMPANY primeiro
- SITE_PATH reduzido: slugs não batem em homepages observadas
- PERSON não é desligado: precisa rodar quando há gente nomeada
