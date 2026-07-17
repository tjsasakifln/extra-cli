# PRE-VPS Final Truth Report

**Date:** 2026-07-17  
**Branch:** `fix/pre-vps-final-truth-gate-20260717`  
**Hypothesis destroyed:** `LOCAL_RESILIENCE_READY`

---

## 1. Veredito

```text
NOT_READY
```

**Por quê:** gates offline (lint, type, unit, chaos, fixture isolation, systemd) passam.  
**Bloqueio residual:** canary live com PostgreSQL real + evidência operacional recente por fonte **não** foi executada neste ambiente (`DATABASE_URL` ausente). Sem isso, declarar `PRE_VPS_FINAL_READY` seria mentira.

O selo `LOCAL_RESILIENCE_READY` **não é mais válido**.

---

## 2. Problemas encontrados (audit → correção)

| ID | Sintoma | Causa raiz | Risco | Arquivo | Correção | Teste |
|----|---------|------------|-------|---------|----------|-------|
| F1 | Cycle “healthy” sem Postgres | Path resiliente só JSON | Datalake morto com job verde | `resilient_cycle.py` | `OperationalPipeline` + `PostgresPersistence` | vertical slice / live require_db |
| F2 | Fixture = healthy live | Health sem env | Falso verde ops | `health.py` | `RESILIENCE_ENV` + live-only default | `test_fixture_cycle_never_makes_live_health_green` |
| F3 | SLA PNCP 24h hardcoded | Health ignora registry | Freshness mentiroso | `health.py` | `_sla_hours` via registry (PNCP=4h) | freshness tests |
| F4 | `except TypeError: pass` | Schema ad hoc | Resume silencioso | `resilient_cycle` | `coerce_canonical_checkpoint` fail-closed | `test_checkpoint_invalid_schema_fails_explicitly` |
| F5 | CB só memória | Campos de instância | Novo processo martela API | `adapters.py` | `PersistentCircuitBreaker` | `test_circuit_breaker_persistent_across_instances` |
| F6 | SC páginas virtuais | Bulk re-fatiado sem hash | Mix de snapshots | `adapters.py` | snapshot imutável + `snapshot_hash` | SC snapshot tests |
| F7 | RESILIENCE_* decorativo | PNCP_* no HTTP real | Tuning inútil | `http_policy.py` + `pncp_crawler_adapter` | Policy injetada no request | `test_http_policy_*` |
| F8 | CI sem gate | Makefile local only | Regressão em merge | `ci.yml` | job `resilience-gate` | CI |
| F9 | CIGA success no adapter | Checkpoint cedo | Resume falso | `adapters.py` | só `raw_persisted` no adapter | cycle fixture |
| F10 | Freshness única | Job time = content time | Stale content “current” | `health.py` | triple freshness | `test_freshness_recent_fetch_old_content` |

---

## 3. Arquitetura final (caminho único)

```text
SourceAdapter.fetch
  → raw imutável (FS, SHA-256)
  → normalize puro
  → persist_canonical (PostgreSQL quando live/require_db)
      upsert + entity match + opportunities/acts aplicáveis
  → evidence (mechanics vs operational)
  → checkpoint state machine
  → watermark (só se satisfactory + regras de env)
  → health (live default; --env fixture explícito)
```

Módulos:

- `scripts/crawl/resilience/pipeline.py` — orquestrador canônico  
- `scripts/crawl/resilience/persistence.py` — serviços compartilhados (reusa `monitor` upsert/match/opportunities)  
- `scripts/ops/resilient_cycle.py` — CLI do ciclo  
- `scripts/ops/health.py` — saúde honesta  

JSON canônico permanece **artefato auditável**, não destino operacional live.

---

## 4. Matriz fixture versus live

| Artefato | fixture/test | development/staging/production |
|----------|--------------|--------------------------------|
| Paths | `output/resilience/{env}/...` | `output/resilience/{env}/...` |
| Evidence claim | `TEST_HEALTHY` / mechanics | `operational_satisfactory` exige DB |
| Watermark live | não existe | só com db_committed |
| `python -m scripts.ops.health` | precisa `--env fixture` | default live; sem evidência → exit 2 |
| Circuit breaker | isolado por env | isolado por env |
| Status cycle | `TEST_HEALTHY` | `healthy` só operacional |

Prova automatizada: `test_fixture_cycle_never_makes_live_health_green`.

---

## 5. Matriz de freshness

| Métrica | Base |
|---------|------|
| `collection_freshness` | `last_complete_collection` vs SLA registry |
| `content_freshness` | `source_content_max_timestamp` (unknown se ausente) |
| `operational_freshness` | stale se content stale; unknown sem content ts |
| SLA PNCP | **4h** (registry) |
| SLA CIGA | 48h (registry ciga_ckan) |
| SLA SC Compras | 24h (registry) |

Fetch recente + conteúdo antigo → `collection=current`, `content=stale`, `operational=stale`.

---

## 6. Cenário de resume (PNCP)

```text
run1: page1 raw_persisted → page2 429 → sem watermark
run2: page1 reused (sem HTTP) → page2 success → DB/evidence/watermark (fixture mechanics)
pending page scopes = 0
```

Teste: `test_pncp_orchestrator_resume_after_429` (orquestrador real, sem promote manual).

---

## 7. Resultados PostgreSQL

Neste ambiente: **DSN ausente**.  
Backend `PostgresPersistence` implementado; teste `@pytest.mark.database` skip sem URL.  
CI `resilience-gate` sobe Postgres 16 e aplica migrations 001–054.

Para validar localmente:

```bash
export DATABASE_URL=postgresql://...
export RESILIENCE_REQUIRE_DB=1
make pre-vps-live-canary
```

---

## 8. CI

Job novo: `resilience-gate` em `.github/workflows/ci.yml`

- ruff resilience/ops  
- mypy resilience modules  
- validate_systemd  
- migrations fresh-install  
- pytest local resilience + vertical (offline)  
- fixture cycle + health live blocked  
- upload artifacts  
- **sem** `continue-on-error` / `|| true`

Makefile:

```bash
make pre-vps-final-gate-offline
make pre-vps-live-canary      # nunca no CI auto
make pre-vps-final-gate
```

---

## 9. Canaries live

**Não executadas** (sem rede operacional + DSN nesta sessão).  
Comando pronto: `make pre-vps-live-canary`.

---

## 10. Riscos residuais

| Área | Risco |
|------|-------|
| Código | `monitor.py` ainda tem path legado paralelo (compartilha upsert via persistence, mas não é só fachada) |
| Dados externos | Canary live não rodou; 429/HTML/schema drift reais não revalidados aqui |
| Infra futura | VPS/timers **não** provisionados (correto) |
| Cobertura | Não se declara 95%; offline suite resilience = 48 testes |
| Operação | Habilitar `extra-crawl-*` sem DSN live = fail-closed exit 2 |
| Segurança | Secrets não commitados; headers sensíveis stripped no raw |

---

## 11. Próximo passo

Enquanto `NOT_READY`:

1. Provisionar DSN local/CI com schema 001–054.  
2. `make pre-vps-live-canary` (3 fontes).  
3. Confirmar `python -m scripts.ops.health --env development` exit 0 com freshness operacional.  
4. Revisar PR adversarial independente.  
5. Só então: checklist VPS (sem timers até go-live).

**Não** declarar `VPS_OPERATIONAL` nem `PROJECT_DONE`.
