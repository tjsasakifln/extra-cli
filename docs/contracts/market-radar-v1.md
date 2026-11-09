# Market Radar public projection v1

Status: **implemented and fixture-tested; deployment and VPS operation are separate evidence**.

## Boundary

`extra-cli` owns acquisition, identity, quality and provenance. This producer
reads `pncp_supplier_contracts` in a `REPEATABLE READ`, read-only transaction and
publishes a sanitized projection. The web runtime receives no PostgreSQL
credential and has group-read access only to the immutable SQLite snapshot.
The daemon runs as the dedicated local role/user `confenge-radar`, whose grant
is column-level `SELECT` on the one source table and which has no database,
role, bypass-RLS, superuser or persistent-write privilege. PostgreSQL may still
provide the cluster's inherited temporary-object capability; the export does
not use it and cannot write persistent source data.

The projection is not a second datalake. It is a bounded, replaceable public-read
contract derived from the canonical store. The timer is independent from the
PNCP crawler and does not use `OnSuccess`; `source_as_of` is the database
transaction cut, while `ingestion_latest_at` is separate telemetry.
That telemetry is `max(COALESCE(last_seen_at, ingested_at))` over the same strict
eligible population. Publication is refused when it is absent or more than 48
hours behind the transaction cut.

## Population and semantics

- fixed window: original `data_publicacao_fonte` in the last 24 calendar months;
- only `is_active`, `supplier_id_type=CNPJ`, `quality_state=VALID`;
- one row per valid official PNCP contract ID, latest observed row wins;
- buyer and supplier identifiers are domain-separated SHA-256 prefixes;
- these stable prefixes are pseudonymous references, not anonymization or a new
  canonical identity system;
- CPF, supplier CNPJ, internal hashes, quality reasons and raw statuses never
  enter the database. The public buyer/agency CNPJ appears only in the official
  PNCP source URL, as required by that URL format;
- the PNCP source link is reconstructed only from a validated official ID;
- `expiry_eligible=1` requires `ACTIVE_PROVEN`, valid start/end dates and a
  contract active by those dates at export time;
- `value_cents` is only the consolidated value reported for the contract. The
  source table does not preserve whether its fallback was global, initial or
  estimated, so values must not be totaled and do not represent payments.

This is observed public history, not a census, an open-tender feed, a prediction
of repurchase or evidence of future procurement. Buyer location does not prove
the execution location.

## Filesystem contract

Directory `/var/lib/confenge-market-radar` is mode `2750`, owned by the producer
user and `confenge-web` group. SGID gives new files the reader group without adding the producer to that group. Snapshots are immutable mode `0440` files named
`snapshot-<sha256>.sqlite`. `current.json` is replaced atomically only after
SQLite `quick_check`, user version, row count, FTS count and identity checks pass.
Failed builds leave the previous pointer untouched. Historical immutable files
are pruned only after a successful pointer replacement, retaining current plus
the two newest predecessors. A conservative free-space preflight also fails
without changing the pointer when the new file cannot safely be built beside
the current snapshot.

Pointer schema `confenge.market-radar.pointer/v1` contains `file`, `sha256`,
`bytes` and metadata schema `confenge.market-radar/v1`. Consumers must verify the
real path, digest, size, schema, state and freshness before opening read-only.
The public API additionally fails closed once `generated_at` is older than 36
hours or `source_as_of` is older than 48 hours.

## SQLite allowlist

`contracts` contains only the fields documented by the web contract: opaque
IDs, object, buyer/supplier display names, buyer UF/city, non-aggregable value,
publication/vigency/source-update dates, canonical PNCP link and the derived
expiry flag. FTS5 indexes only the sanitized object. The single `metadata` row,
key `meta`, contains the exact canonical JSON object repeated at `current.json`
`meta`; this prevents an independently edited pointer from rejuvenating or
relabeling an older SQLite file. No raw source JSON is included.

## Operation

```bash
sudo systemctl enable --now extra-market-radar.timer
sudo systemctl start extra-market-radar.service
journalctl -u extra-market-radar.service --since today
```

Enabling or starting the unit is a deployment action, not implied by this file.
The service uses local PostgreSQL peer authentication as `confenge-radar`, runs
from the isolated versioned release at
`/opt/confenge-market-radar-producer/current`, uses the shared Python runtime
only as an interpreter, runs with low CPU/I/O priority and writes only the
declared state directory.
