# Máquinas de Estado — Extra Consultoria

> Gerado pelo Detective em 2026-07-11T14:00:00Z
> doc_level: completo

---

## 1. Ingestion Run (entity: `ingestion_runs`)

🟢 **CONFIRMADO** — `monitor.py:94-117`

```mermaid
stateDiagram-v2
    [*] --> running: _start_ingestion_run()
    running --> completed: _finish_ingestion_run(status="completed")
    running --> failed: _finish_ingestion_run(status="failed")
    completed --> [*]
    failed --> [*]

    note right of running
        records_fetched = 0
        records_upserted = 0
        entities_covered = 0
    end note

    note right of completed
        finished_at = NOW()
        records_fetched = N
        records_upserted = M
        entities_covered = K
        error_message = NULL
    end note

    note right of failed
        finished_at = NOW()
        error_message = details
    end note
```

**Valores de status:** `running`, `completed`, `failed`

**Gatilhos de transição:**
- `running` → `completed`: Crawl termina sem exceção
- `running` → `failed`: Exceção capturada ou crawler não encontrado

---

## 2. Licitação (entity: `pncp_raw_bids`)

🟢 **CONFIRMADO** — `db/migrations/001:30`

```mermaid
stateDiagram-v2
    [*] --> active: INSERT
    active --> inactive: Soft delete (is_active=FALSE)
    inactive --> active: Re-ingestion (upsert RPC)

    note right of active
        is_active = TRUE
        Visible em queries padrão
    end note

    note right of inactive
        is_active = FALSE
        Excluído de queries com WHERE is_active=TRUE
    end note
```

**Valores de `is_active`:** `TRUE`, `FALSE`

**Gatilhos de transição:**
- INSERT → `active` automaticamente (DEFAULT TRUE)
- `active` → `inactive`: Via soft delete (não implementado em código Python, apenas schema)
- `inactive` → `active`: Re-ingestion via upsert RPC

---

## 3. Entity Coverage (entity: `entity_coverage`)

🟡 **INFERIDO** — `db/migrations/009`

```mermaid
stateDiagram-v2
    [*] --> uncovered: Entidade cadastrada
    uncovered --> covered: Primeiro bid matched
    covered --> uncovered: Sem bids em 90 dias (COVERAGE_WINDOW_DAYS)

    note right of uncovered
        is_covered = FALSE
        last_seen_at = NULL
    end note

    note right of covered
        is_covered = TRUE
        last_seen_at = data do último bid
    end note
```

**Valores de `is_covered`:** `TRUE`, `FALSE`

**Gatilhos de transição:**
- Cadastro → `uncovered`: Entidade inserida em `sc_public_entities`
- `uncovered` → `covered`: Primeiro bid matched com sucesso (trigger após upsert)
- `covered` → `uncovered`: Nenhum bid matched nos últimos 90 dias (query de coverage report)

---

## 4. Órgão Público (entity: `sc_public_entities`)

🟢 **CONFIRMADO** — `db/migrations/007`

```mermaid
stateDiagram-v2
    [*] --> active: INSERT (seed)
    active --> inactive: is_active = FALSE
    inactive --> active: is_active = TRUE

    note right of active
        is_active = TRUE
        Monitorado ativamente
    end note

    note right of inactive
        is_active = FALSE
        Excluído do monitoramento
    end note
```

**Valores de `is_active`:** `TRUE`, `FALSE`

**Gatilhos de transição:**
- INSERT → `active` (seed script popula com `is_active=TRUE`)
- `active` ↔ `inactive`: Atualização manual (não há automação)

---

## 5. Pipeline Intel (entity lógica: execução do pipeline)

🟡 **INFERIDO** — `intel_pipeline.py`

```mermaid
stateDiagram-v2
    [*] --> collect: --cnpj X --ufs SC
    collect --> enrich: GATE 1 PASS
    enrich --> llm_gate: GATE 2 PASS
    llm_gate --> extract_docs: GATE 3 PASS
    extract_docs --> analyze: GATE 4 PASS
    analyze --> validate: (manual ou automático)
    validate --> report: GATE 5 PASS

    collect --> rejected: GATE 1 FAIL (cobertura < 80%)
    enrich --> rejected: GATE 2 FAIL (CNPJ inválido)
    llm_gate --> rejected: GATE 3 FAIL (irrelevante)
    extract_docs --> rejected: GATE 4 FAIL (sem keywords)
    validate --> low_priority: GATE 5 FAIL (score < threshold)

    report --> [*]: PDF + Excel gerados
    rejected --> [*]: Relatório parcial
    low_priority --> [*]: Relatório com flag
```

**Valores de status (por stage):** `PASS`, `FAIL`, `WARN`

**Gatilhos de transição:**
- Stage N → Stage N+1: Gate N retorna PASS
- Stage N → rejected/low_priority: Gate N retorna FAIL ou score abaixo do threshold
