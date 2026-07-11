# Fluxograma — Módulo Intel (Pipeline de Inteligência)

> Gerado pelo Archaeologist em 2026-07-11T21:00:00Z
> doc_level: completo
> Base: commit e9729e1

## Pipeline Completo (7 estágios + 5 quality gates)

```mermaid
flowchart TD
    START(["intel_pipeline.py --cnpj --ufs --dias"]) --> VALIDATE[Valida inputs<br/>cli_validation]
    VALIDATE --> S1["Stage 1: intel-collect.py<br/>Coleta exaustiva PNCP"]
    S1 --> G1{"Gate 1: Cobertura"}
    G1 -->|PASS| S2["Stage 2: intel-enrich.py<br/>Enriquecimento cadastral + geográfico"]
    G1 -->|FAIL| ABORT1[Aborta: dados insuficientes]
    S2 --> G2{"Gate 2: Cadastral"}
    G2 -->|PASS| S3["Stage 3: intel-validate.py<br/>Validação programática"]
    G2 -->|FAIL| ABORT2[Aborta: sanctions/cadastral block]
    S3 --> G3{"Gate 3: Ruído"}
    G3 -->|PASS| S4["Stage 4: intel-analyze.py<br/>Análise GPT-4.1-nano"]
    G3 -->|FAIL| FIX3[Auto-fix: reclassifica ambíguos]
    FIX3 --> G3
    S4 --> S5["Stage 5: intel-extract-docs.py<br/>Download + extração de documentos"]
    S5 --> G4{"Gate 4: Conteúdo"}
    G4 -->|PASS| S6["Stage 6: intel-excel.py<br/>Geração Excel 4 planilhas"]
    G4 -->|FAIL| FIX4[Auto-fix: remove duplicatas<br/>backfill do pool]
    FIX4 --> G4
    S6 --> G5{"Gate 5: Recomendação"}
    G5 -->|PASS| S7["Stage 7: intel-report.py<br/>Geração PDF executivo"]
    G5 -->|FAIL| FIX5[Auto-fix: remove NAO PARTICIPAR<br/>aplica regras de override]
    FIX5 --> G5
    S7 --> END(["Relatório final"])
```

## Stage 1: Coleta — Fluxo Detalhado

```mermaid
flowchart TD
    START(["intel-collect.py"]) --> PROFILE[1. Profile company<br/>OpenCNPJ: razão, CNAE, capital]
    PROFILE --> SICAF[2. SICAF + Sanctions<br/>Playwright (captcha)<br/>CEIS/CNEP/CEPIM/CEAF]
    SICAF --> MAP_CNAE[3. Map CNAEs → Keywords<br/>setores_config.yaml<br/>agrega keywords]
    MAP_CNAE --> SEARCH_DL{Datalake disponível?}
    SEARCH_DL -->|sim| DL_SEARCH[search_datalake_for_intel<br/>PostgreSQL RPC<br/>< 2s]
    SEARCH_DL -->|não| LIVE_SEARCH[search_pncp_exhaustive<br/>PNCP API live<br/>chunk 14 dias<br/>parallel UF/mod]
    DL_SEARCH --> DEDUP1[4. Cross-portal dedup<br/>SHA-256 hash]
    LIVE_SEARCH --> DEDUP1
    DEDUP1 --> DEDUP2[5. Semantic dedup<br/>Jaccard > 80%<br/>valor ± 15%<br/>mesmo órgão]
    DEDUP2 --> CNAE_GATE[6. CNAE Keyword Gate<br/>probabilístico<br/>threshold 35%]
    CNAE_GATE --> AMBIGUOUS{Confidence < 40%?}
    AMBIGUOUS -->|sim| LLM[7. LLM Fallback<br/>GPT-4.1-nano<br/>SIM/NAO binário]
    AMBIGUOUS -->|não| INTEL
    LLM --> INTEL[8. Competitive Intelligence<br/>HHI, concorrência,<br/>price benchmarks]
    INTEL --> DOCS[9. Document Listings<br/>top 50 editais]
    DOCS --> DELTA[10. Delta Detection<br/>vs análise anterior<br/>NOVO/ATUALIZADO/VENCENDO]
    DELTA --> END(["Retorna {empresa, editais[], metadata}"])
```

## CNAE Keyword Gate (Probabilístico)

```mermaid
flowchart TD
    START(["apply_cnae_keyword_gate(edital, keywords, patterns, sector)"]) --> DENSITY[Calcula keyword density<br/>matches / total_tokens<br/>no objeto_compra]
    DENSITY --> BASE["Base confidence = min(density × 100, 60%)"]
    BASE --> HEURISTIC{Heuristic match?}
    HEURISTIC -->|strong_compatible| ADD20["+20% bonus"]
    HEURISTIC -->|weak_compatible| ADD10["+10% bonus"]
    HEURISTIC -->|strong_incompatible| SUB30["-30% penalty"]
    HEURISTIC -->|none| CNAE_CHECK
    ADD20 --> CNAE_CHECK{CNAE prefix match?}
    ADD10 --> CNAE_CHECK
    SUB30 --> CNAE_CHECK
    CNAE_CHECK -->|sim| ADD10C["+10% CNAE bonus"]
    CNAE_CHECK -->|não| CLAMP
    ADD10C --> CLAMP["Clamp [0.0, 1.0]"]
    CLAMP --> THRESHOLD{"Confidence ≥ 35%?"}
    THRESHOLD -->|sim| COMPATIVEL["cnae_compatible = True<br/>gate2_decision = COMPATIVEL"]
    THRESHOLD -->|não| INCOMPATIVEL["cnae_compatible = False<br/>gate2_decision = INCOMPATIVEL"]
    COMPATIVEL --> END(["Fim"])
    INCOMPATIVEL --> END
```

## Stage 4: Análise LLM

```mermaid
flowchart TD
    START(["analyze_edital(client, model, edital, empresa)"]) --> OVERRIDE[Verifica regras de override<br/>CNAE 0%? bid_score < 0.20?<br/>CNAE < 20% AND fit < 15%?]
    OVERRIDE -->|override| FORCE["Força NAO PARTICIPAR<br/>retorna fallback_analysis"]
    OVERRIDE -->|não| SCORE[_compute_bid_score<br/>7 dimensões ponderadas]
    SCORE --> CONTEXT[_build_enrichment_context<br/>enriched data → string LLM]
    CONTEXT --> PROMPT[_build_user_prompt<br/>21 campos estruturados]
    PROMPT --> CALL[_call_llm<br/>GPT-4.1-nano<br/>temperature=0<br/>JSON response format]
    CALL --> VALIDATE[_validate_analysis<br/>normaliza enums<br/>forbidden words check<br/>programmatic override]
    VALIDATE --> ADVERSARIAL{Adversarial review?}
    ADVERSARIAL -->|sim| REVIEW[_adversarial_review<br/>modelo DIFERENTE<br/>cross-model audit]
    ADVERSARIAL -->|não| MATRIX
    REVIEW --> MATRIX[_build_compliance_matrix<br/>8 categorias × capacidades]
    MATRIX --> URGENCY[_compute_urgency<br/>dias até sessão<br/>EXPIRADO..CONFORTAVEL]
    URGENCY --> END(["Retorna analise (21 campos)"])
```

## Simulação de Lance (bid_simulator.py)

```mermaid
flowchart TD
    START(["simulate_bid(edital, competitive_intel, benchmark, cnae_principal)"]) --> SECTOR[_get_sector<br/>CNAE 2-digit → margens setoriais]
    SECTOR --> COMPETITORS{Competitive intel disponível?}
    COMPETITORS -->|HHI > 0| EFF_N["N_eff = 1/HHI × 1.5<br/>clamp [2, 20]"]
    COMPETITORS -->|label only| LABEL_N["BAIXA=8, MODERADA=5<br/>ALTA=3, MUITO_ALTA=2"]
    COMPETITORS -->|não| DEFAULT_N["Default N = 5"]
    EFF_N --> DISCOUNT
    LABEL_N --> DISCOUNT
    DEFAULT_N --> DISCOUNT

    DISCOUNT[Calcula desconto ótimo<br/>sugerido = median + 0.3σ<br/>capped: 1.0 - margem_mínima]
    DISCOUNT --> P_WIN[P vitória<br/>z = (discount - median) / std<br/>CDF logístico × (N-1) competidores<br/>clamp [0.02, 0.95]]
    P_WIN --> MARGIN[Margem = BDI setorial - desconto<br/>Valor esperado = P × margem × valor]
    MARGIN --> CONFIANÇA{Histórico ≥ 3 contratos?}
    CONFIANÇA -->|sim, baixa std| ALTA["confianca = ALTA"]
    CONFIANÇA -->|sim, alta std| MEDIA["confianca = MEDIA"]
    CONFIANÇA -->|não| BAIXA["confianca = INSUFICIENTE"]
    ALTA --> END(["Retorna BidSimulation"])
    MEDIA --> END
    BAIXA --> END
```
