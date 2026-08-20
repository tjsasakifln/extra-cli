# `public-read-bofu-evidence/1.0` producer contract

Version: `v1.0.0`
Schema: `public-read-bofu-evidence/1.0`
Machine-readable twin: [`bofu-evidence-v1.json`](bofu-evidence-v1.json)

Producer: Extra CLI (`python3 -m scripts.bofu_evidence`)
Future consumer: `web-cfg` pages/specs (read-only). This artifact does not
register a consumer, authorize publication, or authorize indexation.

## Boundary

This is a **producer-only**, versioned, fail-closed evidence pack for eight
BOFU service families. It is not a page publisher, indexer, SEO brief, CTA
surface, crawler, datalake writer, or legal opinion.

- Inputs are a frozen snapshot (`as_of` from the snapshot or CLI, never
  wall-clock) plus versioned public schemas from `#435` and `#437`.
- Copied fixtures are allowed only in tests marked synthetic/fixture.
  Expired, incompatible, or missing input is refused.
- No backfill, no SQL write, no recensus of the live PNCP catalog.
- `#435` comparables attach only to `orcamento_bdi` as
  `valor_integral_nominal` / `BRL_TOTAL`.
- `#437` PARTIAL/BLOCKED blocks any national claim
  (`national_claim_authorized=false`).
- Packs serialize both `expires` and `expires_at` to the same timestamp.

`publication`, `index` and `national` are **false by default**, including
when the pack state is `READY`.

## Families

| Family id | Service family |
|---|---|
| `reequilibrio` | reequilíbrio |
| `aditivos` | aditivos |
| `medicoes_glosas` | medições/glosas |
| `atrasos_prorrogacoes` | atrasos/prorrogações |
| `defesa_tecnica` | defesa técnica |
| `orcamento_bdi` | orçamento/BDI |
| `pre_licitacao_bid_room` | pré-licitação/Bid Room |
| `gestao_acompanhamento` | gestão/acompanhamento |

Exactly eight nominal packs. One pack per family.

## Pack fields

Every pack declares:

- identity: `pack_id`, `version`, `family`, `question`
- time: `as_of`, `expires`
- provenance: `source`, `method`, `coverage`
- `claims` (claim matrix)
- `calculations`
- `limitations`, `prohibited_claims`
- `state` ∈ {`READY`, `HOLD`, `REJECT`}
- `publication` / `index` / `national` (default `false`)
- `content_hash` (SHA-256 of canonical JSON excluding this field)

## Epistemic classes

Every assertion is exactly one of:

| Class | Meaning |
|---|---|
| `FACT` | Observed in a named evidence ref. Never inferred. |
| `CALCULATION` | Deterministic function of named inputs with evidence refs. |
| `OBSERVATION` | Scoped note that does not assert a legal or economic right. |
| `UNKNOWN` | Not observed in the frozen recorte. |

Absence of a document or event is `UNKNOWN`. It is never a negative `FACT`
("não houve aditivo", "glosa indevida", "não existe direito").

`FACT` and `CALCULATION` require non-empty `evidence_refs`.

## States

| State | When |
|---|---|
| `READY` | Freshness holds, no prohibited claim, no national claim, no unit promotion, `as_of` is not wall-clock. |
| `HOLD` | Freshness expired, `#437` blocks a national attempt, `#435` attached off-family, or unit promotion attempted. |
| `REJECT` | Prohibited field/token, missing evidence ref on FACT/CALCULATION, or invented `as_of`. |

`READY` never authorizes publication, indexation, or a national claim.

## Fail-closed gates

| Gate | Effect |
|---|---|
| `#437` `PARTIAL` / `national_claim_authorized=false` | `national=false`; any national claim → not `READY` |
| `BRL_TOTAL` promoted to cost/km or unit cost | not `READY` |
| `#435` COMPARABLE | attached only when the family question is semantically about observed `BRL_TOTAL` of paralelepípedo peers (`orcamento_bdi`); unit stays `BRL_TOTAL` |
| Missing document/event | `UNKNOWN`, never negative `FACT` |
| Right / irregularity / margin inference | `REJECT` |
| `as_of` from wall-clock or `now > expires` | not `READY` |

## Determinism

JSON is canonical (`sort_keys=true`, compact separators). `content_hash` is
SHA-256 of that encoding with the hash field omitted. Two builds on the same
frozen inputs emit identical hashes.

## Consume

```bash
python3 -m scripts.bofu_evidence --out DIR --as-of 2026-08-19T00:00:00Z
```

Writes `manifest.json`, `packs/<family>.json`, `SHA256SUMS.txt`.
web-cfg may read the pack later. This producer does not write web-cfg,
authorize INDEX, or close `#302` / `#415`.
