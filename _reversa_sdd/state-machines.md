# Máquinas de Estado — Extra Consultoria

> Gerado pelo Detective em 2026-07-11T21:30:00Z
> doc_level: completo
> Base: commit e9729e1

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
