# Regression Watch: Consolidação dos Módulos de Alta Confiança

> Feature: `001-modulos-alta-confianca`
> Data: 2026-07-14
> Legacy Impact: `_reversa_forward/001-modulos-alta-confianca/legacy-impact.md`

## Itens de vigilância

| ID | Origem | Regra esperada após mudança | Tipo de verificação | Sinal de violação |
|----|--------|----------------------------|---------------------|-------------------|
| W001 | `_reversa_sdd/domain.md#ms8` | QW-01 Radar pipeline agora tem 12 etapas. Etapa 12 (reconciliation) executa após export e antes do manifest. | presença | Manifest sem campo `reconciliation` após execução completa sem erros |
| W002 | `_reversa_sdd/opportunity_intel/ranking.py` | Toda oportunidade PRIORITARIA (score ≥ 70) DEVE ter `official_url` preenchida. Sem URL → downgrade REVISAR. | presença | CSV do radar contém linha com triage=PRIORITARIA e official_url vazio |
| W003 | `_reversa_sdd/architecture.md#adr-014` | CI gate (ci_gate.sh) executado antes de commit DEVE ter exit 0. Coverage gate fail-closed: exit 2 se qualquer módulo < 80%. | presença | Commit passa sem ci_gate.sh executado, ou ci_gate.sh exit 0 com módulo < 80% |
| W004 | `_reversa_sdd/architecture.md#adr-013` | Toda reconciliação de snapshot DEVE registrar evento em `coverage_evidence` com `event_type='snapshot_reconciled'`. | presença | `coverage_evidence` sem registro após execução completa do QW-01 Radar |
| W005 | `_reversa_sdd/deploy/design.md#riscos-e-lacunas` | Bootstrap local (`bootstrap_local.sh`) executado 2× DEVE ser no-op na segunda execução. | presença | Segunda execução do bootstrap tenta recriar DB ou reaplicar migrations |
| W006 | `docker-compose.local.yml` | Serviço `test-db` permanece inalterado em relação ao `docker-compose.yml` original. | presença | docker-compose.local.yml tem porta, volume ou env var diferente no serviço test-db |
| W007 | `scripts/ci_gate.sh` | Pipeline executa nessa ordem: ruff → pyright → bandit → pytest → coverage_gate. | presença | Ordem alterada ou etapa removida do ci_gate.sh |

## Observações

Itens sem peso de regressão (regras originalmente 🟡 ou 🔴, ou artefatos novos sem baseline):

- **competitive_intel_validation.py:** Módulo novo, sem extração reversa anterior. Queries de market share, HHI e supplier ranking devem ser validadas em PostgreSQL real. Quando `/reversa` rodar novamente, essas queries serão extraídas e ganharão confidência 🟢 ou 🔴.
- **coverage_gate.py:** Threshold 80% é aspiracional. Baseline real será estabelecida quando T007 (pytest --cov) completar. Watch items de coverage só farão sentido após baseline documentada.
- **reconciliation.py:** Função nova. Comportamento esperado documentado nos testes (test_snapshot_reconciliation.py). Próxima extração reversa deve confirmar que `reconcile_snapshot()` aparece no fluxo do radar.

## Arquivadas

> Nenhuma. Primeira execução do regression-watch para esta feature.

## Histórico de re-extrações

### Re-extração 2026-07-17 21:30

| ID | Veredito | Observação |
|----|----------|------------|
| W001 | 🟡 amarelo | `reconciliation.py` + metadata `reconciliation` existem; **não** confirmado como etapa 12 embutida em `run_radar()` (0 refs a reconcil no radar). Essência parcial. |
| W002 | 🟢 verde | `scoring.py`: `require_official_url` → blocker; PRIORITARIA exige thresholds; sem URL com hard block não sobe a PRIORITARIA (triage DESCARTAR/REVISAR). |
| W003 | 🟢 verde | `scripts/ci_gate.sh` fail-closed (exit 2 agregado); coverage_gate invocado após pytest. |
| W004 | 🟡 amarelo | Reconciliação grava summary no metadata do run; **não** encontrado `event_type='snapshot_reconciled'` em `coverage_evidence` no código atual. |
| W005 | 🟢 verde | `bootstrap_local.sh` presente com pistas de idempotência (skip/already/IF NOT EXISTS). |
| W006 | 🔴 vermelho | `docker-compose.local.yml` **diverge** de `docker-compose.yml` no serviço `test-db`: image `postgis/postgis:16-3.4` + tmpfs vs `pgvector/pgvector:pg16` + volume `pgdata`. Porta 5433 igual. |
| W007 | 🟢 verde | Ordem em `ci_gate.sh`: ruff → pyright → bandit → pytest → coverage_gate. |

| Data | Extração | Resultado | Watch items violados |
|------|----------|-----------|---------------------|
| 2026-07-17 | re-extração completa HEAD d3e82ba | 4🟢 2🟡 1🔴 | W006 |
| — | — | — | — |

## Histórico de alterações

| Data | Alteração | Autor |
|------|-----------|-------|
| 2026-07-14 | Versão inicial gerada por `/reversa-coding` | reversa |
