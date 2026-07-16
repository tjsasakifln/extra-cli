# PE-CLOSE-01 — Atualizar DoD/HTML + publicação main

Status: Ready  
Epic: EPIC-PLANO-EXECUTIVO-30D  
Risk: HIGH-RISK  
Priority: P0

## Story

Como PO/DevOps, quero sincronizar DoD e plano HTML com evidências da campanha e publicar em main via AIOX.

## Acceptance Criteria

1. **Given** evidências, **when** DoD atualizado, **then** só itens com evidência marcada; revisões §37 preenchidas.
2. **Given** tasks do plano, **when** HTML atualizado, **then** statuses/evidências refletem a campanha.
3. **Given** stories Done + QA, **when** publicação, **then** PR para main via @devops (sem force).

## File List

- `DOD.md`
- `extra-consultoria-plano-executivo.html`
- `.aiox/state/stories/PE-*.json`
