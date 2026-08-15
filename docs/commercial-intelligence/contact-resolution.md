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
- Contact intelligence never grants permission to send. `EMAIL_VALIDATED` remains restricted to the existing email-safe policy. Inference does not become observation.

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
- known-domain queries for directorate, engineering, contact, published email patterns, and PDFs.

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
- email-to-person association requires the observed person's first and last name in the address local part in this first slice;
- generic mailboxes never become named contacts;
- observed company telephone remains company-owned unless explicit evidence proves otherwise.

## Replaceable adapters and licenses

Evaluation date: 2026-08-14. Recheck license and maintenance before upgrades.

| Project | Repository | License | Decision and reuse |
|---|---|---|---|
| DDGS | <https://github.com/deedy5/ddgs> | MIT | Selected for the small local canary through a lazy adapter. It is replaceable and rate-limited; engine behavior is not treated as a stable contract. |
| SearXNG | <https://github.com/searxng/searxng> | AGPL-3.0 | Selected only as an optional HTTP service boundary. No SearXNG code is copied or linked into extra-cli. A modified/network deployment requires explicit license compliance review. |
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
