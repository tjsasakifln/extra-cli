# Requirements — Crawl (atualizado 2026-07-17)

## Propósito
Coleta multi-fonte com registry SoT, monitor vivo, resilience fail-closed, atos oficiais.

## RFs delta
- RF-CR-20 Registry único 11 sources com capabilities/SLA 🟢
- RF-CR-21 monitor (não orchestrator) é orquestrador 🟢
- RF-CR-22 Adapters PNCP/CIGA/SC com FetchResult tipado 🟢
- RF-CR-23 429 → rate_limited; pages incompletas → partial 🟢
- RF-CR-24 empty_confirmed único zero-ok 🟢
- RF-CR-25 Official acts classificados e persistidos 🟢
- RF-CR-26 Evidence run_id + content hash 🟢
