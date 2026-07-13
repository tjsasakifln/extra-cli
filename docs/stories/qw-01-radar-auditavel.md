# QW-01 — Radar Auditável de Editais Abertos

Status: InProgress

## Story

Como consultor da Extra Construtora, quero executar localmente um radar de editais abertos com universo, cobertura, freshness e ranking auditáveis, para priorizar análise humana sem transformar presença de dados em falsa prontidão.

## Acceptance Criteria

- Um comando gera todos os artefatos imutáveis com o mesmo `run_id`.
- A seed da execução define uma única população dentro de 200 km.
- Monitoramento, presença e completude de campos são métricas distintas.
- Paginação incompleta não produz run completa nem `success_zero`.
- Apenas abertura/futuro comprovados entram no radar.
- Confiança do dado e aderência ao cliente são scores independentes.
- PostgreSQL é obrigatório e a execução falha fechada.
- Testes direcionados e gates locais passam ou têm blocker explícito.

## Tasks

- [x] Persistir baseline pré-alteração.
- [x] Consolidar universo canônico e ledger.
- [x] Corrigir paginação/runs/freshness.
- [x] Implementar perfil, scores, radar e artefatos.
- [x] Adicionar testes unitários, integração PostgreSQL e smoke opt-in.
- [ ] Executar migration, run real e quality gates.
- [ ] Atualizar documentação e registrar resultados.

## Dev Agent Record

### Agent Model Used

Codex GPT-5

### Debug Log References

- `docs/reports/qw-01-baseline.md`
- `tests/test_qw01_radar.py`: 95 testes direcionados no checkpoint, incluindo regressões relacionadas.
- `tests/test_qw01_postgres.py`: 4 testes PostgreSQL opt-in.

### Completion Notes List

- Baseline anterior preservado antes das alterações.
- Migration 029 aplicada e reaplicada com `ON_ERROR_STOP=1` para provar idempotência.
- CLI `radar` e conjunto de artefatos validados contra PostgreSQL real com `update_mode=never`.
- Paginação incompleta e `success_zero` sem escopo completo falham fechados no Python e no banco.
- Exportações CSV/XLSX removem controles inválidos e neutralizam fórmulas externas.
- Checkpoint: Ruff, compileall, Bandit, pip-audit, 95 testes direcionados e 4 integrações PostgreSQL passaram.
- Smoke PNCP real permanece opt-in para o run operacional final.

### File List

- `config/client_profiles/extra.yaml`
- `db/migrations/029_qw01_auditable_radar.sql`
- `db/rollback/029_qw01_auditable_radar.sql`
- `docs/decisions/qw-01-canonical-opportunity-pipeline.md`
- `docs/reports/qw-01-baseline.md`
- `docs/stories/qw-01-radar-auditavel.md`
- `output/qw-01/baseline.json`
- `scripts/lib/universe.py`
- `scripts/opportunity_intel/cli.py`
- `scripts/opportunity_intel/crawler_base.py`
- `scripts/opportunity_intel/models.py`
- `scripts/opportunity_intel/pncp_audit.py`
- `scripts/opportunity_intel/pncp_crawler.py`
- `scripts/opportunity_intel/profile.py`
- `scripts/opportunity_intel/radar.py`
- `scripts/opportunity_intel/schema.py`
- `scripts/opportunity_intel/scoring.py`
- `scripts/opportunity_intel/status.py`
- `scripts/opportunity_intel/transformer.py`
- `tests/conftest.py`
- `tests/smoke/test_qw01_pncp_smoke.py`
- `tests/test_opportunity_status.py`
- `tests/test_qw01_postgres.py`
- `tests/test_qw01_radar.py`

### Change Log

| Data | Versão | Mudança | Autor |
|---|---:|---|---|
| 2026-07-13 | 0.1.0 | Story criada a partir do pedido explícito QW-01. | @dev |
| 2026-07-13 | 0.2.0 | Desenvolvimento retomado em modo autônomo — Status: Ready for Dev → InProgress. | @dev |
| 2026-07-13 | 0.3.0 | Núcleo, migration e testes do radar auditável validados; checkpoint pronto para publicação. | @dev |

## QA Results

Pendente.
