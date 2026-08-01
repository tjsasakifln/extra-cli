# Spec 008 — EXTRA Command Center Consulting Workbench

**Campaign:** `EXTRA-COMMAND-CENTER-CONSULTING-WORKBENCH-01`  
**Vehicle:** PR #186 · `feat/extra-local-command-center`  
**Class:** `PRODUCT_SURFACE_OVER_CANONICAL_CLI`  
**Operator:** Tiago Sasaki (civil engineer / consultant)

## Problem

PR #186 delivered a secure local UI over allowlisted CLI capabilities, but the mental model remains backend-centric: capability forms, log-first jobs, path parameters, binary-only PDF/XLSX, text-card review without hash binding, and no guided path from consulting need to professional deliverable.

## Goals

1. Outcome-first workbench: Flows A–E complete in browser without terminal, manual paths, or mandatory raw JSON/logs.
2. Deliverable-first: Extra / CONFENGE suppliers / CONFENGE agencies / process_documents produce PDF + XLSX (+ evidence/manifest); not logs-only.
3. Run-manifest is primary artifact discovery; stdout path parse is tested fallback only.
4. Evidence-bound review: ACCEPT↔hashes; REJECT rationale; DEFER rationale+return; invalidation on hash change.
5. Security preserved: allowlist, loopback, CSRF, redaction, no outreach, no DOD auto-accept.
6. Local product layer only (SQLite CC store) — no unjustified main schema change.

## Non-goals

- Second SPA / alternate commercial router
- Auto outreach
- DOD auto-accept / controller bypass
- Coverage or legal inflation
- Semantic AI search ornament

## Actors

| Actor | Role |
|-------|------|
| Tiago | Daily operator: Extra, CONFENGE, documents, review, packages |
| CLI modules | Canonical business engines |
| Command Center | Orchestration UX, manifests, render profiles, review audit |

## Functional requirements (traceable IDs)

| ID | Requirement |
|----|-------------|
| FR-HOME-01 | Home shows continue, start work, reviews, deliverables, health, blockers |
| FR-FLOW-A | Extra opportunities guided flow → PDF+XLSX+manifest+reviews |
| FR-FLOW-B | CONFENGE suppliers guided flow → PDF+XLSX+manifest+coverage honesty |
| FR-FLOW-C | CONFENGE agencies guided flow → PDF+XLSX+review package; no guaranteed hiring |
| FR-FLOW-D | Process documents → coverage PDF+index XLSX+ZIP+manifest |
| FR-FLOW-E | Review queue with counters and evidence-bound decisions |
| FR-MANIFEST-01 | Every main run writes valid run-manifest.json |
| FR-PREV-01 | PDF embeddable in browser |
| FR-PREV-02 | XLSX sheeted preview with pagination |
| FR-REV-01 | REJECT requires rationale ≠ title |
| FR-REV-02 | DEFER requires rationale + return_by |
| FR-REV-03 | ACCEPT binds artifact hashes; mismatch blocks |
| FR-BUNDLE-01 | Export bundle with checksums fail-closed without manifest |
| FR-SEC-01 | No arbitrary commands; no public bind default; no DOD accept |
| FR-PATH-01 | Common flows do not require user-typed output directories |

## Success metrics

Usability tasks 1–5 complete without terminal/paths/JSON; campaign acceptance matrix in FINAL-REPORT.
