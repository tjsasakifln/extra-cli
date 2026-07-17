# C4 — Componentes (Nível 3)

> Architect 2026-07-17 🟢

## 1. Crawl Runtime

```mermaid
flowchart TB
    subgraph Crawl["scripts/crawl"]
      REG[registry.SourceInfo]
      MON[monitor.py]
      ADP[resilience adapters]
      CLS[act_classifier]
      EV[run_evidence]
      CK[checkpoint/watermark/dlq]
    end
    subgraph Schema["scripts/schema"]
      OAS[OfficialActsStore]
    end
    REG --> MON
    MON --> ADP
    ADP --> CK
    ADP --> EV
    MON --> CLS
    CLS --> OAS
```

## 2. Coverage + ESR

```mermaid
flowchart TB
    ESR[source_registry builder/discovery/gap]
    CC[coverage_contract M1-M5]
    ST[states + commercial_status]
    MS[multi_source_coverage]
    ESR --> CC
    ST --> CC
    MS --> CC
    CC --> WS[workspace coverage]
    CC --> GATE[coverage_gate / readiness]
```

## 3. Workspace Facade

```mermaid
flowchart LR
    CLI[workspace CLI] --> Q[queue.build_today]
    CLI --> A[actions decide/scaffold]
    CLI --> C[coverage dual-metric]
    Q --> OI[opportunity_intel]
    Q --> CI[contract_intel]
    Q --> EL[extra_ledger]
    A --> EL
    C --> CC[coverage_contract]
```

## 4. Product intel

```mermaid
flowchart TB
    UNI[lib.universe]
    OI[opportunity_intel radar/score/rank]
    CT[contract_intel target_universe]
    BI[buyer_intel ranking]
    UNI --> OI
    UNI --> CT
    UNI --> BI
    MATCH[matching cascade + acts reconcile] --> OI
    MATCH --> CT
```

## Component inventory (alto nível)

| Container | Componentes |
|-----------|-------------|
| Crawl | registry, monitor, crawlers×11, resilience, act_classifier, provenance |
| Identity | universe, ESR, entity_matcher, official_acts_reconcile |
| Truth | coverage_contract, states, multi_source, commercial_status |
| Product | opportunity_intel, contract_intel, buyer_intel, workspace |
| Delivery | reports, intel_pipeline legado |
| Control | consulting_readiness, freshness_gate, coverage_gate, ci_gate, ops |
