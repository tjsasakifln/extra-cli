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
| W006 | `docker-compose.local.yml` | Local **deve igualar** o oficial: `test-db` com mesma image/volume/env/porta que `docker-compose.yml` (`pgvector/pgvector:pg16` + volume persistente; vector obrigatório). | presença | local com image, volume (ex.: tmpfs-only), porta ou env diferente do oficial no serviço test-db |
| W007 | `scripts/ci_gate.sh` | Pipeline executa nessa ordem: ruff → pyright → bandit → pytest → coverage_gate. | presença | Ordem alterada ou etapa removida do ci_gate.sh |

## Observações

Itens sem peso de regressão (regras originalmente 🟡 ou 🔴, ou artefatos novos sem baseline):

- **competitive_intel_validation.py:** Módulo novo, sem extração reversa anterior. Queries de market share, HHI e supplier ranking devem ser validadas em PostgreSQL real. Quando `/reversa` rodar novamente, essas queries serão extraídas e ganharão confidência 🟢 ou 🔴.
- **coverage_gate.py:** Threshold 80% é aspiracional. Baseline real será estabelecida quando T007 (pytest --cov) completar. Watch items de coverage só farão sentido após baseline documentada.
- **reconciliation.py:** Função nova. Comportamento esperado documentado nos testes (test_snapshot_reconciliation.py). Próxima extração reversa deve confirmar que `reconcile_snapshot()` aparece no fluxo do radar.

## Arquivadas

> Nenhuma. Primeira execução do regression-watch para esta feature.

## Histórico de re-extrações

### Decisão + unificação W006 — 2026-07-27 (owner)

**Decisão do owner (chat):**

1. Local **deve** igualar o compose oficial (`docker-compose.yml`)
2. Extensão **vector** (pgvector) é obrigatória
3. Persistência de dados no PC local **não importa** (prod no Netcup VPS)
4. Ação: **unificar** (não aceitar divergência postgis+tmpfs)

| ID | Veredito | Observação |
|----|----------|------------|
| W006 | 🟢 verde | **Unificado.** `docker-compose.local.yml` `test-db` = `pgvector/pgvector:pg16` + volume nomeado `pgdata` (não tmpfs-only postgis). Paridade com `docker-compose.yml` (image, env, porta 5433, volume, healthcheck). Diffs aceitos no local: `container_name`, `networks`, serviço `app` (stack de dev, fora do contrato test-db). Evidência: `docker-compose.yml` L15–32; `docker-compose.local.yml` L30–46 + volumes L80–83. |

| Data | Extração / evento | Resultado W006 | Notas |
|------|-------------------|----------------|-------|
| 2026-07-27 | Decisão owner + unificação compose (W006) | 🟢 | Unifyado: unificar; vector obrigatório; persistência local irrelevante; fix aplicado nos arquivos oficiais do workspace root |

### Re-extração 2026-07-27 (W006 fix — unify test-db)

| ID | Veredito | Observação |
|----|----------|------------|
| W006 | 🟢 verde | `docker-compose.local.yml` test-db = `pgvector/pgvector:pg16`, ports 5433:5432, volume `pgdata`, env test/test/extra_test — paridade com `docker-compose.yml` (extras locais: container_name, network). `bootstrap_local.sh --reset` usa `down -v`. |

| Data | Extração | Resultado | Watch items violados |
|------|----------|-----------|---------------------|
| 2026-07-27 | fix W006 unify test-db | W006🟢 | — |
| 2026-07-28 | re-extração auditoria HEAD ffbb9608 | 4🟢 2🟡 1🔴 | W006 (pré-fix) |
| 2026-07-17 | re-extração completa HEAD d3e82ba | 4🟢 2🟡 1🔴 | W006 |

### Re-extração 2026-07-28 (auditoria profunda HEAD ffbb9608)

| ID | Veredito | Observação |
|----|----------|------------|
| W001 | 🟡 amarelo | `reconciliation.py` existe; não revalidado como etapa 12 embutida end-to-end no radar nesta sessão. |
| W002 | 🟢 verde | `scoring.py`: `require_official_url` hard block; triage PRIORITARIA com regras de notice/url. |
| W003 | 🟢 verde | `ci_gate.sh` fail-closed exit 2; stages ruff→pyright→bandit→pytest→coverage_gate. |
| W004 | 🟡 amarelo | Sem confirmação de `event_type='snapshot_reconciled'` em coverage_evidence no código amostrado. |
| W005 | 🟢 verde | `bootstrap_local.sh` ainda presente (idempotência não re-executada live). |
| W006 | 🔴 vermelho | **Pré-fix (histórico):** local=`postgis/postgis:16-3.4`+tmpfs; base=`pgvector/pgvector:pg16`+volume pgdata. Corrigido em 2026-07-27. |
| W007 | 🟢 verde | Ordem ruff → pyright → bandit → pytest → coverage_gate confirmada em `scripts/ci_gate.sh`. |

| Data | Extração | Resultado | Watch items violados |
|------|----------|-----------|---------------------|
| 2026-07-28 | re-extração auditoria HEAD ffbb9608 | 4🟢 2🟡 1🔴 | W006 (pré-fix) |
| 2026-07-17 | re-extração completa HEAD d3e82ba | 4🟢 2🟡 1🔴 | W006 |


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
