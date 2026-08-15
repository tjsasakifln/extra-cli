# CONFENGE contact resolution

## Ownership and boundary

`CONFENGE Prospect` is not a product, repository, CRM, or lead database. It is a distributed capability:

```text
extra-cli facts + public web
  -> account/trigger/offer
  -> decision unit/person/route/evidence/confidence
  -> versioned consumer projection
  -> Warmbly CONFENGE cockpit
  -> human review and channel policy
  -> action/reply/outcome
  -> bounded commercial feedback
```

- **extra-cli owns intelligence:** canonical account identity, domain resolution, people, observed roles, contact candidates, derivation, verification, provenance, freshness, suitability, and consumer-agnostic projections.
- **Warmbly owns activation:** operator review, approval/rejection, messages, campaigns, mailbox effects, replies, outcomes, suppression, and the commercial action ledger.
- Warmbly may materialize the exact projection needed for audit and execution. It does not repeat search or become the identity/reachability source of truth.
- Contact intelligence never grants permission to send. `EMAIL_VALIDATED` is defined operationally by `dui.email-validated-promotion.v1` (see `docs/commercial-intelligence/email-validated-promotion.md`): real known person, defensible affiliation, observed professional-public email or an explicit policy exception, provenance, freshness, suppression clear, no technical hard-fail. Score ≥ X and MX/DNS never promote. Inference does not become observation. A gold-set label is a benchmark verdict, not send authorization.

## Epistemic and route model

The model keeps these dimensions separate:

- person identity confidence;
- observed or inferred role and role confidence;
- corporate-domain confidence;
- email derivation;
- technical verification;
- route suitability;
- evidence freshness and conflicts;
- suppression and policy status.

Operational classes already map to R0-R5. A company switchboard plus a named person is R3 `ROUTES_TO_NAMED_PERSON`, never a personal phone. A pattern-generated email remains `INFERRED`, even when technically plausible. SMTP or MX evidence does not prove mailbox ownership or identity.

## Public web discovery

Public search is a first-class bounded provider when explicitly enabled. The cascade uses cached datalake/campaign facts to obtain the legal name and known site, then runs targeted search before a positive early stop. Search remains disabled by default in generic/test commands so no caller silently creates network traffic.

The query planner records the full contextual plan and executes only the configured budget. It covers:

- company name plus decision roles appropriate to the offer;
- company name plus directorate, partners, contact, email, and telephone;
- CNPJ plus email or telephone;
- known-domain queries for equipe, diretoria, contato, engenharia, comercial, licitacoes, published email patterns, and PDFs;
- named-person email-job shapes (`"NOME" "empresa"`, `"NOME" "@dominio"`, `"NOME" email`, `site:dominio "NOME"`) when QSA/site people are already known.

Each account records executed queries, result count, pages, bytes, failures, duration, backend, domain alternatives, reason codes, and stop reason. Search and crawl failures remain visible as `SOURCE_BLOCKED`, `BUDGET_EXHAUSTED`, or `POLICY_SKIP`; they are not converted to “no route”.

### Domain resolution

Input is CNPJ, legal name, service context, optional known site, and public search hits. The resolver:

1. excludes government, social, directory/aggregator, and common third-party hosts;
2. scores exact CNPJ evidence, legal-name tokens, official-site language, observed known site, and corporate TLD;
3. returns one canonical domain only above a minimum explainable score;
4. returns `UNKNOWN` or ambiguous alternatives when top candidates conflict.

Output is persisted under `extra.domain_resolution` and in the search attempt:

```json
{
  "canonical_domain": "example.com.br",
  "confidence": "HIGH",
  "alternatives": [],
  "reason_codes": ["CNPJ_EXACT_ON_RESULT", "LEGAL_NAME_TOKEN_MATCH"]
}
```

### Crawl and extraction safety

- public HTTP(S) only; private, loopback, link-local, multicast, and reserved targets fail closed;
- robots policy is checked before fetch;
- redirects are revalidated;
- HTML/plain text only in the first slice;
- per-account query, result, page, byte, timeout, retry, and inter-query limits;
- local TTL cache prevents blind rediscovery;
- exact public page text may produce observed person/role/contact evidence;
- email-to-person association requires auditável contextual evidence (same DOM card/block/row, `mailto:` in the person block, explicit “e-mail de Nome”, unique same-window proximity, or a same-domain person page). Local-part first+last is a signal only;
- generic/role/ethics mailboxes (`contato@`, `comercial@`, `licitacoes@`, `conduta@`) never become a person;
- third-party professional domains (`.adv.br`, contabil, advocacia) and non-canonical domains never become identity;
- observed company telephone remains company-owned unless explicit evidence proves otherwise;
- crawl may follow a bounded set of same-domain high-value slugs/anchors (equipe, diretoria, contato, engenharia, comercial, licitações, contratos, administração, imprensa). Not an infinite spider.

### Corporate site contact crawl (isolated layer)

After a domínio corporativo defensável exists, a specialized layer
(`scripts/decision_unit_intelligence/site_contact_crawl.py`) runs behind the
existing `WebCrawler` adapter. It does **not** rewrite domain resolution, the
query planner, or SearXNG/DDGS. `CompanyWebsiteProvider` is the consumer.

Observable chain:

```text
domínio corporativo defensável
  → URLs internas de alto valor
  → pessoa / cargo / email observado
  → evidence bundle (SITE_* reason codes)
```

Seeds: homepage, useful URLs already returned by public search (#392/#394),
`sitemap.xml`, `robots.txt`, and same-domain internal links (menus, anchors,
breadcrumbs). Paths/anchors prioritized: equipe, time, quem somos, diretoria,
liderança, administração, engenharia, comercial, licitações, contratos,
contato, imprensa, representantes, unidades, authors/staff.

Same-domain by default. Subdomain only with an explicit corporate relation
(`www`, `institucional`, `equipe`, `contato`, `engenharia`, `comercial`,
`portal`, `site`). Login, carrinho, webmail, search infinito, calendário,
parâmetros combinatórios, and authenticated networks are skip-listed.
URLs are canonicalized (fragment, `www`, tracking params, trailing slash)
and de-duplicated. A huge sitemap is truncated at `max_sitemap_urls`; the
crawl stops at the per-domain budget. Static HTML first; no browser farm.

#### Budget defaults (`SiteCrawlBudget`)

| Limit | Default | Meaning |
|---|---|---|
| `max_pages` | 12 | Fetches per domain (including sitemap/robots) |
| `max_depth` | 3 | Link-follow depth from seeds |
| `max_bytes` | 2_500_000 | Total response bytes per domain |
| `timeout_seconds` | 20.0 | Wall-clock budget for the whole domain crawl |
| `max_redirects` | 5 | Redirect hops counted toward the domain |
| `requests_per_minute` | 20 | Rate ceiling (fixture crawlers skip sleep) |
| `max_sitemap_urls` | 80 | Sitemap `<loc>` entries parsed before scoring |

These are independent of the #392 search budget (`SearchBudget.max_pages=4`).

#### SITE_* reason-code contract

Strong promotion (named-associated) **only** when one of these is present and
the structural evidence is unique:

| Code | Meaning |
|---|---|
| `SITE_PROFILE_EMAIL` | Unique email on an individual profile page |
| `SITE_TEAM_CARD_EMAIL` | Unique name+email inside a card / unique table row |
| `SITE_MAILTO_ASSOCIATED` | `mailto:` inside the same card/profile as one person |
| `SITE_STRUCTURED_CONTACT` | JSON-LD / microdata Person coherent with visible text |

Never promoted to a person:

| Code | Meaning |
|---|---|
| `SITE_GENERIC_ONLY` | Footer/header/nav or generic/role mailbox |
| `SITE_JS_BLOCKED` | Shell page, almost no visible text, scripts only |
| `SITE_NO_HIGH_VALUE_PATH` | Budget spent, no equipe/diretoria/contato-class URL |
| `SITE_STALE_OR_UNKNOWN` | Ex-colaborador, holding/foreign domain, no freshness |

Weak association (same text window, two nearby names, cross-card mailto
whose local-part names a *different* visible person) stays **candidate**.
`SAME_TEXT_WINDOW` from the #392 search-page associator is **not** used to
promote SITE_* named emails. Stop-the-line: any known false association
becomes a fixture and blocks promotion.

#### Recommendation

Keep this layer specialized and budget-hard. Do not grow it into a generic
spider, do not add a browser farm, and do not promote footer or proximity
hits. If the TRACK_A 30 canary shows incremental named-associated yield with
zero false associations, raise `max_pages` only after another canary — never
by relaxing association rules.

Fixture canary on the in-repo corporate corpus (homepage-only vs deep bounded
crawl, same `site-crawl` entry, no live spider):

| Metric | Baseline | Deep bounded |
|---|---|---|
| high-value pages | 0 | 4 |
| pages / account | 3 | 7 |
| emails observed | 1 | 6 |
| named-associated | 0 | 5 |
| false association | 0 | 0 |
| footer promoted | 0 | 0 |

Pages that most generate yield: `equipe` (team cards + individual profile),
then structured/obfuscated contact pages. Live TRACK_A 30 requires SearXNG or
DDGS; it was not invented when those backends were unreachable.

Published email-discovery classes stay distinct: `OBSERVED_DIRECT_EMAIL_IDENTITY_ASSOCIATED`, `OBSERVED_DIRECT_EMAIL_IDENTITY_UNRESOLVED`, `INFERRED_PATTERN_EMAIL`, `GENERIC_MAILBOX`, `ROLE_MAILBOX`, `DOMAIN_ONLY`, `TECHNICALLY_PLAUSIBLE`, `EMAIL_VALIDATED` (only when the existing email-safe policy already allows), `BLOCKED` / `UNKNOWN`. Org email patterns are versioned evidence (`org-email-pattern.v1`) derived only from OBSERVED same-domain addresses; generated candidates remain `INFERRED` / `CANDIDATE_UNVERIFIED` even with MX.

## Replaceable adapters and licenses

Evaluation date: 2026-08-14. Recheck license and maintenance before upgrades.

| Project | Repository | License | Decision and reuse |
|---|---|---|---|
| DDGS | <https://github.com/deedy5/ddgs> | MIT | Selected for the small local canary through a lazy adapter. It is replaceable and rate-limited; engine behavior is not treated as a stable contract. |
| SearXNG | <https://github.com/searxng/searxng> | AGPL-3.0 | Selected only as an optional HTTP service boundary. No SearXNG code is copied or linked into extra-cli. CONFENGE runs a private official image (digest-pinned). A modified/network deployment requires offering corresponding source (AGPL-3.0 §13). See [`../ops/searxng-private-backend.md`](../ops/searxng-private-backend.md). |
| Crawl4AI | <https://github.com/unclecode/crawl4ai> | Apache-2.0 | Evaluated and deferred. It is active and capable, but browser/runtime weight is unnecessary for the first static-HTML slice. The crawler interface allows later adoption. |
| theHarvester | <https://github.com/laramies/theHarvester> | GPL metadata / repository license ambiguity | Not adopted. Its broad OSINT surface and licensing posture add more risk and complexity than this targeted professional-public-data use case needs. |
| dnspython | <https://github.com/rthalley/dnspython> | ISC | Selected for passive DNS/MX resolution. It never performs mailbox ownership or SMTP identity proof. |

The first slice reuses existing `httpx`, Beautiful Soup, and lxml dependencies. No paid data provider, authenticated LinkedIn scraping, breach data, evasion, or copied third-party code is introduced.

## Verification boundary

`--verify-email-dns` runs syntax, domain, DNS and MX checks with a TTL cache. Reports explicitly preserve `MX_PRESENT_NOT_MAILBOX_PROOF`, `UNKNOWN_NOT_PROBED` for catch-all, and `SKIPPED_POLICY` for SMTP. Direct candidates remain `UNVERIFIED_DIRECT_CANDIDATE`; generic and role mailboxes remain generic. No passive result proves a person owns a mailbox.

SMTP and catch-all probing are intentionally not implemented in the default adapter. A future implementation requires an explicit policy, controlled egress, reputation safeguards, rate limits, retry/timeouts, a kill switch, and evidence that the probe is technically reliable and lawful for the exact use case.

## Projection contract

The current account projection remains `confenge.decision_unit_account.v1`. Additive fields include persisted field evidence and `extra.domain_resolution`. `confenge.decision_unit_queue.v1` remains the multichannel operator projection. `confenge.outreach.v1` remains the narrower observed-email-safe projection consumed by Warmbly.

Warmbly must display the route's person, role, company, relevance, channel, derivation, verification, confidence dimensions, source links, freshness, warnings, and policy status. It must not reinterpret an inferred route as observed or sendable.

## Feedback boundary

Warmbly owns delivered, bounce, replied, positive reply, wrong person, left company, generic mailbox, referral, meeting, no interest, and suppression events. extra-cli may consume the smallest idempotent signal needed to update a route, pattern, role prior, or golden case. It does not copy campaign or CRM state.

## Metrics

Every run manifest records public-web accounts attempted, domains resolved, searches, pages, bytes, and external cost. The account ledger also preserves duration, cache/search attempts, failures, and stop reasons. Decision-unit and route coverage remain in the existing funnel; Warmbly remains authoritative for approved, sent, delivered, bounced, replies, positive replies, meetings, and opportunities.

The North Star is not email coverage. It is `qualified account -> defensible decision-maker route -> observed commercial outcome`.

## Local runbook

Install dependencies, then choose one explicit backend:

```bash
# Small zero-cost canary through the MIT adapter
python3 -m scripts.decision_unit_intelligence run \
  --out /tmp/confenge-prospect-10 \
  --limit 10 \
  --search-backend ddgs \
  --search-max-queries 2 \
  --search-results-per-query 4 \
  --crawl-max-pages 2 \
  --verify-email-dns

# Self-hosted metasearch boundary
CONFENGE_SEARXNG_URL=https://search.internal.example \
python3 -m scripts.decision_unit_intelligence run \
  --out /tmp/confenge-prospect-10 \
  --limit 10 \
  --search-backend searxng
```

Raw search/crawl cache stays under `.cache/confenge-prospect/` and is not committed. Operator output and projections remain review-only. No command enables auto-send.
