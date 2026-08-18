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
| producer_commit | `5984750c14a4653bf64e16ba7547063f3e1cdab9` |
| dossier `content_hash` | `f7ed6bcc70a74e274c222b89293afaf430ed88679264c4189bbe4c033fabcb1b` |
| `READY.json` `root_content_hash` | `5957e02b7982e000ca7dda2a9a06b88769085bc2a163eadcd8d59bd134b26b3e` |
| listing sha256 (contract detail JSON, canonical) | `89a3ba4c49eac6a83d74030981248f352528c115aebb193013e0048ced620303` |
| PDF sha256 | `64a238e6094f4d093f1ee970820fd277bcd34a66457d776a59225219b8e77604` |
| final-run manifest SHA-256 | `75684cd66f95bffb0df4867530d0b86129e47e1bbee0908e889cdba5eb28b586` |
| final-run manifest `content_hash` | `96761c84f17a370fef7e8187f2d2a09b7e998c4fab7d0891bc8bbdf2ec18258c` |

`producer_commit` is the git SHA of the tree that emitted the pack (`git rev-parse HEAD` at run time). It is not required to equal a later docs-only or verify-only PR tip. Ancestry: `5984750c` is a descendant of `7958f204` (the previous emission SHA) and of `2fcff236` (docs-only FGV record). A later closeout commit that only updates this report does not change pack identity.

Two bounded canaries (`--limit 20 --start-date 2026-07-19 --end-date 2026-08-18 --as-of 2026-08-18T12:00:00Z --skip-pages`) from `5984750c` produced the same `analysis_id`, dossier `content_hash`, `root_content_hash`, listing sha256 and PDF sha256. `generated_at` differs (`2026-08-18T12:37:46Z` vs `2026-08-18T12:38:35Z`); `generated_at` / `retrieved_at` / `verified_at` are excluded by `strip_temporal_for_hash`. Manifest `content_hash` also includes the SC scan `candidate_log` of non-selected listings, which changes with the live consulta page; it is not part of READY pack identity (`root_content_hash` is `ids` + dossier hashes only).

`publication_authorization=false`, `index_authorization=false`, `production_write=false`, `backfill=false`. No human approval was simulated.

## FACT binding

Every FACT was checked with shipped `verify_claim_url_hash`: sha256 equals bytes retrieved from that FACT’s own URL (JSON records use the canonical sorted-key digest; PDFs use the raw byte digest). Listing FACTs use the contract-specific PNCP detail URL `https://pncp.gov.br/api/pncp/v1/orgaos/14862788000150/contratos/2026/69` (`$.objetoContrato` / `$.valorGlobal` / `$.dataVigenciaInicio`). PDF FACTs use the `/arquivos/1` URL and page locators. The SPA `/app/contratos/...` is `portal_url` only and does not inherit another endpoint’s hash. A shared consulta pagination page is not the listing FACT URL.

## Tests

```
python3 -m pytest tests/historical_contract_authority/ tests/official_contract_semantics/ -o addopts= -q
# 118 passed
```

New/updated gates: locação de veículos discarded; generic purchase discarded; `mão de obra` alone is not AEC; SPA cannot inherit listing sha256; READY requires located FACTs + singular insight; READY xor BLOCKED; two canaries share identity/hash; apostilamento gestor/fiscal is not insight; PDF reajuste page is material; Brazilian `4.710,00 m²` ratio; FGV Coluna 35 page text does not invent DNIT or reequilíbrio; process_document FACTs are `fact-indice`/`fact-reajuste`/`fact-data_base`, not `Objeto oficial`; `producer_commit` is emission HEAD; listing FACTs rebind to contract detail JSON; JSON key order is canonicalized; READY xor BLOCKED.

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
