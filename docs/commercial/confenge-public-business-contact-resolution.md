# CONFENGE public business contact resolution

**Schema:** `confenge-contact-candidates-v1`  
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
```

Artifacts:

- `confenge-contact-candidates-v1.jsonl` — one JSON object per CNPJ/account
- `run_manifest.json` — run metadata + checksum

## Adapters

| Adapter | Source |
|---------|--------|
| `registry` | Local RFB release via `scripts.company_registry.lookup`; optional BrasilAPI only with `--allow-network` |
| `site` | Institutional site extracts / fixtures |
| `public_docs` | Already-ingested contract/licitação contact extracts |
| `contact_page` | Public team/contact pages + human outcomes (DNC) |
| `web_search` | Optional provider interface; **NoOp by default**; disabled in tests |

No private social scraping. No captcha/evasion. No outbound verification mail. No WhatsApp account probing.

## Policy highlights

- Pattern-guessed personal emails → `CANDIDATE_UNVERIFIED`, never enrollable, never recommended primary.
- Exact observed emails preserved in `email_display`.
- BR phones → E.164; type `mobile` / `landline` / `unknown`.
- `whatsapp.consent_status` defaults to `UNKNOWN` / `NO_OPT_IN`; `OPTED_IN` only with provenance.
- DNC / bounce dominate ranking and block recommendation.
- Stale `source_date` decays freshness and confidence.
- Ranking is **service-aware and explainable** (not purchase probability).

## Composition with CONFENGE / Warmbly

- Commercial lead scoring remains in `scripts/commercial_leads` (no purchase-prob rewrite).
- Outreach kits continue to treat absence as `NOT_AVAILABLE`.
- This module supplies **channel candidates** with verification/consent so Warmbly (or human send) can decide without inventing people.
