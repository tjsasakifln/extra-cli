# ADR-033 — Bid readiness evidence model

## Status
Proposed (campaign-delivered; INDEX snippet in integration-handoff only)

## Context
Proposal scaffold left all compliance PENDING. Bid participation needs reproducible evidence linking requirements to immutable document hashes without claiming legal habilitation.

## Decision
- Case directory is source of truth (JSON/JSONL/files only; no DB).
- Originals stored content-addressed by SHA-256; never altered.
- Dual readiness enums: SYSTEM_* and package READY_FOR_HUMAN_REVIEW|BLOCKED_BY_* only.
- Semantic similarity never alone proves technical equivalence.
- Private originals never enter git; fixtures are fictional.
- Simulated package always carries SIMULATION_ONLY.

## Consequences
- Operational support tool, not a legal system.
- Parallel campaigns integrate via file interchange contracts only.
