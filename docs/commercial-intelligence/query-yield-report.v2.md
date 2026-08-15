# Query yield report — query-policy.v2

Fonte: `python -m scripts.decision_unit_intelligence.query_planner` (mesmo entry que `decision_unit_intelligence query-yield`) sobre o Track A de 30 contas reais. O pedido de 100 usou as 30 disponíveis — o índice de campanha neste workspace não tem CNPJs extras; nenhuma conta foi inventada.

Ranking por yield downstream (não por SERP count). SearXNG/DDGS ao vivo falharam neste ambiente (URL SearXNG ausente; DDGS `ConnectTimeout`). O relatório abaixo é o mesmo entry em replay das mesmas contas.

## Famílias

| família | searches | useful/s | observed email/s | identity-associated/s |
|---|---:|---:|---:|---:|
| SITE_PATH | 40 | 1.0 | 0.70 | 0.0 |
| DOCUMENT | 6 | 1.0 | 0.0 | 0.0 |
| PERSON | 12 | 1.0 | 0.0 | 0.0 |
| ROLE | 0 | 0.0 | 0.0 | 0.0 |
| COMPANY | 26 | 0.0 | 0.0 | 0.0 |

Fonte fraca: 2 URLs, série separada. Não entram em observed/identity.

## Top / bottom (shape)

- Top: `site_contato`, `site_diretoria` — 0.82 observed email/search (mailboxes genéricos no site oficial).
- Bottom: ROLE (0 execuções após early-stop) e COMPANY em contas sem domínio (hits de diretório = fonte fraca).

## SearXNG vs DDGS (replay)

- SearXNG executa `filetype:pdf`; DDGS marca o operador como sem suporte (3 skips, não miss vazio).
- observed email/search: 0.333 (SearXNG) vs 0.346 (DDGS) — denominador maior no SearXNG por DOCUMENT extra.
- identity-associated/search: 0.0 vs 0.0.
- **no_gain = true** para EMAIL OBSERVED / IDENTITY-ASSOCIATED por busca.

## Policy default nova

`query-policy.v2` (contrato #393):

- family_order: SITE_PATH → DOCUMENT → PERSON → ROLE → COMPANY
- budgets: SITE_PATH 4, DOCUMENT 3, PERSON 3, ROLE 1, COMPANY 4
- adaptive: pessoa+domínio → SITE_PATH/PERSON/DOCUMENT; sem domínio → COMPANY primeiro
- early-stop: 1 identity-associated, ou 2 observed emails, ou 2 buscas seguidas sem yield
- 245 queries planejadas → 84 executadas (161 early-stop)

Identidade associada ficou em zero neste cohort: e-mails publicados são `contato@` / `adm@` / `rh@`, não pessoa↔email. PERSON não ganha volume até haver evidência de associação.
