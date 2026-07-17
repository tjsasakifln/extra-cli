# ADR-017 — Workspace CLI Facade

| Campo | Valor |
|-------|-------|
| **Status** | Accepted |
| **Data** | 2026-07-17 |
| **Decisores** | PM (Morgan), Architect (Aria), Dev (Dex) |
| **Epic** | E4 Daily workspace / B2G Operational Platform |
| **Relacionados** | ADR-018, ADR-022, QW-01 pipeline |
| **Implementação** | `scripts/workspace/` |
| **Guia** | `docs/operations/workspace-guide.md` |

---

## Contexto

O consultor (Tiago Sasaki) precisa operar a plataforma em minutos, não em dezenas de CLIs (`local_datalake.py`, `opportunity_intel/cli.py`, `monitor.py`, `contract_intel`, scripts de coverage, reconciliação). A fragmentação gera:

- rotina diária não repetível;
- métricas lidas de artefatos errados;
- onboarding impossível;
- impossibilidade de SLA de “briefing matinal”.

Módulos já existentes e maduros:

| Module | Responsibility |
|--------|----------------|
| `scripts/opportunity_intel` | Open opportunities, ranking, radar, briefing |
| `scripts/contract_intel` | Historical contracts, suppliers, expiring |
| `scripts/extra_ledger` | Proprietary decisions and own contracts |
| `scripts/buyer_intel` | Buyer ranking / organ profiles |
| `scripts/local_datalake` | Search, pricing, competitors |
| `scripts/coverage/coverage_contract` | Multi-metric coverage (ADR-018) |
| `scripts/reports/*` | Panorama, coverage weekly |

---

## Decisão

Criar uma **facade CLI `workspace`** (`scripts/workspace/`) como **única interface operacional primária** do consultor.

### Por que CLI (não web app / TUI)

1. **CLI-first surface already exists** — every vertical is argparse + terminal tables.
2. **Single-user** — Tiago is the only operator; no multi-tenant UI needed.
3. **Low friction** — runs on laptop/VPS via SSH; no browser, deploy, or auth layer.
4. **Reuse** — import or thin-delegate to opportunity_intel, contract_intel, extra_ledger, buyer_intel, local_datalake, coverage_contract, reports.
5. **Graceful offline** — file fallbacks from `docs/ops/session-*` and `output/` when PostgreSQL is down; sections report `UNAVAILABLE` with reason (never silent crash).

### Comandos v1 (implementados)

| Comando | Responsabilidade | Delega / fallback |
|---------|------------------|-------------------|
| `today` | Fila diária: novas, prazos, REVIEW, source-health, expiring, perfil pendente, ações | opportunity_intel + session artifacts |
| `opportunities` | Lista/filtra (orgao, municipio, distance, modalidade, valor, prazo, status, score, ranking, fonte, search) | opportunity_intel SQL / session |
| `dossier ID` | Show + explain + fit + missing fields + overrides | opportunity_intel + profile + overrides |
| `coverage` | Dual-metric + gaps sample | coverage_contract + session_summary |
| `competitors` | Top suppliers / dossiê CNPJ | contract_intel / pncp_supplier_contracts |
| `expiring-contracts` | Buckets 30/60/90/180/365 | v_expiring_contracts |
| `prices` | P25/mediana/P75 ou `NOT_READY` honesto | local_datalake pricing logic |
| `edital analyze` | Scaffold checklist 20 pontos; PDF extract se possível; default REVIEW | filesystem workspace |
| `proposal support` | Checklist + matriz + preços + margem + disclaimer | filesystem workspace |
| `contracts` | Monitoramento admin (vigência/prazos/garantias placeholder; sem obra física) | contract_intel + ledger |
| `decide` | approve/reject/override → ledger + overrides | extra_ledger.json + workspace_overrides.json |
| `briefing` / `report daily\|weekly` | Delega briefing / coverage_weekly / panorama | opportunity_intel + reports |

### Princípios

1. **Facade, não reimplementação** — orquestra módulos existentes; não reescreve ranking/crawl.
2. **Degradação graceful** — se PG down, seções `UNAVAILABLE`/`EMPTY` com reason; fallback de sessão.
3. **Dual-metric obrigatória** em coverage (ADR-018): sinal comercial ≠ cobertura operacional.
4. **Perfil cliente** é lei comercial única (ADR-022); campos PENDING não são inventados.
5. **Edital/proposta** nunca inventam GO sem evidência (default REVIEW + slots de página/seção).
6. **DSN** via `LOCAL_DATALAKE_DSN`.

### Entry points

```bash
python -m scripts.workspace today
python -m scripts.workspace today --json
python -m scripts.workspace coverage
python scripts/workspace/cli.py --help
```

---

## Consequências

### Positivas

- Um entrypoint para o trabalho diário do Tiago.
- Rotina documentada em `docs/operations/workspace-guide.md`.
- Decisões humanas dual-write em ledger + overrides.
- Offline útil com artefatos de sessão.

### Negativas / trade-offs

- Facade deve permanecer thin; lógica de negócio fica nos verticais.
- Fallbacks de sessão podem estar defasados vs DB live.
- Campos de perfil PENDING exigem elicitation humana (não automatizar valores).

### Non-goals

- Web UI / multi-user.
- Reescrever ranking, crawl ou scoring.
- Acompanhamento físico de obra.
- Inventar GO sem evidência de edital.

---

## Follow-ups

- Completar elicitation do perfil Extra com Tiago.
- source-health como subcomando dedicado se `today` ficar saturado.
- TUI apenas se fricção diária da CLI for medida alta.
