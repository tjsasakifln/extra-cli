# Feature Specification: Canonical Entity Linkage

**Feature Branch**: `campaign/canonical-entity-linkage-01`  
**Spec dir**: `specs/006-canonical-entity-linkage`  
**Created**: 2026-07-24  
**Status**: Active  
**Campaign**: `CANONICAL-ENTITY-LINKAGE-01`  
**Authority order**: DOD.md > ADRs > this spec > code > narrative

## Why not evolve 001/002/003

| Spec | Owns | Why not linkage authority |
|------|------|---------------------------|
| 001 dual-capability-coverage-truth | Dual coverage measurement for open_tenders / historical_contracts | Coverage denominators/numerators; explicitly not identity graph |
| 002 historical-contracts-operational-coverage | VPS backfill, soak, operational contracts capability | Presence of contracts; not opportunity↔supplier investigation |
| 003 open-tenders-operational-decision-cycle | Weekly open-tender cycle, snapshot integrity | Open tenders ops; weekly package still showed contracts=0/competitors=0 |

**006** is the authority for golden organ/supplier identity and auditable linkage used by investigation.

## Problem

The lake holds ~4.44M historical contracts and dual coverage is accepted, but a real weekly offline package reported `contracts=0`, `competitors=0`. Presence ≠ usable linkage. Investigators cannot go from an open opportunity to related historical contracts and observed winners with provenance.

## Goals

1. Golden records for organs/units and suppliers without auto-merging conflicting strong IDs.
2. Layered matching: exact → deterministic composite → heuristic reviewable → ambiguous → unresolved.
3. Links opportunity→organ→contract→observed supplier with score, reason codes, rule version, run_id, source IDs.
4. Facade `python3 -m scripts.workspace` exposes `entity`, `competitors`, `expiring-contracts` with claim language.
5. Consultative dossier for ≥1 eligible opportunity.
6. Quality metrics with unresolved retained in denominators; auto-accepted precision ≥99%; zero strong-id false merges.
7. Isolated PostgreSQL only; soak/production forbidden.

## Non-goals

- Touch VPS/soak/production
- New crawler or national-intel identity parallel store
- Infer unobserved participation, win rate, consortia
- Merge distinct CNPJs by name alone
- Reopen ADR-030 coverage semantics
- Claims LOCAL_READY / VPS_OPERATIONAL / PROJECT_DONE

## Threat model (false merges)

| Threat | Control |
|--------|---------|
| Two CNPJ14 merged by similar names | `conflicting_strong_ids` refuses; classification=ambiguous |
| Name-only organ merge | classification=unresolved; no golden key |
| Treat historical winner as tender participant | claim_level=similarity/fact split; explicit non_claims |
| Drop hard cases from denominator | MatchMetrics always counts unresolved/ambiguous |
| Coverage contamination | Linkage tables separate from dual coverage views |

## User stories

### US1 — Investigate from opportunity (P1)

Given an open opportunity with organ CNPJ, when linkage runs, then organ is resolved (exact/deterministic), related historical contracts for same organ appear as similarity links, and observed winners are listed with non-claims.

### US2 — Inverse supplier lookup (P1)

Given a supplier CNPJ, when `workspace entity --cnpj` or inverse investigation runs, then observed relations from the linkage run are returned without inventing tender participation.

### US3 — Fail closed (P1)

Given no eligible opportunities or isolation failure, when pipeline/gate runs, then status fails closed (non-zero / failed), never silent zero-as-success.

## Acceptance

See campaign criteria: double migrate, isolation guard, workspace JSON paths, labeled sample precision, dossier, performance ≤60s, production_touched=false.
