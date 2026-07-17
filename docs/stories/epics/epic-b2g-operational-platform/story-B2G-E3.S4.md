---
story_id: B2G-E3.S4
title: "Operational data paths + gitignore policy (ADR-020)"
status: Draft
priority: P1
risk_level: STANDARD
effort: S
agent: "@devops"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E3
depends_on: []
blocks: []
adr: [ADR-020]
---

# Story B2G-E3.S4: Operational data not in git

## Contexto

Raw JSONL, checkpoints e dumps poluem git status e PRs.

## Acceptance Criteria

1. **Given** novos outputs de crawl, **When** escritos, **Then** paths cobertos por .gitignore.
2. **Given** PR checklist, **When** review, **Then** ban de raw dumps codificado em docs (e idealmente hook/CI size check).
3. **Given** evidência de gate, **When** stamp docs/ops, **Then** apenas summary + hashes.

## DoD

- [ ] .gitignore atualizado; ADR-020 link no README ops

## Comandos de validação

```bash
git check-ignore -v output/pncp_sc/dummy.jsonl || true
git status --short | head
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |
