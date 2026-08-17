# CONFENGE-PRODUCTION-CLOSEOUT-01 — relatório A–Q

Aprovação: `OWNER_CONDITIONAL_PREAPPROVAL_CONFENGE_PRODUCTION_CLOSEOUT_01`  
Token: `PRODUCTION_CLOSEOUT_PARTIAL_CREDENTIAL_BLOCK`  
as_of: 2026-08-17T13:04Z

Evidências não colapsadas: `CODE_PROVEN` / `CI_PROVEN` / `DEPLOYED` / `LIVE_PROVEN` / `CONTROLLED_OWNER_CANARY` / `REAL_EXTERNAL` / `BLOCKED` / `UNKNOWN` / `NO_GO`.

## A. Estado inicial e final por repo

| Repo | Início | Final |
|---|---|---|
| extra-cli | `origin/main` `2d68272d`; lake live; checkout VPS `bbc4b6b7` | Backfill aceito; Market Answer SC `official_live`; #415 NOT_COMPARABLE; #414/#302 NEEDS_DATA |
| web-cfg | live = main `909621a0` | live = merge #111 `1a27783a` (consume SC noindex) |
| Warmbly | deploy `d6eb0ef1` | deploy `6612b7ed` + canário HMAC |
| SmartLic | DNS baseline `smartlic.tech`; pin ready | preflight BLOCKED; DNS inalterado |

## B. SHAs

| Repo | origin/main (início) | Deploy / live |
|---|---|---|
| extra-cli | `2d68272dbe4680c6285b9a35a43f6e4f9076e966` | VPS extra `bbc4b6b7`; lake via DSN |
| web-cfg | `909621a058b6cdd2402a8eb5192e4c645b45bd97` | **LIVE** `1a27783ad1be785b267275b8a305e0e964470725` |
| Warmbly | `6612b7ed3769bd8bf0341ed64fb4b638ccd7bf09` | **LIVE** mesmo SHA, rebuild 2026-08-17T12:45:12Z |
| SmartLic | `fa939a18c226b7c6046aa5dcf024780f0b717140` | sem cutover |

## C. PRs

| PR | Ação |
|---|---|
| web-cfg #102 | CLOSED DEFER (paid search) |
| web-cfg #111 | MERGED `1a27783a` — consume SC noindex + manifesto |
| web-cfg #104 | rebase `b18253fa` + fix CodeQL URL parse; merge após site-ci |
| extra-cli #424 | OPEN; ruff I001 corrigido `fb6f6576` |
| Warmbly #89 | MERGED (evidência deploy/canário) |
| SmartLic #2150 | OPEN; metadata gate BLOCKED (docs) |

## D. Issues (KEEP OPEN)

#60 #62 #83 #84 #88 · extra-cli #302 #400 #414 #415 · Warmbly #47 · SmartLic #2115 #2111  
Canário **não** fecha #60/#88/#47.

## E. Deploy IDs

- web-cfg Netlify production: `6a83065efe7c01000868a9ff` (`LIVE_PROVEN`)
- Warmbly compose rebuild: `2026-08-17T12:45:12Z` (`DEPLOYED` + `LIVE_PROVEN`)

## F. URLs live

- `https://confenge.com.br/`
- `https://confenge.com.br/inteligencia/valor-tipico-contratos-pavimentacao/` (noindex)
- `https://api.confenge.com.br/api/v1/webhooks/confenge/inbound/health`

## G. Artifact / manifest

| Superfície | artifact_hash | manifest_hash | classe |
|---|---|---|---|
| Produção após #111 | `b8491275b19a528a3559f012162078187ea76be190c57e26fe8443167bb7648d` | `9c0ae3ddda4d5b485ad2c20b6b2e6e5896d4679a464d21e42ffb1e978400e30b` | LIVE_PROVEN |
| Duas builds locais normalizadas | `7bfa32df020d0d420753f3f6e67a510dfbc825eb35b617a6e8cc7ff6f77e040a` (ambas) | compare `ok=true` | CODE_PROVEN |

## H. Payload / evidence hashes

| Item | Hash / valor | classe |
|---|---|---|
| Auditor window matrix ×2 | `a8e43af599f4d5511c1dae030990f5e5c99031c7dfa9b193f2323efba0b9c7bd` | CODE_PROVEN + LIVE_PROVEN |
| Checkpoint hc_closure_3y | `17ff50a4…e9312bf8` | LIVE_PROVEN |
| Market Answer folded | `9b69e30cb9e696a6c268526b3646f2d1588519849c5024aa46e6ba89ec06c0b6` | CODE_PROVEN |
| Consume adaptado | `de410553091aa22239c7c6e241f485d4b1a91da6459fce4d7bd412c41a42ac71` | CODE_PROVEN |
| SmartLic manifesto | `9e5667c127fc5494f5849aece2234b13a1c1db10257a17274545019634506ca9` | CODE_PROVEN |
| SmartLic config | `fd391e3667541953e6a830135c863f75452a27c879308fd0012d517740e537a4` | CODE_PROVEN |

## I. Owner canary

- classe: `CONTROLLED_OWNER_CANARY` (não `REAL_EXTERNAL`)
- lead_id: `synthetic-owner-canary-closeout-83431301ee10`
- receipt_id: `synthetic-owner-canary-receipt-83431301ee10`
- row: `97489e04-2c13-4666-bd6e-19a9849f2ec9`
- 201 persist + 200 replay `duplicate=true`
- HMAC inválido 401
- `next_action=SUPPRESSED` · `dispatch_attempted=false`

## J. Flags

`CONFENGE_AUTO_SEND_ENABLED=false` · GREEN autorun false · dispatch/sending paused · human approval true · WhatsApp false.

## K. Health

- Público inbound/health READY ×2 (`LIVE_PROVEN`)
- Localhost `/live` `/ready` `/health/deps` 200, planes ok (`LIVE_PROVEN`)

## L. Market Answer

- URL: `https://confenge.com.br/inteligencia/valor-tipico-contratos-pavimentacao/`
- official_live: true (`LIVE_PROVEN` HTML + payload)
- INDEX: **noindex,nofollow**
- geografia: Santa Catarina (UF)
- período: 2023-07-20 → 2026-08-15
- n: 5038
- discovery: `DISCOVERY_PENDING` / não submetido (noindex)

## M. Análise técnica

- não produzida · `NEEDS_DATA` / `NO_GO` para #414 (`public_read_v1` vazio; comparáveis NOT_COMPARABLE)

## N. X-Ray

- flag `conversion_market_answer_xray`: **off**
- `public_read_v1` snapshot COUNT=0 · `NEEDS_DATA`

## O. SmartLic

- pin/config PASS; destinos CONFENGE 200 PASS; blackbox 301/410/rollback PASS
- cutover **BLOCKED**: `$BRIDGE_PUBLIC_IPV4`, `$SMARTLIC_ACME_EMAIL`, `CF_API_TOKEN`, `CF_ZONE_ID`
- `dns_mutated=false`
- first-production-301: UNOBSERVED
- janela 28d: não iniciada

## P. Blockers

1. `NETLIFY_AUTH_TOKEN` / env sender HMAC / `OPS_TOKEN` — AUSENTE nesta sessão (`BLOCKED`)
2. SmartLic IPv4 + ACME + CF — AUSENTE (`BLOCKED`)
3. #302 tabelas nacionais ausentes (`NO_GO` para claim BR)
4. Incremental unit failed hoje por `source_population_drift` (não Incremental HEALTHY)

## Q. Uma ação humana por blocker

1. No site Netlify production, gravar `CONFENGE_INBOUND_WEBHOOK_URL=https://api.confenge.com.br/api/v1/webhooks/confenge/inbound` e `CONFENGE_INBOUND_WEBHOOK_SECRET` igual ao de `/opt/warmbly-confenge/deploy/confenge-vps/.env` (copiar no host; não colar em chat). Opcional: `OPS_TOKEN` para ler ops inbound_handoff.
2. Exportar `$BRIDGE_PUBLIC_IPV4`, `$SMARTLIC_ACME_EMAIL`, `CF_API_TOKEN`, `CF_ZONE_ID` e rerodar `python3 -m bridge.preflight`. Sem isso, não alterar DNS.
3. Aplicar persist #302 antes de qualquer claim nacional.

`REAL_EXTERNAL`: nenhum lead externo consentido nesta campanha.
