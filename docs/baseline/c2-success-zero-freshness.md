# C2 — success_zero e freshness (implementação + fail-closed)

**Story:** PE-C2-01  
**Data:** 2026-07-16  
**Fontes de requisito:** `DOD.md` §4.2 (success_zero), §4.3 (freshness)  
**Escopo:** prova por código/testes existentes; listar gaps fail-closed. Código de produção **não** alterado nesta story.

---

## 1. success_zero — o que o DoD exige

Uma consulta com zero registros só conta como cobertura se (síntese DoD §4.2):

1. ente e fonte aplicável corretos;
2. capability e período consultados registrados;
3. paginação iniciada **e** concluída (sem página ignorada / truncamento);
4. sem timeout/erro parcial escondido, auth ou rate-limit pendente, erro de schema;
5. resposta vazia persistida como `success_zero`;
6. run com `run_id`, timestamps, fonte/capability;
7. run **dentro da janela de freshness**;
8. evidência auditável a posteriori.

Estados que **não** são success_zero: `partial`, `*_failed`, `not_investigated`, etc.

---

## 2. Implementação de success_zero

### 2.1 Ledger e enum

Tabela `coverage_evidence` (`db/migrations/024_coverage_evidence_ledger.sql`):

- estado tipado `evidence_state` inclui `success_zero` e `partial`;
- campos de escopo: `queried_start`, `queried_end`, `run_id`, contagens, `metadata`.

View `v_latest_evidence` / `v_source_health`: última observação por (entity, source, data_type); contagem de `success_zero` por fonte.

### 2.2 Constraints de completude (fail-closed no DB)

**Migration 025b** — `ck_success_zero_completeness`:

```sql
state != 'success_zero'
OR (queried_start IS NOT NULL AND queried_end IS NOT NULL)
OR (metadata ? 'completeness')
```

**Migration 029 (QW-01)** — `ck_ce_success_zero_scope` (mais rígida):

```sql
state != 'success_zero'
OR (
  queried_start IS NOT NULL
  AND queried_end IS NOT NULL
  AND scope_key IS NOT NULL
  AND pages_processed > 0
  AND (
    (pages_expected IS NOT NULL AND pages_processed >= pages_expected)
    OR (
      pages_expected IS NULL
      AND evidence_metadata->>'completion_rule' IN (
        'short_page_without_total',
        'empty_page_after_valid_scope',
        'http_204_complete'
      )
    )
  )
)
```

Trigger `fn_validate_coverage_evidence` (029):

- `success_with_data` exige `count_persisted > 0`;
- `success_zero` exige `count_persisted = 0`.

### 2.3 Máquina de estados em Python

`scripts/coverage/states.py` — `determine_run_result_state`:

```text
se fetched|transformed|persisted > 0 → SUCCESS_WITH_DATA
se zero e fetch_complete:
  se supports_zero_proof e pages_processed >= pages_expected → SUCCESS_ZERO
  se records_expected == 0 → SUCCESS_ZERO
  senão → PARTIAL   # conservador sem prova de paginação
se zero e NOT fetch_complete → PARTIAL
```

Isso prova o AC da story: **paginação incompleta → não vira success_zero**.

### 2.4 Uso no numerador de cobertura

```text
evidence_success_states = {"success_with_data", "success_zero"}
# coverage_truth.py e consulting_readiness.py
```

`partial` **não** entra no numerador (correto).

### 2.5 Testes existentes (prova)

| Teste | O que prova | Path |
|-------|-------------|------|
| `TestSuccessZero.test_success_zero_treated_as_success` | success_zero conta como monitored | `tests/test_consulting_readiness.py` |
| `TestSuccessZero.test_partial_not_treated_as_success` | partial **não** é success | idem |
| `test_success_zero_without_complete_pagination_is_rejected` | INSERT success_zero sem paginação completa **rejeitado** no PG | `tests/test_qw01_postgres.py` |
| `test_partial_evidence_is_allowed_for_incomplete_scope` | partial permitido para escopo incompleto | idem |
| `test_success_zero_without_completeness_rejected` | CHECK de completude | `tests/test_evidence_projection_db.py` |
| `test_page_limit_cannot_be_complete_or_success_zero` | limite de página ≠ complete | `tests/test_qw01_radar.py` |
| smoke FetchStatus SUCCESS_ZERO ≠ CONNECTION_FAILED | não converter exceção em lista vazia | `tests/smoke/test_smoke_contract_intel.py` |

---

## 3. Freshness — o que o DoD exige

| Item | DoD |
|------|-----|
| Editais abertos | idade máxima **24 h** |
| Contratos incremental | intervalo máximo **7 dias** |
| Contratos backfill | mínimo **3 anos** (histórico) |
| Dados vencidos | marcar `stale` |
| Sem prova de atualização | marcar `unknown` |
| Numerador de cobertura | `stale` e `unknown` **não** contam |
| Gate | **fail-closed** |
| Proibido | converter silenciosamente freshness desconhecida em aprovada |

---

## 4. Implementação de freshness

### 4.1 Gate de ingestão — `scripts/freshness_gate.py` (fail-closed)

Fontes críticas:

| source | purpose | SLA default | recent_window default |
|--------|---------|-------------|------------------------|
| `pncp` | editais_abertos | `FRESHNESS_SLA_PNCP_HOURS` **24** | 24 h |
| `contracts` | historical_contracts | `FRESHNESS_SLA_CONTRACTS_HOURS` **24×24 = 576 h (24 dias)** | `24×7 = 168 h (7 dias)` |

Lógica `_status_from_snapshot` (fail-closed):

```text
sem last_success_at            → "never"   (falha)
idade run > SLA                → "stale"   (falha)
run ok mas sem last_ingested_at→ "stale"   (falha)
idade dos dados > SLA          → "stale"   (falha)
senão                          → "fresh"
```

Exit codes:

- `0` — todas críticas `fresh`
- `2` — uma ou mais `stale|never|…` (não fresh)
- `1` — falha técnica (ex.: DB down, coluna ausente)

`unknown` **não** é promovido a `fresh`: ausência de sucesso = `never`/`stale`.  
Qualquer status ≠ `fresh` entra em `failing_sources`.

Outputs: `output/readiness/freshness-gate.json`, `.csv`.

### 4.2 Freshness em reports de cobertura

`coverage_truth.compute_metrics` / `consulting_readiness.compute_freshness`:

```text
usa entity_coverage.last_seen_at
fresh  se delta_dias <= COVERAGE_WINDOW_DAYS (default 90)
stale  se delta_dias > 90
unknown se sem last_seen_at
```

Essa métrica é **descritiva** no report; **não** é o mesmo gate que `freshness_gate.py`.

### 4.3 Estado de coverage / evidence

- `scripts/coverage/states.py` `evaluate_freshness(state, checked_at, freshness_sla_hours=24)` → `fresh|…` e pode marcar overdue.
- Migration 029: `freshness_status IN ('fresh','stale','never','unknown')` em evidence.

### 4.4 Backfill 3 anos

Views de contratos históricos (`v_contract_historical` / contract_intel) usam janela `INTERVAL '3 years'` — alinhado ao DoD de **backfill**, distinto do SLA de **incremental**.

---

## 5. Provas fail-closed (resumo)

| Comportamento | Fail-closed? | Onde |
|---------------|--------------|------|
| success_zero sem escopo/paginação | **Sim (DB)** | CHECK 025b/029 + testes PG |
| partial no numerador de coverage | **Sim (Python)** | só `success_*` contam |
| freshness desconhecida → pass | **Não no freshness_gate** | `never`/`stale` → exit 2 |
| DB down no freshness_gate | **Sim** | exit 1 |
| Line coverage ausente (`.coverage`) | **Sim** (outro domínio) | `coverage_gate.py` exit 3 |
| Evidence ledger vazia em truth | Report `unverified` / None (não inventa %) | `coverage_truth` |

---

## 6. Gaps prioritários (success_zero + freshness)

| ID | Severidade | Gap | Detalhe |
|----|------------|-----|---------|
| C2-SZ1 | **P0** | DoD: success_zero só conta se **fresh**; readiness/truth **contam success_zero/stale** no numerador sem filtrar freshness | numerador ignora `freshness_status` e idade do run |
| C2-SZ2 | **P0** | SLA contratos no `freshness_gate` = **24 dias**, DoD incremental = **7 dias** | `FRESHNESS_SLA_CONTRACTS_HOURS = 24*24`; `recent_window` já é 7d, mas SLA de “fresh” é 24d |
| C2-SZ3 | **P1** | `COVERAGE_WINDOW_DAYS=90` para “fresh” em reports ≠ 24h/7d | confunde operadores ao ler % freshness do report |
| C2-SZ4 | **P1** | Nem todo caminho de crawl grava evidence com prova QW-01 (constraint 029 `NOT VALID` em alguns deploys) | precisa validação operacional de que inserts usam colunas novas |
| C2-SZ5 | **P2** | DoD lista blockers (auth, rate limit, schema) — cobertura depende de o crawler mapear erro → `*_failed`, não `success_zero` | política SOURCE_BLOCKERS em readiness/truth mitiga fontes conhecidas, não todos os erros runtime |
| C2-SZ6 | **P2** | Freshness de “oportunidade prioritária reconfirmada na execução mais recente” não está no `freshness_gate` (só pncp + contracts agregados) | gap de produto |

---

## 7. AC da story PE-C2-01 (mapeamento)

| AC | Status documental |
|----|-------------------|
| 1. Fórmulas editais/contratos separadas e ≥95% gate | **Parcial no código** — documentado em `c2-coverage-formulas.md` (gaps C2-F1, F2) |
| 2. success_zero: paginação incompleta não conta | **Provado** — `states.py` + constraints DB + testes listados |
| 3. freshness stale → gate falha fechado | **Provado** no `freshness_gate.py` (status ≠ fresh → exit 2); **gap** de SLA 24d vs 7d e de numerador de coverage |

---

## 8. Recomendações (sem implementar aqui)

1. Story HIGH-RISK: filtrar numerador de monitoring por evidence `fresh` (e/ou run dentro do SLA por capability).  
2. Story HIGH-RISK: default `FRESHNESS_SLA_CONTRACTS_HOURS` → `24*7` (7 dias) **com** env override e testes de gate.  
3. Documentar em runbook: diferença entre freshness_gate (SLA ingestão) e COVERAGE_WINDOW_DAYS (report 90d).  
4. Garantir migrations 029 aplicadas e constraints validadas em todos os ambientes (`VALIDATE CONSTRAINT` se ainda `NOT VALID`).
