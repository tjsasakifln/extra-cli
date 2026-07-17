# Máquinas de Estado — Extra Consultoria

> Re-extração Detective 2026-07-17 | HEAD `d3e82ba`  
> Mantém MS1–MS10 (2026-07-13) e adiciona MS11–MS16 do delta B2G

---

## MS1–MS10 (resumo — ver histórico 2026-07-13)

| ID | Entidade | Campo / conceito |
|----|----------|------------------|
| MS1 | Edital intel | status_temporal (PLANEJAVEL…EXPIRADO) |
| MS2 | ingestion_runs | status running/completed/failed |
| MS3 | entity match | match_method cascade |
| MS4 | opportunity status | open/terminal/review (QW-01) |
| MS5 | bid recommendation | GO/REVIEW/NO_GO triage |
| MS6 | soft-delete | is_active + purge |
| MS7 | evidence_state | coverage_evidence states |
| MS8 | QW-01 Radar pipeline | stages crawl→score→export |
| MS9 | Readiness Gate | pass/fail-closed |
| MS10 | Freshness Gate | fresh/stale fail-closed |

Detalhes Mermaid completos das MS1–MS10 permanecem válidos; abaixo o delta crítico.

---

## MS11: Access status do Entity Source Registry 🟢

**Entidade:** `entity_source_registry.access_status`  
**Fonte:** migration 053, `source_registry/models.py`

```mermaid
stateDiagram-v2
    [*] --> unknown
    unknown --> source_not_identified: discovery sem portal
    unknown --> mapped: binding criado
    mapped --> accessible: probe OK
    accessible --> collected: crawl com dados ou empty_confirmed
    collected --> verified: evidência carimbada
    verified --> operational: strict operational criteria
    operational --> failed: regressão de coleta
    accessible --> blocked: auth/CAPTCHA/rate permanente
    blocked --> accessible: unblock
    collected --> failed: transform/upsert fail
    failed --> mapped: replan strategy
    verified --> unknown: invalidação de evidência
```

| De | Para | Gatilho |
|----|------|---------|
| * | mapped | build_registry / discovery grava binding |
| mapped | accessible | probe_url sucesso |
| accessible | collected | adapter success/empty_confirmed |
| collected | verified | evidence ledger seal + stages |
| verified | operational | `is_strict_operational` true |
| * | blocked | auth_blocked / blocker class |
| * | failed | error sem recovery |

---

## MS12: FetchResult do Adapter (ADR-021) 🟢

**Entidade:** resultado de `SourceAdapter.fetch`  
**Campo:** `status`

```mermaid
stateDiagram-v2
    [*] --> fetching
    fetching --> success: 2xx + records
    fetching --> empty_confirmed: 2xx + zero + zero_proof
    fetching --> partial: pages incompletas / subset
    fetching --> rate_limited: HTTP 429
    fetching --> auth_blocked: 401/403/credencial
    fetching --> error: body inesperado / exceção
    rate_limited --> fetching: backoff + checkpoint
    partial --> fetching: resume token
    error --> fetching: retry policy
    success --> [*]
    empty_confirmed --> [*]
    auth_blocked --> [*]
```

**Regra:** apenas `success` e `empty_confirmed` podem alimentar `satisfactory=true` (com demais predicados mig 054).

---

## MS13: CoverageEvidence satisfactory 🟢

**Entidade:** `coverage_evidence`  
**Campo:** `satisfactory` (boolean derivado/guardado)

```mermaid
flowchart TD
    A[state] --> B{success_with_data OR success_zero?}
    B -->|no| Z[satisfactory=false]
    B -->|yes| C{request_scope?}
    C -->|no| Z
    C -->|yes| D{provenance non-empty?}
    D -->|no| Z
    D -->|yes| E{pages OK?}
    E -->|no| Z
    E -->|yes| F{error_code null?}
    F -->|no| Z
    F -->|yes| G[satisfactory=true]
```

---

## MS14: DLQ entry lifecycle 🟢

**Entidade:** `dlq_entries.status`

```mermaid
stateDiagram-v2
    [*] --> pending: push fail
    pending --> replayed: worker replay OK
    pending --> dead: max_retries exceeded
    pending --> archived: purge policy
    replayed --> [*]
    dead --> archived: cleanup
    archived --> [*]
```

---

## MS15: Pipeline watermark 🟢

**Entidade:** `pipeline_watermarks.status`

```mermaid
stateDiagram-v2
    [*] --> in_progress: begin scope
    in_progress --> committed: commit_watermark
    in_progress --> stalled: timeout / crash
    stalled --> in_progress: resume
    committed --> [*]
```

---

## MS16: Workspace section availability 🟢

**Entidade:** seção da fila `today`  
**Estados lógicos:** READY | EMPTY | UNAVAILABLE

```mermaid
stateDiagram-v2
    [*] --> READY: PG OK + rows
    [*] --> EMPTY: PG OK + zero rows
    [*] --> UNAVAILABLE: PG down / query error
    UNAVAILABLE --> READY: reconnect + data
    EMPTY --> READY: new opportunities
```

🟢 CONFIRMADO — ADR-017, `workspace/queue.py` (fallback session JSON).

---

## MS7 (detalhe atualizado): evidence / coverage states 🟢

Integra map_monitor_state_to_evidence + evaluate_freshness:

| Monitor status | Evidence state típico |
|----------------|----------------------|
| success + records | success_with_data |
| success zero + zero_proof | success_zero |
| partial pages | partial |
| 429 | rate_limited / error path |
| exception | error |

Freshness: estado operacional pode degradar para stale se `now - checked_at > freshness_sla_hours`.

---

## Diagrama transversal — jornada entidade 1093

```mermaid
flowchart LR
    A[seed CSV] --> B[ESR mapped]
    B --> C[accessible]
    C --> D[collected via adapter]
    D --> E[verified evidence]
    E --> F[operational M2]
    D --> G[official_acts]
    G --> H[reconcile PNCP]
    H --> I[opportunity_intel]
    I --> J[workspace today]
    F --> K[coverage contract M2]
    I --> L[coverage contract M1]
```
