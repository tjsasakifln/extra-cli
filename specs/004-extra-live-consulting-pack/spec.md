# Spec 004 — Extra Live Consulting Pack (A–E) + integrated recurring cycle

**Campaign (pack):** `EXTRA-LIVE-CONSULTING-PACK-01`  
**Campaign (integration):** `CLIENT-READY-RECURRING-CONSULTING-CYCLE-01`  
**Status:** Integrated operational capability (terminal may be BLOCKED pending human accept)  
**Base:** `origin/main` @ `5d906f6` + PR #130 + PR #129  
**Relationship:** Operational successor to architecture/fixture work in PR #121 (`national_intel`, **superseded**) and proven dual/open-tenders campaigns. Spec **006** remains the component truth for linkage and is referenced (not duplicated) here.

## Problem

Operational assets exist (4.4M contracts dump, dual coverage evidence, Deliverable E live, weekly cycle, workspace CLI, deliverable schemas A–E) but no single isolated cycle produces a reconciled consulting pack A–E over the **full eligible population** with PDF/Excel, monthly recurrence, and honest claims.

## Goals

1. One cycle, one `run_id`/`as_of`/profile/schema/SHA on isolated PostgreSQL restored from authenticated snapshot.
2. Deliverables A–D over full eligible population; E from captured real open-tenders evidence.
3. PDF + Excel + CSV/JSON + executive summary reconciled (divergence = 0).
4. Workspace facade queries coherent with the same DSN.
5. Weekly/monthly recurrence without manual rebuild; state only under campaign paths.
6. Isolation fail-closed; `production_touched=false`; no soak contact.
7. Human acceptance by Tiago or `BLOCKED_HUMAN` — never auto-PASS.

## Non-goals

- VPS/soak deploy, SSH, live production DSN.
- Merge PR #121 as-is or claim national complete market.
- Sample-of-5000 as universe; invent capacity/margin/CATs.
- Mark `LOCAL_READY` / `VPS_OPERATIONAL` / `PROJECT_DONE` solely from this campaign.

## Functional requirements

| ID | Requirement | DOD map | Evidence |
|----|-------------|---------|----------|
| FR-01 | A ranking non-empty on real isolated data with period/sources/universe/quality | §2.5 A, §2.2 | deliverable_a.json |
| FR-02 | B ≥15 defensable competitors or fail-closed INSUFFICIENT | §2.5 B | deliverable_b.json |
| FR-03 | C full 90–180 window query; zero only as success_zero | §2.5 C | deliverable_c.json |
| FR-04 | D ≥1 comparable panel with explicit value magnitude | §2.5 D, §12 valores | deliverable_d.json |
| FR-05 | E incorporate captured open editais; PENDING ≠ GO | §2.5 E | deliverable_e.json |
| FR-06 | Package PDF/Excel same run_id reconcile PASS | §2.5 pacote | pack-manifest.json |
| FR-07 | `scripts.workspace` today/competitors/expiring/prices on isolated DSN | §2.1, §34 | workspace-*.json |
| FR-08 | Monthly two-cycle delta on isolated snapshot | §2.6 | monthly-cycle.json |
| FR-09 | Aggregates use full eligible population; export_limit ≠ universe | §9–11 | population fields |
| FR-10 | Isolation verifier fails on prod/soak DSN | ops | verify-isolation |
| FR-11 | Single canonical entry runs full cycle: migrations→snapshot→opportunities→linkage→dossiers→A–E→weekly→monthly→reconcile→evidence | §2.6, consulting product | `make client-ready-consulting-cycle` |
| FR-12 | Linkage opportunity→organ→contract→supplier with dossiers for pack opportunities (Spec 006) | linkage | linkage-quality.json + dossiers/ |
| FR-13 | Global terminal status exactly PASS \| BLOCKED \| FAIL; human accept required for PASS | ops | result.json / user-acceptance.json |

## Component reference — Spec 006

Canonical entity linkage requirements live in `specs/006-canonical-entity-linkage/`. This pack **must not** fork a second identity engine. Migration **061** + `scripts/linkage/` are the authority.

## Non-functional

| ID | Requirement |
|----|-------------|
| NFR-01 | Interactive query SLO soft ceiling 60s; pack 30min |
| NFR-02 | Migrations idempotent; 060 does not alter dual spine 059 |
| NFR-03 | ADR-020: large artifacts outside git; compact manifests versioned |
| NFR-04 | No `\|\| true` in campaign make gates |

## Entry points

**Canonical integrated (CRC-01):**

- `make client-ready-consulting-cycle`
- `python -m scripts.ops.client_ready_consulting_cycle run --dsn … --out …`
- `make campaign-gate-client-ready-recurring-consulting-cycle`
- `make release-candidate-client-ready-recurring-consulting-cycle`
- `make verify-client-ready-recurring-consulting-cycle-isolated`
- `make dod-audit-client-ready-recurring-consulting-cycle`

**Component / legacy pack entry points (still valid):**

- `python -m scripts.ops.live_consulting_pack run --dsn … --out …`
- `make extra-weekly` (weekly operational surface)
- `make campaign-gate-extra-live-consulting-pack`
- `python -m scripts.ops.strategic_monthly_monitor --live-isolated --dsn …`
- `python -m scripts.linkage run|investigate|guard`

## Claims / non-claims

**Claims allowed:** isolated snapshot consulting pack; CONTRATADO semantics; full eligible population aggregates; E from captured evidence.

**Forbidden:** live VPS proof via this campaign; win rate without denominator; unit price from global valor_total; soak interference; auto human accept.
