# Plan — 008 Command Center Consulting Workbench

## Architecture

- Keep FastAPI + React SPA on PR #186 roots.
- Add `workflows/` in-process runners for outcome-first flows (fixture-backed offline; CLI engines remain for live cycles).
- Add `run_manifest.py`, `deliverables/` (reportlab PDF, openpyxl XLSX), `review_rules.py`, `export_bundle.py`.
- JobRunner intercepts `workflow.*` capabilities → structured progress + manifest-primary artifacts + review enqueue.
- Artifact reader: PDF embed + XLSX preview API.
- Decision API enforces rationale/return/hash rules.

## Phases

1. Baseline (done in campaign BASELINE.md)
2. Contracts + renderers + workflow runners
3. API + JobRunner + overview IA
4. Frontend: work start, viewers, review panel, home
5. Tests + campaign pack + PR update

## Risks

- Live DB absent → fixture mode honest limitations
- Scope vs CI time → prioritize real deliverable path tests
