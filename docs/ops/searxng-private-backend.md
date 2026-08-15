# CONFENGE private SearXNG — runbook

Status: **LOCAL_READY**. Host of record is Netcup / `ec-prod` (`SERVER_UP` ≠ this stack is live). This document is the operator contract for the search **infrastructure** only. It does not change query planning, person/email parsing, or Warmbly.

## 1. Deployment diagram

```text
                    extra-cli batch discovery
                    --search-backend searxng
                    CONFENGE_SEARXNG_URL
                              |
                              | HTTPS or loopback HTTP
                              | GET /search?q=&format=json
                              v
                 +---------------------------+
                 | reverse proxy (optional)  |
                 | TLS, no public admin UI   |
                 +-------------+-------------+
                               |
                 127.0.0.1:18888 (default bind)
                               |
                 +-------------v-------------+     +------------------+
                 | searxng/searxng@sha256…   |---->| valkey@sha256…   |
                 | JSON + html formats       |     | limiter / cache  |
                 | CPU 1 / RAM 768Mi         |     | CPU 0.25 / 128Mi |
                 +-------------+-------------+     +------------------+
                               |
                conservative public engines only
                duckduckgo, brave, mojeek, qwant,
                wikipedia, wikidata
                               |
                               v
                      public web (no login)
```

Isolation: compose project `confenge-searxng`, dedicated bridge, port published only on `127.0.0.1`. Firewall on Netcup remains default-deny inbound. Admin / preferences are not published.

## 2. Launch (deploy entry point)

From the extra-cli checkout:

```bash
cd deploy/searxng
# first time: copy env and replace the secret (launch.sh does this if .env is missing)
make up          # == bash ./launch.sh
make ps
make logs
```

`launch.sh` is the **real deploy entry point**. It:

1. refuses to start without `PINNED.env` digest pins
2. writes `.env` from `.env.example` and fills `SEARXNG_SECRET` when missing
3. runs `docker compose up -d`
4. waits for health
5. probes `GET /search?q=…&format=json` and requires HTTP 200 + a JSON `results` array (length may be 0)

Second launch of the same command is idempotent.

Rollback:

```bash
# stop
bash deploy/searxng/rollback.sh stop
# restore previous digest pair (only if PINNED.prev.env exists)
cp deploy/searxng/PINNED.env deploy/searxng/PINNED.prev.env   # do this BEFORE changing pins
bash deploy/searxng/rollback.sh
```

## 3. extra-cli integration

```bash
export CONFENGE_SEARXNG_URL=http://127.0.0.1:18888
python3 -m scripts.decision_unit_intelligence run \
  --out /tmp/confenge-prospect-searxng \
  --limit 10 \
  --search-backend searxng
```

`--search-backend ddgs` is a **separate recorded run**, not a hidden fallback.

`--search-failover ddgs` (or `CONFENGE_SEARCH_FAILOVER=ddgs`) is the only in-process failover. It changes the backend id to `searxng_explicit_failover_ddgs` and appends an event. Default is `off`.

Client disk cache remains `.cache/confenge-prospect/`. Failures are not cached as empty hits. Instance limiter/cache lives in Valkey.

## 4. Rate, timeout, circuit, failover matrix

| Condition | extra-cli | Operator action |
|---|---|---|
| Missing `CONFENGE_SEARXNG_URL` | fail closed (`ValueError` / `missing_url`) | set the private URL |
| HTTP 429 | `SearchBackendUnavailableError(http_429)` → `SOURCE_BLOCKED` | back off; do not rotate proxies |
| HTTP 5xx | `http_5xx` → `SOURCE_BLOCKED` | inspect `docker compose logs` |
| Timeout | `timeout`/`network` → `SOURCE_BLOCKED` | check egress / engine bans |
| 5 consecutive failures | `circuit_open` for 60s | wait; fix instance |
| Empty `results: []` with HTTP 200 | valid miss | not an outage |
| Instance down, failover `off` | `SOURCE_BLOCKED` | start a **new** run with `--search-backend ddgs` if you accept DDGS |
| `--search-failover ddgs` | recorded; backend id changes | never treat as a SearXNG success |

Concurrency default: 2 in-flight SearXNG calls. Client interval: `SearchBudget.min_query_interval_seconds` (1s). No proxy rotation, no CAPTCHA/login bypass.

## 5. Security

- Bind `127.0.0.1:18888`. Do not open 18888 on the public NIC. Netcup UFW default-deny stays in place.
- `.env` / `SEARXNG_SECRET` stay out of Git (`deploy/searxng/.gitignore`).
- Images are digest-pinned in `PINNED.env`. Never deploy `:latest`.
- `public_instance: false`. `pass_searxng_org = false`. No public UI/product.
- Optional Caddy snippet (`Caddyfile.example`) terminates TLS on loopback and 404s `/preferences`, `/stats`, `/metrics`.
- `no-new-privileges` is set. Official images are not run with `cap_drop: ALL` because Valkey needs `setresuid` to start.

## 6. AGPL-3.0 obligations

SearXNG is AGPL-3.0. extra-cli is an HTTP client only.

- Do **not** copy `searx/` source into this repo.
- Running the **unmodified official image** plus this configuration is a network service. If you **modify** the image or settings in a way that produces a derived SearXNG program and expose it to others, you must offer the corresponding source (AGPL §13).
- CONFENGE policy: keep the instance private (loopback / internal TLS). If it is ever reachable by anyone outside the operators, publish the exact image digest and any patches you ship.
- License review lives next to the adapter table in [`../commercial-intelligence/contact-resolution.md`](../commercial-intelligence/contact-resolution.md).

## 7. Observability

Client (`SearchHttpMetrics.snapshot()`): request count, HTTP status histogram, p50/p95 latency, 429/5xx, timeouts, circuit opens, per-engine `unresponsive_engines`, result count.

Instance:

```bash
docker compose -f deploy/searxng/docker-compose.yml ps
docker stats confenge-searxng-core confenge-searxng-valkey --no-stream
docker compose -f deploy/searxng/docker-compose.yml logs --tail 100 core
curl -fsS http://127.0.0.1:18888/stats || true
```

`enable_metrics: true` is on; `/metrics` stays passwordless-disabled (`open_metrics: ""`) so it is not a public scrape surface.

## 8. Canary (10 TRACK_A accounts)

```bash
python3 -m scripts.ops.searxng_canary \
  --out artifacts/confenge/searxng-canary.json \
  --limit 10 \
  --searxng-url "${CONFENGE_SEARXNG_URL:-http://127.0.0.1:18888}"
```

The report compares useful yield, pages that led to a person/email, latency, failures, and cost (always R$ 0 purchased data). Each backend is a separate run.

Cold live 2026-08-15 against **Netcup** (`ssh -L 18889:127.0.0.1:18888`, image `searxng/searxng@sha256:892cf809341915a4b7710d3c9045005b4c377d51335a089b6d4da0b28750788d`). `--fresh-cache`: `cache_hits=0`, `cache_reused_accounts=0`, `cache_misses=29` per backend. `useful_yield` counts **search-derived** person/email/domain pages only (historical QSA is not credited to a backend). Direct backend compare (`compare_live_backends`) calls the shipped clients with no disk cache.

| Backend | Search useful yield | Person/email pages | p50 wall | Search hits | Cache hits/misses | Failures | Blocked | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DDGS | 7/10 | 9 | 20.6 s | 63 | 0 / 29 | 0 | 0 | R$ 0 |
| SearXNG private (Netcup) | 7/10 | 8 | 2.9 s | 46 | 0 / 29 | 0 | 0 | R$ 0 |

Direct same-query probe (no cache): DDGS returned 4 hits on all 10 accounts (p50 ~4 s). SearXNG returned 4 hits on 5/10 and 0 on 5/10 (p50 ~1.0 s; Brave/Mojeek/Qwant 429/CAPTCHA stay suspended). Overlap 0–3 URLs. This is engine yield, not a cache replay.

Netcup extra-cli smoke: `--search-backend searxng --searxng-url http://127.0.0.1:18889` (SSH tunnel) on CNPJ `00820854000114` → `ACTIONABLE_ROUTE` / `R3_ROUTED_TO_NAMED_PERSON`, not blocked. Engines that 429/CAPTCHA (Brave, Mojeek, Qwant) stay suspended; no bypass.

## 9. Resource / cost estimate

| Component | Limit | Typical idle | Notes |
|---|---|---|---|
| searxng-core | 1 CPU / 768 MiB | 150–300 MiB | official image |
| valkey | 0.25 CPU / 128 MiB | 10–30 MiB | limiter + cache |
| extra-cli client | existing process | n/a | httpx only |

Purchased-data cost: **R$ 0**. Incremental VPS cost on Netcup is the RAM/CPU above on the existing host (already paid). No third-party search API bill.

## 10. Failover recommendation

- **Primary for batch discovery:** `searxng` against the CONFENGE instance.
- **Fallback:** a new, explicit `--search-backend ddgs` run. Do not enable `--search-failover ddgs` in production batch until a canary shows SearXNG availability is worse than DDGS **and** operators accept mixed provenance.
- `--search-backend off` is the policy skip, not an outage hide.

## 11. Blockers

Named live blocker is written at canary time. `SERVER_UP` on Netcup does not mean this stack is running. Port `8080/tcp` on `ec-prod` is already taken by Warmbly; this kit uses **18888**.
