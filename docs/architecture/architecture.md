# Arquitetura — Extra Consultoria

**Atualizado:** 2026-07-25  
**Status:** visão viva (não substitui ADRs nem `DOD.md`)

## Visão geral

Plataforma **CLI** de inteligência em licitações. Single-user, single-client (Extra Construtora).  
DataLake PostgreSQL; ingestão multi-fonte; relatórios Excel/PDF; ciclo semanal e workspace operacional.

| Dimensão | Valor atual |
|----------|-------------|
| Host de record | **Netcup** RS 2000 · Debian 13 · PG **17** · `ssh ec-prod` · `/opt/extra-consultoria` |
| Runtime local | Python 3.12 + Docker Postgres de teste (ex. porta 5433) |
| Agendamento | systemd timers em `deploy/systemd/` |
| Universo | **1.093** entes (raio 200 km / planilha R-0) |
| Decisões | ADRs em `docs/architecture/adr/` (ver `INDEX.md`) |

Existência do host **não** implica `VPS_OPERATIONAL`. Detalhe de gates: `DOD.md` + `README.md`.

## C4 — Nível 1 (Contexto)

```
┌─────────────────────────────────────────────────────────────────┐
│  Usuário: Tiago Sasaki (Consultor)                              │
│  Acesso: terminal local (WSL/Linux) e SSH → VPS (ec-prod)       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│  Extra Consultoria Platform                                      │
│  scripts/* (CLI) · workspace · weekly_cycle · golden_path        │
│  crawl/monitor · opportunity_intel · coverage · reports          │
└──────────────────────────┬───────────────────────────────────────┘
                           │
     ┌───────────┬─────────┼─────────┬───────────┬────────────┐
     ▼           ▼         ▼         ▼           ▼            ▼
  PNCP API    DOM/CIGA   DOE-SC    PCP       ComprasGov    outros
  (editais +  publicações SC                 federal       (SC Compras,
  contratos)                                               transparência…)
```

## C4 — Nível 2 (Containers)

```
┌─────────────────────────────────────────────────────────────────┐
│              VPS Netcup (Debian 13) — host de record            │
│                                                                 │
│  ┌──────────────────────┐   ┌────────────────────────────────┐  │
│  │ systemd timers       │   │ PostgreSQL 17                  │  │
│  │ deploy/systemd/      │   │ pncp_* · contracts · entities  │  │
│  │ pncp-crawl / contracts│  │ coverage_evidence · runs …     │  │
│  │ ciga / doe / pcp …   │   │ checkpoints / provenance       │  │
│  │ backup / health      │   └────────────────────────────────┘  │
│  └──────────────────────┘                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Python 3.12 @ /opt/extra-consultoria                     │   │
│  │ monitor · contracts crawler · weekly · ops health        │   │
│  └──────────────────────────────────────────────────────────┘   │
│  Backup off-site: Netcup Storagespace (NFS) quando provisionado │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Dev workstation                                                │
│  pytest · ruff · golden_path · docker-compose test DB           │
│  workspace CLI · force-next · dod_controller                    │
└─────────────────────────────────────────────────────────────────┘
```

## Capacidades e medição

Cobertura operacional é **por capability** (ADR-028 / ADR-030), não uma % única ambígua:

- `open_tenders` — editais abertos / monitoramento de oportunidade  
- `historical_contracts` — histórico de contratos (meta ≥95%; dual 100% observado na campanha HC)  
- Sinal comercial e “qualquer linha no banco” **não** contam como cobertura  

Registry de fontes: `scripts/crawl/registry.py` + `config/source_applicability.yaml`.  
Universo: `scripts.lib.universe.load_canonical_universe` (seed planilha).

## Superfície CLI principal

| Entry | Papel |
|-------|--------|
| `python3 -m scripts.workspace …` | Facade diária (ADR-017) |
| `make extra-weekly` | Ciclo semanal canônico |
| `python3 -m scripts.golden_path` | Prova técnica de pipeline |
| `python3 -m scripts.crawl.monitor` | Orquestração multi-fonte |
| `python3 -m scripts.opportunity_intel.cli` | Vertical editais abertos |
| `python3 -m scripts.ops.*` | Migrations, health, campanhas, weekly |
| `tools/dod_controller.py` | Convergência DOD |

## Diagramas e docs relacionadas

- C4 detalhado / legado: `system-architecture.md`, `_reversa_sdd/c4-*.md` (extração Reversa — snapshot)
- Contratos de cobertura: `coverage-contract.md`, ADR-018, ADR-030
- Deploy: `docs/ops/`, `deploy/ansible/`, ADR-007 / ADR-008
- Target B2G: `b2g-operational-target-architecture.md`

## Non-claims

Este documento **não** declara `LOCAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE` nem open_tenders ≥95%.
