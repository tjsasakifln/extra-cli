# CONFENGE-EXTRA-AUTHORITY-SINGULARITY-02

Sanitized campaign report. No DSN, tokens, cookies, restricted documents or unnecessary PII.

## Status

**READY** — one `HANDOFF_READY` pack. `READY.json` xor `BLOCKED.json` (no `BLOCKED.json` as final).

Campaign: `CONFENGE-EXTRA-AUTHORITY-SINGULARITY-02`  
Branch: `goal/authority-singularity-20260818`  
Issue comment (start, no duplicate): https://github.com/tjsasakifln/extra-cli/issues/414#issuecomment-5323055908  
Base: `origin/main` `b668f02a` (PR #432 claim URL+bytes+sha256+locator bind)

## Selected contract

- PNCP `14862788000150-2-000069/2026`
- Object (listing FACT): pavimentação em paralelepípedo de 4.710,00 m² de ruas no município de São Gonçalo do Piauí – PI
- Contracting entity CNPJ: `14862788000150`
- Supplier CNPJ: `53291908000168`
- Listing `valor_global`: `719177.48 BRL`
- Listing vigência: `2026-07-08` a `2027-07-08`
- UF in listing unit field: PI (município da unidade listada: Teresina; o objeto cita São Gonçalo do Piauí). Both strings are recorded as written. No inference about the discrepancy.

SC cohort first: 80 SC listings in the 30-day window were scanned. 0 entered as AEC. Typical SC objects in that window were hospital supplies, food, kitchen utensils and stationery. National fallback then selected AEC contracts. This paving contract was the first integral READY.

## Singularity

Primary contract PDF (`/arquivos/1`, sha256 `64a238e6094f4d093f1ee970820fd277bcd34a66457d776a59225219b8e77604`) documents, quoted from the retrieved page text:

- cláusula 12.3: o índice de reajuste é o **Índice Nacional da Construção Civil – Coluna 35**, publicado pela Fundação Getúlio Vargas (página 14);
- cláusula 12.2: reajuste após interregno de um ano, contado da data do orçamento a que a proposta se referir.

The insight and PDF FACTs quote those strings. They do **not** name DNIT or reequilíbrio (those words are absent from this PDF).

`/termos` for this contract returned HTTP 204 (empty). That is recorded as `not_found` on that URL, not as “there are no terms in the world”.

Apostilamento de gestor/fiscal with zero value delta is **not** treated as a singularity (tested).

## Replayable calculation

```
valor_global 719177.48 BRL / 4710.00 m² = 152.6916 BRL/m²
rounding: quantize 0.0001
denominator: documented area in the official object text
```

This is a unit price derived from published global value and published area. It is not cost/km, not BDI, and not a peer comparison.

## Pack identity

| Field | Value |
|---|---|
| `analysis_id` | `13ec615146b3d348190a9b0b9148831e` |
| producer_commit | `7958f2048b36299d6f89f80faa3b4f208a7dbc63` |
| dossier `content_hash` | `ee6e40fd903453438d3b6b9121dd1e8cba3877ac00bc32e7c845435022cb37b1` |
| `READY.json` `root_content_hash` | `47a18e666040551f124b1edaa267bbb033878b68cf7925584b9529ac9297bd5a` |
| manifest `content_hash` | see live rendezvous `manifest.json` (clocks excluded from `content_hash`) |
| listing sha256 | `1ffbc82f73f8eca8eeac0b0ddc22860b2b3f261dba39191b7e77b87b8cde33ee` |
| PDF sha256 | `64a238e6094f4d093f1ee970820fd277bcd34a66457d776a59225219b8e77604` |

Two identical bounded canaries (`--limit 20 --start-date 2026-07-19 --end-date 2026-08-18 --as-of 2026-08-18T12:00:00Z --skip-pages`) produced the same `analysis_id`, dossier `content_hash` and `root_content_hash`. Manifest `generated_at` differs; temporal clocks are excluded from content hashes.

`publication_authorization=false`, `index_authorization=false`, `production_write=false`, `backfill=false`. No human approval was simulated.

## FACT binding

Every FACT was checked with shipped `verify_claim_url_hash`: sha256 equals bytes retrieved from that FACT’s own URL. Listing FACTs use the consulta JSON. PDF FACTs use the `/arquivos/1` URL and page locators. The SPA `/app/contratos/...` is `portal_url` only and does not inherit another endpoint’s hash.

## Tests

```
python3 -m pytest tests/historical_contract_authority/ tests/official_contract_semantics/ -o addopts= -q
# 109 passed
```

New/updated gates: locação de veículos discarded; generic purchase discarded; `mão de obra` alone is not AEC; SPA cannot inherit listing sha256; READY requires located FACTs + singular insight; READY xor BLOCKED; two canaries share identity/hash; apostilamento gestor/fiscal is not insight; PDF reajuste page is material; Brazilian `4.710,00 m²` ratio; FGV Coluna 35 page text does not invent DNIT or reequilíbrio; process_document FACTs are `fact-indice`/`fact-reajuste`/`fact-data_base`, not `Objeto oficial`.

## Rendezvous (outside git)

`$HOME/.local/share/confenge/handoffs/contract-analysis/official-live-01/`

Contains `READY.json`, `manifest.json`, `dossiers/13ec615146b3d348190a9b0b9148831e.json`, `SHA256SUMS.txt`, `replay.txt`, `README.md`. No `BLOCKED.json`.

## Consumer instruction (web-cfg)

Do not INDEX. Do not treat `publication_authorization` as approval. Locate the pack here:

```
$HOME/.local/share/confenge/handoffs/contract-analysis/official-live-01/READY.json
```

If `CONFENGE_HANDOFF_DIR` is set, the same relative path is `$CONFENGE_HANDOFF_DIR/contract-analysis/official-live-01/`.

Replay:

```bash
python3 -m scripts.historical_contract_authority --mode official-live \
  --limit 20 --start-date 2026-07-19 --end-date 2026-08-18 \
  --as-of 2026-08-18T12:00:00Z --skip-pages --output <isolated-dir>
```

One human action remains: hash-bound editorial review in web-cfg. The producer does not authorize publication or index.

## What the documents show / what cannot be concluded

The official listing and the official contract PDF show identity, a published global value, a published area, a one-year reajuste clause referenced to the proposal budget date, and measurement language. They do not demonstrate that a reajuste was paid, that a measurement was approved, or that any party is at fault.

Prohibited conclusions: irregularidade, culpa, sobrepreço, fraude, case, cliente, relação comercial, INDEX.

## Residual risk

- DSN was absent (`LOCAL_DATALAKE_DSN` / `DATABASE_URL` unset; local 5432/5433 closed). The public official route resolved a READY without it. No `FOUNDER_ACTION_REQUIRED_DSN.txt`.
- SC 30-day listings in this window had no AEC object. READY is a Brazil fallback (PI paving), recorded in `query_window.sc_denominator`.
- Listing unit município (Teresina) differs from the object município (São Gonçalo do Piauí). Left as written.
- `/termos` 204 is unavailability-of-terms-on-that-URL, not proof that no apostille exists elsewhere.

## Code change

Official-live was patched so that this campaign could reach a real AEC singularity instead of selecting locação/generic listings: AEC discard, SC scan vs AEC shortlist, `/termos` 204 as `not_found`, material term filter, contract PDF clause extract, BRL/m² calculation. No cosmetic-only commit.

PR: https://github.com/tjsasakifln/extra-cli/pull/433
