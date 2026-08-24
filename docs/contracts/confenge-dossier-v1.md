# Consumer contract — `confenge-dossier/1.0`

Machine twin: [`confenge-dossier-v1.json`](confenge-dossier-v1.json).
Producer: extra-cli `scripts/dossier/`.
Consumers: `web-cfg/contract-analysis`, `warmbly/confenge-cohort`.

## What this is

The dossier is the **company-grain** artifact behind the paid offer
`CFG-DIAG-EXP-v1` (Diagnóstico B2G de Expansão). Every other consumer-bound
family in this repository is contract-grain; this one composes canonical
DataLake reads for a single supplier CNPJ into the deliverable the offer
promises: mapa de compradores, concorrentes, painel de preços, contratos a
vencer, editais triados.

It produces one artifact set with three destinations:

| File | Destination | Contains the prospect? |
| --- | --- | --- |
| `dossier.json` | paid delivery | yes |
| `dossier.md` | paid delivery (human deliverable) | yes |
| `public-read.json` | web-cfg public analysis | no |
| `manifest.json` | Warmbly touchpoint reference | no body, hashes only |

## Commands

```bash
python3 -m scripts.dossier build --cnpj 00820854000114 --as-of 2026-08-22 \
  --reference-scope BOTH --out artifacts/dossier/<slug>
python3 -m scripts.dossier verify --dir artifacts/dossier/<slug>
```

The DSN comes from `--dsn`, `DATABASE_URL` or `LOCAL_DATALAKE_DSN`, in that
order. `--fixture <path>` runs offline and can never claim `official_live`.

Exit codes: `0` ok · `2` no DSN · `3` forbidden claim content · `4` `--strict`
and not `DATA_READY` · `5` `DATA_REJECT`.

## Honesty rules this artifact enforces

- A missing field stays `UNKNOWN` and is excluded from the denominator.
  `UNKNOWN` is never zero. `valued_count` is always reported next to
  `contract_count` so a partial value sum cannot be read as a total.
- `catalog_mode=fixture` can never reach `publication_readiness=DATA_READY`.
  Labelling a fixture run `official_live` returns `DATA_REJECT`.
- Every document is scanned for forbidden claim tokens and metric keys before
  it is written. Official `objeto` text is exempt: the engine must not rewrite
  official text, and an official object containing the word "irregular" is a
  fact, not a claim by CONFENGE.
- The declared-limitations block is exempt from the scan and is pinned by
  `test_limitations_are_frozen_constants` so the exemption cannot become a hole.
- The category ladder is coarse. Where the focal median sits more than `10x`
  outside the panel interquartile band, the position is `OUT_OF_PANEL_RANGE`
  and **no percentile position and no finding** are emitted for that category.
- Every price panel is explicitly scoped. `BOTH` is the fail-closed default and
  carries the regional reference plus a national `DATA_HOLD` while no authorized
  comparable national corpus exists. `NATIONAL` never borrows the regional
  denominator. Consumers must read `scope_id`, geography, denominator, `as_of`,
  source/version, sample count, coverage, missingness, method, hash and limitations.
- The regional focal and panel use the same `public.contract_category_v1` and
  active target-universe population. The `TI` rung uses lexical token matching,
  never a bare `%ti%` substring. `TI` remains `LOW_PRECISION_BUCKET` until the
  broader `sistema` family is statistically defensible.
- Competitors are bound to the focal's **primary** category. Sharing a buyer is
  not enough: a municipality buys stationery and asphalt from the same list.
- `content_hash` strips volatile fields, so two runs over the same data agree
  byte for byte. `verify` recomputes it and fails on drift.
- `producer_sha` resolves an explicit `CONFENGE_REPOSITORY_SHA` first, then a
  validated `.deployed_sha`, and uses Git only in a worktree without a deploy
  marker. An invalid authoritative value yields no SHA instead of silently
  binding the artifact to a stale checkout.

## Findings

A finding is a **fact plus the question that fact opens**. It never asserts a
right, an imbalance, a loss, or that an adjustment is due.

| `finding_id` prefix | Trigger |
| --- | --- |
| `contract_anniversary_reached` | running contract with 12+ months since `data_inicio` |
| `contract_ending_within_window` | contract ends inside the window |
| `buyer_concentration_high` | HHI over `0.25` on known contract value |
| `value_position_in_category` | focal median inside the panel range |
| `open_opportunity_from_known_buyer` | open bid from a buyer already in the portfolio |
| `contract_horizon_beyond_window` | contract ends after the window |

## Privacy boundary

The prospect is never the subject of a public page. Public bodies and their
published contracts are public record and stay. `public-read.json` drops the
identity and buyer-map sections entirely and redacts every field in
`PUBLIC_REDACTED_FIELDS`. `verify` requires every redacted key that remains in
the projection to carry `UNKNOWN` and blocks private identity values outside
fields anchored in published opportunity records. Matching is lexical rather
than arbitrary substring matching, so an authority such as `MUNICIPIO DE
PALHOCA` is not mistaken for a leak merely because the prospect is also based
in Palhoça; the same value in an untrusted profile or generated field still
fails closed.

## What this artifact does not decide

- It does not decide editorial `INDEX`, sitemap membership or SEO. That belongs
  to `contract-analysis-publication-gate/1.0` in the consumer.
- It does not send anything. Warmbly may reference a dossier on a touchpoint;
  the dossier body is delivered by a human.
- It does not replace `comparable-contracts/1.0`. Contract-grain peer analysis
  stays there; this is portfolio-grain.
