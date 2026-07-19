# DOD map — EXTRA-DECISION-LOOP-01

Mapeamento das 7 perguntas de Tiago → artefatos.

| # | Pergunta | Artefato |
|---|----------|----------|
| 1 | Editais abertos no universo Extra? | `live-pack-http/snapshot.json` (open/upcoming + high_confidence_open) |
| 2 | PARTICIPAR / REVIEW / NÃO_PARTICIPAR? | `all_decisions.csv`, brief PDF/Excel |
| 3 | Por quê? | dimensões + hard_blockers + rules em cada decisão |
| 4 | O que falta? | `missing_information`, `profile_status.json` |
| 5 | O que mudou? | `snapshot_delta.json`, `snapshot_changes.csv` |
| 6 | Aceite/correção humana? | `human_review_queue.csv` + import labels (nunca auto) |
| 7 | Desempenho medido? | `make extra-calibrate` → PENDING_HUMAN até ≥10 labels |

## Seções DOD vs dod-delta.json

| Seção | after_status | Nota |
|-------|--------------|------|
| §2.1 | PARTIAL | decisão utilizável; sem 95% |
| §2.2 | PARTIAL | PDF/Excel + reconfirm; HTTP parcial |
| §2.5 | PARTIAL | resolvedor + 11 PENDING |
| §2.6 | PARTIAL | análise crítica triagem, não jurídica final |
| §12.2 | PARTIAL | saídas do decision pack |
| §15 | PENDING_HUMAN | human-acceptance.md |
