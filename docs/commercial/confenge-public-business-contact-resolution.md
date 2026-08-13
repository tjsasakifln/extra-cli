# CONFENGE public business contact resolution

**Schema:** `confenge-contact-candidates-v1` / contract version `1.3.0`
**Package:** `scripts/confenge_contact_resolution`

## Goal

Resolve **legitimate public business contacts** for CONFENGE outreach so Warmbly can choose channel (email / phone / hold). This is **not** “find any email” and **never invents identity**.

## CLI

```bash
# Single CNPJ
python -m scripts.confenge_contact_resolution resolve \
  --cnpj 11222333000181 \
  --output-dir output/confenge-contacts/run-1 \
  --service-context licitações \
  --fixtures-dir path/to/optional/fixtures

# Batch
python -m scripts.confenge_contact_resolution batch \
  -i cnpjs.txt \
  -o output/confenge-contacts/run-batch \
  --service-context claims_reajuste \
  --max-workers 4

# Auditable network enrichment (never sends a verification message)
python -m scripts.confenge_contact_resolution enrich-batch \
  -i eligible-accounts.jsonl \
  -o /protected/contact-enrichment/run-1 \
  --service-context claims_reajuste \
  --allow-network --enable-web-search --check-mx --no-resume
```

Artifacts:

- `confenge-contact-candidates-v1.jsonl` — one JSON object per CNPJ/account
- `contact-source-attempts.jsonl` — ordered source attempts, semantic dates,
  reason codes, limitations and reproducible evidence identifiers
- `contact-discovery-terminals.jsonl` — one terminal state per account
- `contacts_verified.jsonl`, `contacts_review_required.jsonl`,
  `contacts_rejected.jsonl`, and `no-contact.jsonl` — mutually auditable outputs
- `warmbly_feed/contacts.jsonl` — candidate projection; only a strict named
  human can appear in `contacts_enrollable.jsonl`
- `manifest.json` — run metadata and artifact inventory

## Adapters

| Adapter | Source |
|---------|--------|
| `registry` | Local RFB release via `scripts.company_registry.lookup`; optional BrasilAPI only with `--allow-network` |
| `site` | Institutional site extracts / fixtures |
| `public_docs` | CNPJ-linked contract/licitação extracts; exact full-CNPJ or equivalent strong document binding is mandatory for identity proof |
| `contact_page` | Public team/contact pages + human outcomes (DNC) |
| `web_search` | Optional Brave, DuckDuckGo HTML, and Bing HTML discovery providers; snippets are leads only and never final identity proof |

No private social scraping. No captcha/evasion. No outbound verification mail. No WhatsApp account probing.

## Policy highlights

- `EMAIL_SEND_READY` means a real named human: explicitly published name,
  commercially suitable role and nominal email, with a complete auditable
  source chain. A syntactically valid company mailbox is not sufficient.
- Generic and functional purposes (`contato`, `comercial`, `vendas`, finance,
  engineering, procurement, administration and equivalents) fail closed.
- Pattern-guessed personal emails → `CANDIDATE_UNVERIFIED`, never enrollable, never recommended primary.
- Names and roles are never derived from an email local-part.
- Public-document search hits are downloaded only after institutional/company
  relevance checks, then rejected unless the exact CNPJ is present. PNCP
  contracting-authority documents cannot be attributed to the supplier by
  name/root similarity.
- Exact observed emails preserved in `email_display`.
- BR phones → E.164; type `mobile` / `landline` / `unknown`.
- `whatsapp.consent_status` defaults to `UNKNOWN` / `NO_OPT_IN`; `OPTED_IN` only with provenance.
- DNC / bounce dominate ranking and block recommendation.
- `source_published_at`, `observed_at`, and `verified_at` are distinct.
  Reading an old artifact does not create a new observation or publication
  date; live HTTP retrieval supplies `observed_at`, never a fabricated
  `source_published_at`.
- Cache identity includes schema/contract version, network/MX policy, adapter
  set and discovery budget. Changing evidence policy invalidates old results.
- Ranking is **service-aware and explainable** (not purchase probability).

## Ordered source ladder and terminality

The network cascade records these steps in order: official company site;
CNPJ-linked administrative/process documents; PNCP/procurement/transparency;
professional councils and legitimate associations; complementary public
company pages; and official registry/QSA corroboration. Search results are
bounded and filtered before download, but every accepted document must prove
the exact CNPJ. Registry/QSA may corroborate a role and active registration;
it never creates an email.

`CONTACT_EXHAUSTED` is legal only when every ladder step completed without an
external blocker. Provider outage, inaccessible document, CAPTCHA/auth wall or
budget exhaustion yields `CONTACT_EXTERNAL_BLOCKER`/`CONTACT_RETRY_PENDING`,
never a false exhaustion. Cache-only reruns preserve the original attempt time.

## Composition with CONFENGE / Warmbly

- Commercial lead scoring remains in `scripts/commercial_leads` (no purchase-prob rewrite).
- Outreach kits continue to treat absence as `NOT_AVAILABLE`.
- This module supplies **channel candidates** with verification/consent so Warmbly (or human send) can decide without inventing people.
