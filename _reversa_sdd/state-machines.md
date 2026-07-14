# Máquinas de Estado — Extra Consultoria

> Gerado pelo Detective em 2026-07-13T17:00:00Z
> doc_level: completo
> Base: commit 249340d
> Adições: MS7 (evidence_state), MS8 (QW-01 Radar), MS9 (Readiness Gate), MS10 (Freshness Gate)

---

## MS1: Status Temporal do Edital

**Entidade:** Edital (pipeline Intel) | **Campo:** `status_temporal`

```mermaid
stateDiagram-v2
    [*] --> PLANEJAVEL: data_sessao > 30 dias
    [*] --> CONFORTAVEL: data_sessao > 15 dias
    [*] --> NORMAL: data_sessao > 7 dias
    [*] --> ATENCAO: data_sessao ≤ 15 dias
    [*] --> URGENTE: data_sessao ≤ 7 dias
    [*] --> CRITICO: data_sessao ≤ 3 dias
    [*] --> IMINENTE: data_sessao = hoje
    [*] --> EXPIRADO: data_sessao < hoje
    [*] --> SEM_DATA: data_sessao = NULL

    PLANEJAVEL --> ATENCAO: tempo passa
    CONFORTAVEL --> ATENCAO: tempo passa
    NORMAL --> ATENCAO: tempo passa
    ATENCAO --> URGENTE: tempo passa
    URGENTE --> CRITICO: tempo passa
    CRITICO --> IMINENTE: tempo passa
    IMINENTE --> EXPIRADO: data passou
    EXPIRADO --> [*]: hard override NAO PARTICIPAR

    note right of EXPIRADO: Força NAO PARTICIPAR<br/>independente de outros scores
    note right of SEM_DATA: Penalizado no bid score<br/>janela_temporal = 0.4
```

🟢 CONFIRMADO — `intel-analyze.py:_compute_urgency()`, `intel_pipeline.py:gate5_recomendacao()`.

**Transições e gatilhos:**

| De | Para | Gatilho | Efeito no Score |
|----|------|---------|-----------------|
| Qualquer | EXPIRADO | `data_sessao < hoje` | Força NAO PARTICIPAR |
| Qualquer | IMINENTE | `data_sessao = hoje` | janela_temporal = 0.6 |
| Qualquer | CRITICO | `dias_restantes ≤ 3` | janela_temporal = 0.3 |
| Qualquer | URGENTE | `dias_restantes ≤ 7` | janela_temporal = 0.3 |
| Qualquer | ATENCAO | `dias_restantes ≤ 15` | janela_temporal = 0.5 |
| Qualquer | NORMAL | `dias_restantes ≤ 30` | janela_temporal = 0.8 |
| Qualquer | CONFORTAVEL | `dias_restantes > 30` | janela_temporal = 1.0 |
| Qualquer | PLANEJAVEL | `dias_restantes > 30` | janela_temporal = 1.0 |
| — | SEM_DATA | `data_sessao IS NULL` | janela_temporal = 0.4 |

---

## MS2: Status de Execução de Crawl (Ingestion Run)

**Entidade:** `ingestion_runs` | **Campo:** `status`

```mermaid
stateDiagram-v2
    [*] --> running: start_ingestion_run()
    running --> completed: crawl + transform + upsert OK
    running --> failed: exceção/timeout/API erro
    failed --> running: retry (nova execução)
    completed --> [*]
    failed --> [*]

    note right of running: records_fetched > 0<br/>mas ainda em progresso
    note right of failed: error_message preenchido<br/>webhook disparado (OnFailure)
```

🟢 CONFIRMADO — `orchestrator.py:_start_ingestion_run()`, `_finish_ingestion_run()`.

---

## MS3: Estado de Match de Entidade

**Entidade:** `pncp_raw_bids` | **Campo:** `match_method`

```mermaid
stateDiagram-v2
    [*] --> unmatched: novo registro inserido
    unmatched --> cnpj: CNPJ exact match (8-digit base → 14 prefix)
    unmatched --> name_normalized: nome + municipio exact match
    unmatched --> fuzzy: rapidfuzz/difflib ≥ 0.85
    cnpj --> re_match: re-run cascade (novas entities)
    name_normalized --> re_match: re-run cascade
    fuzzy --> re_match: re-run cascade

    note right of cnpj: confidence = 'high'<br/>score = 1.0
    note right of name_normalized: confidence = 'high'<br/>score = 1.0
    note right of fuzzy: score ≥ 0.95 → high<br/>score ≥ 0.85 → medium
```

🟢 CONFIRMADO — `entity_matcher.py:match_entities_cascade()`.

**Estados possíveis de `match_confidence`:** `high`, `medium`, `low` (declarado mas nunca atribuído — fuzzy com score ≥ 0.85 e < 0.95 vai para `medium`, < 0.85 não faz match).

---

## MS4: Estado de Ingestão (Checkpoint)

**Entidade:** Crawler execution | **Lógica:** checkpoint TD-5.2

```mermaid
stateDiagram-v2
    [*] --> check_checkpoint: crawl_source(source, 'incremental')
    check_checkpoint --> skip: is_crawl_completed_today() = TRUE
    check_checkpoint --> execute: is_crawl_completed_today() = FALSE
    execute --> save_checkpoint: crawl concluído
    save_checkpoint --> [*]
    skip --> [*]

    note right of skip: skipped_by_checkpoint = True<br/>economiza chamadas desnecessárias
    note right of execute: modo 'full' sempre executa<br/>(ignora checkpoint)
```

🟢 CONFIRMADO — `orchestrator.py:crawl_source()`.

---

## MS5: Circuit Breaker (Rate Limiting)

**Entidade:** API externa | **Classe:** `PNCPCircuitBreaker`

```mermaid
stateDiagram-v2
    [*] --> closed: estado inicial
    closed --> degraded: threshold falhas consecutivas atingido
    degraded --> half_open: cooldown_seconds expirado
    half_open --> closed: try_recover() sucesso
    half_open --> degraded: try_recover() falha

    note right of closed: operação normal<br/>rate limit padrão
    note right of degraded: concorrência reduzida<br/>3 UFs, ordenação por população
    note right of half_open: 1 request de teste<br/>decide se recupera
```

🟢 CONFIRMADO — `circuit_breaker.py:PNCPCircuitBreaker`.

---

## MS6: Pipeline de Análise (Intel)

**Entidade:** Execução do pipeline | **Campo:** gate status

```mermaid
stateDiagram-v2
    [*] --> collect: Stage 1
    collect --> gate1: G1: Cobertura
    gate1 --> enrich: PASS
    gate1 --> [*]: FAIL (aborta)
    enrich --> gate2: G2: Cadastral
    gate2 --> validate: PASS
    gate2 --> [*]: FAIL (aborta)
    validate --> gate3: G3: Ruído
    gate3 --> analyze: PASS
    gate3 --> validate: FAIL (auto-fix tenta)
    analyze --> extract: Stage 4→5
    extract --> gate4: G4: Conteúdo
    gate4 --> excel: PASS
    gate4 --> extract: FAIL (auto-fix: dedup)
    excel --> gate5: G5: Recomendação
    gate5 --> report: PASS
    gate5 --> excel: FAIL (auto-fix: override)
    report --> [*]: PDF + Excel gerados
```

🟢 CONFIRMADO — `intel_pipeline.py:main()`.

---

## MS7: Estado de Evidência de Cobertura (Evidence Ledger)

**Entidade:** `coverage_evidence` | **Campo:** `evidence_state` (enum)

```mermaid
stateDiagram-v2
    [*] --> not_investigated: fonte nunca executada para (entity, source)
    not_investigated --> success_with_data: crawl OK + fetched > 0
    not_investigated --> success_zero: crawl OK + fetched = 0
    not_investigated --> partial: crawl degraded
    not_investigated --> connection_failed: fetch_failed / runtime_error
    not_investigated --> auth_failed: missing_credentials
    not_investigated --> parse_failed: parse error
    not_investigated --> transform_failed: transform error
    not_investigated --> persist_failed: DB write error
    not_investigated --> not_applicable: crawler_not_implemented / SOURCE_BLOCKERS

    success_with_data --> success_with_data: re-crawl (update count_obtained)
    success_zero --> success_with_data: re-crawl com dados
    connection_failed --> success_with_data: retry bem-sucedido
    auth_failed --> success_with_data: credencial corrigida
    partial --> success_with_data: recovery completo

    note right of not_investigated: Estado default<br/>NUNCA assume coberto
    note right of not_applicable: Fonte bloqueada<br/>SOURCE_BLOCKERS override
    note right of success_with_data: Único estado "coberto"<br/>para métricas de readiness
```

🟢 CONFIRMADO — `supabase/migrations/006-v3-unified-schema.sql:391` (enum definition), `scripts/crawl/monitor.py:_map_evidence_state()`.

**Mapeamento determinístico:** `monitor_status + error_code → evidence_state`:

| monitor_status | error_code | fetched | evidence_state |
|---------------|------------|---------|---------------|
| success | — | > 0 | `success_with_data` |
| success | — | = 0 | `success_zero` |
| degraded | — | any | `partial` |
| failed | — | any | `connection_failed` |
| empty | — | any | `success_zero` |
| skipped | — | any | `not_investigated` |
| — | crawler_not_implemented | — | `not_applicable` |
| — | missing_credentials | — | `auth_failed` |
| — | fetch_failed | — | `connection_failed` |
| — | persist_failed | — | `persist_failed` |
| — | runtime_error | — | `connection_failed` |

**Estados considerados "coberto" para readiness:** apenas `success_with_data` e `success_zero`.

---

## MS8: QW-01 Radar Execution

**Entidade:** `RadarExecution` | **Campo:** `exit_code`, `readiness`

```mermaid
stateDiagram-v2
    [*] --> validating: iniciar radar
    validating --> schema_check: validate_qw01_schema()
    schema_check --> universe_load: schema OK
    schema_check --> [*]: schema mismatch (exit 1)

    universe_load --> evidence_query: load_canonical_universe()
    evidence_query --> compute_metrics: latest evidence por entity
    compute_metrics --> threshold_check: monitoring_coverage%

    threshold_check --> ready: coverage ≥ 95%
    threshold_check --> not_ready: coverage < 95%

    ready --> scoring: score_opportunity() todas
    not_ready --> scoring: score_opportunity() todas (non-blocking)

    scoring --> export: CSV + JSON output/
    export --> [*]: exit 0 (ready) ou exit 2 (not ready)

    note right of ready: readiness = "ready"<br/>triage_counts populated
    note right of not_ready: readiness = "monitoring_below_threshold"<br/>gaps CSV gerado
```

🟢 CONFIRMADO — `scripts/opportunity_intel/radar.py:cmd_radar()`, `RadarExecution`, `MONITORING_THRESHOLD=95.0`.

**Exit codes:** 0 = pronto (coverage ≥ 95%), 2 = abaixo do threshold, 1 = falha técnica.

---

## MS9: Consulting Readiness Gate

**Entidade:** Execução do gate | **Lógica:** `consulting_readiness.py`

```mermaid
stateDiagram-v2
    [*] --> load_universe: --radius-km R --threshold T
    load_universe --> resolve_entities: match canonical → sc_public_entities
    resolve_entities --> query_evidence: latest coverage_evidence
    query_evidence --> apply_blockers: SOURCE_BLOCKERS override

    apply_blockers --> compute_coverage: covered / conservative_population
    compute_negative --> export_manifest: coverage_manifest.json + gaps.csv
    compute_ready --> export_manifest: coverage_manifest.json

    compute_coverage --> compute_ready: coverage ≥ threshold
    compute_coverage --> compute_negative: coverage < threshold

    export_manifest --> [*]: exit 0 (ready) ou exit 2 (not ready)

    note right of compute_ready: exit 0<br/>"Consulting Ready"
    note right of compute_negative: exit 2<br/>gap report gerado
```

🟢 CONFIRMADO — `scripts/consulting_readiness.py:main()`. `DEFAULT_THRESHOLD=0.95`.

---

## MS10: Freshness Gate SLA

**Entidade:** `CriticalSourceSpec` | **Campo:** `freshness_sla_hours`

```mermaid
stateDiagram-v2
    [*] --> check_pncp: verificar PNCP (SLA 24h)
    [*] --> check_contracts: verificar Contracts (SLA 24d)

    check_pncp --> pncp_fresh: MAX(last_run_at) ≥ NOW() - 24h
    check_pncp --> pncp_stale: sem run recente

    check_contracts --> contracts_fresh: MAX(last_run_at) ≥ NOW() - 24d
    check_contracts --> contracts_stale: sem run recente

    pncp_fresh --> aggregate: ✓
    pncp_stale --> aggregate: ✗
    contracts_fresh --> aggregate: ✓
    contracts_stale --> aggregate: ✗

    aggregate --> all_fresh: todas fresh
    aggregate --> some_stale: ≥1 stale

    all_fresh --> [*]: exit 0
    some_stale --> [*]: exit 2

    note right of pncp_stale: SLA configurável:<br/>FRESHNESS_SLA_PNCP_HOURS
    note right of contracts_stale: SLA configurável:<br/>FRESHNESS_SLA_CONTRACTS_HOURS
```

🟢 CONFIRMADO — `scripts/freshness_gate.py:CRITICAL_SOURCES`, `main()`. SLAs configuráveis via env vars.
