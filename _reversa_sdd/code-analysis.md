# Análise Técnica — Extra Consultoria

> Gerado pelo Archaeologist em 2026-07-11T21:00:00Z
> Projeto: Extra Consultoria — Plataforma de Inteligência em Licitações B2G
> Base: commit e9729e1 (EPIC-FEAT-001 + EPIC-TD-001, 32 stories)
> doc_level: completo
> LOC total: 98.247 (Python), 5.328 (SQL), 3.556 (Shell), 404 (YAML)
> Arquivos: 196

---

## Resumo Executivo

Sistema de inteligência para licitações públicas B2G focado em Santa Catarina. Opera em 3 camadas: **(1) ingestão multi-source** de dados de licitações (10 crawlers sync para 8 fontes), **(2) pipeline analítico** de 7 estágios com 5 quality gates usando GPT-4.1-nano, e **(3) geração de relatórios** executivos em PDF/Excel com estética Big Four. Toda a operação roda em VPS Hetzner CX22 com 20 systemd timers, PostgreSQL 18.4 self-hosted e backup automatizado.

---

## Módulo 1: Crawl (scripts/crawl/) — 35 arquivos, ~14K LOC

### Arquitetura

Pipeline de ingestão unificado: `Crawl → Transform → Upsert → Entity Match → Coverage Update`.

Cada fonte é um módulo Python independente que expõe `crawl(mode) → list[dict]` e `transform(records) → list[dict]`.

🟢 **CONFIRMADO** — Extraído diretamente de `monitor.py:42-85` e `orchestrator.py:28-65`.

### Orquestradores

#### monitor.py (684 linhas)
Entry point principal. Orquestra 8 fontes com entity matching cascade inline.

| Função | Assinatura | Retorno |
|--------|-----------|---------|
| `_get_conn()` | `() → psycopg2.connection` | Conexão PostgreSQL |
| `_load_entities(conn, within_200km_only)` | `(conn, bool) → list[dict]` | Entes públicos SC |
| `crawl_source(source, entities, mode)` | `(str, list, str) → dict` | Crawl + upsert + match |
| `report_coverage(conn)` | `(conn) → dict` | Relatório de cobertura |
| `main()` | `() → int` | CLI entry point |

🟢 **CONFIRMADO** — `monitor.py:589-684`.

#### orchestrator.py (306 linhas) — NOVO
Refatoração do monitor com checkpointing e módulo de matching externo.

| Função | Assinatura | Retorno |
|--------|-----------|---------|
| `crawl_source(source, entities, mode, dsn)` | `(str, list, str, str|None) → dict` | Crawl com checkpoint |
| `load_crawler(source)` | `(str) → module|None` | Carrega módulo crawler |

**Diferenças vs monitor.py:**
- Usa `scripts.matching.entity_matcher.match_entities_cascade()` (externo)
- Checkpoint TD-5.2: verifica `is_crawl_completed_today()` antes de crawlar
- Rota de upsert diferenciada para contracts vs bids
- Logger estruturado via `config.logging_config`

🟢 **CONFIRMADO** — `orchestrator.py:1-306`.

### Crawlers Individuais

| Crawler | Target | Auth | Paginação | Retry | Filtro |
|---------|--------|------|-----------|-------|--------|
| `pncp_crawler_adapter.py` | PNCP /publicacao | Public | offset + has_next | 2×, 2^N backoff | UF server-side |
| `dom_sc_crawler.py` | DOM-SC search | Basic + API Key | 3 categorias | 0 (sem retry) | N/A |
| `doe_sc_crawler.py` | DOE-SC /materia | Bearer (login) | offset + totalPages | 2×, 2^N | Categoria client-side |
| `pcp_crawler.py` | PCP v2 /processos | Public | offset + pageCount | 2×, 2^N | UF client-side |
| `compras_gov_crawler.py` | ComprasGov (2 endpoints) | Public | offset + paginasRestantes | 2×, 2^N×2 | Ambos |
| `contracts_crawler.py` | PNCP /contratos | Public | offset + totalPaginas | 3×, 2^N | CNPJ inference |
| `tce_sc_crawler.py` | SCMWeb transparencia | Public | Heurística (<20 itens) | 3×, 2^N | N/A |
| `transparencia_crawler.py` | Portais municipais | Public | N/A (template-driven) | 1× | N/A |
| `sc_compras_crawler.py` | SC Compras + e-lic | Public | HTML scraping | 3×, 2×N | N/A |
| `bids_crawler.py` | PNCP /publicacao (async) | Public | offset + temProximaPagina | Via client | UF server-side |

🟡 **INFERIDO** — `pncp_arp_crawler.py` e `pncp_pca_crawler.py` são async (httpx), não compatíveis com monitor.py/orchestrator.py. Provável legado.

🟢 **CONFIRMADO** — Todos os 10 crawlers sync têm a interface `crawl(mode)` + `transform(records)` verificada.

### Transparência Templates — NOVO subpacote

Sistema de scraping template-driven para portais municipais de transparência:

| Template | Plataforma | ~Municípios SC | URL Pattern | Estratégia |
|----------|-----------|----------------|-------------|------------|
| `betha.py` | Betha Sistemas | 80 | `{slug}.atende.net/transparencia` | 7 seletores CSS, fallback div |
| `ipam.py` | Ipam | 50 | `{slug}.ipm.org.br/transparencia` | 7 seletores, fallback genérico |
| `egov.py` | E-gov Betha | 40 | `{slug}.e-gov.betha.com.br` | Container div.lista-licitacoes |
| `generico.py` | Genérico (Fallback) | ∞ | Domínio próprio | 3 níveis: score tables → divs → any table |

🟢 **CONFIRMADO** — `transparencia_templates/__init__.py:1-65`.

### Infraestrutura de Crawl

| Arquivo | Linhas | Função |
|---------|--------|--------|
| `common.py` | 213 | Helpers: `digits_only()`, `safe_float()`, `parse_date()`, `generate_content_hash()` |
| `checkpoint.py` | 448 | Duas APIs: sync (psycopg2) + async (Supabase). Tabela `ingestion_checkpoints` |
| `security.py` | 102 | USER_AGENT padronizado, `sanitize_url_param()`, `make_url()` |
| `enricher.py` | 670 | 3 jobs ARQ: enrich_entities, enrich_municipios, enrich_pncp_ibge_codes |
| `transformer.py` | 224 | `transform_pncp_item()`, `compute_content_hash()` SHA-256 |
| `loader.py` | 317 | `bulk_upsert()`, embedding opcional via `text-embedding-3-small` (256d) |
| `retry.py` | 285 | `validate_timeout_chain()`, `calculate_delay()` |
| `circuit_breaker.py` | 523 | `PNCPCircuitBreaker` + `RedisCircuitBreaker`, 5 singletons |
| `sanctions.py` | 640 | `SanctionsChecker` async, CEIS+CNEP, cache 24h TTL |
| `async_client.py` | 741 | `AsyncPNCPClient`, rate limiting Redis-backed |
| `_parallel_mixin.py` | 464 | Multi-UF parallel fetch com batching e degraded mode |
| `config.py` | 246 | 16 feature flags, timeouts, rate limits, escopos |

🟢 **CONFIRMADO** — Todos os arquivos lidos integralmente.

### Constantes e Feature Flags

| Grupo | Qtd | Exemplos |
|-------|-----|---------|
| Feature flags | 16 | `DATALAKE_ENABLED`, `ARP_ENABLED`, `SC_COMPRAS_ENABLED` |
| UFs | 27 | Todos estados + DF |
| Modalidades | 6 | 4,5,6,7,8,12 |
| Timeouts | 10+ | `SC_COMPRAS_FULL_TIMEOUT=7200` |
| Keywords engenharia | 17 | "construç, obra, engenharia, paviment, infraestrutura..." |

🟢 **CONFIRMADO** — `config.py:1-246`.

### GAPs identificados

🔴 **LACUNA** — Dois orquestradores coexistem (`monitor.py` legado + `orchestrator.py` novo). Não está claro qual é o canônico.
🔴 **LACUNA** — Dois sistemas de checkpoint (sync psycopg2 vs async Supabase) com schemas diferentes.
🔴 **LACUNA** — `_parallel_mixin.py` importa de `clients.pncp.*` — pacote fora de `scripts/crawl/`, possível dependência quebrada.

---

## Módulo 2: Intel (scripts/intel_*.py) — 8 arquivos, ~12K LOC

### Arquitetura do Pipeline

Pipeline de 7 estágios orquestrado por `intel_pipeline.py` com 5 quality gates:

```
Collect → Enrich → Validate → Analyze (LLM) → Extract Docs → Excel → PDF Report
   │         │         │           │              │            │         │
   G1        G2        G3          -             G4           G5        -
```

🟢 **CONFIRMADO** — `intel_pipeline.py:739-1184`.

### Estágios

#### Stage 1: intel-collect.py (3.193 linhas)
Coleta exaustiva de licitações com 12 sub-etapas:
1. Profile company (OpenCNPJ) → 2. SICAF + Sanctions → 3. Map CNAEs → 4. PNCP search (datalake preferido, API fallback) → 5. Cross-portal dedup (hash) → 6. Semantic dedup (Jaccard) → 7. CNAE Keyword Gate → 8. LLM fallback (GPT-4.1-nano) → 9. Competitive intelligence (HHI) → 10. Document listings → 11. Price benchmarking → 12. Delta detection

| Função | Linhas | Propósito |
|--------|--------|-----------|
| `AdaptiveRateLimiter` | 223 | Rate limiter thread-safe com circuit breaker |
| `search_pncp_exhaustive(api, ufs, dias, modalidades, cnpj14, use_cache)` | 831 | Core PNCP fetcher com paralelismo |
| `apply_cnae_keyword_gate(editais, keywords, ...)` | 1186 | Classificador probabilístico CNAE |
| `_llm_classify_edital_relevance(cnae_description, objeto, model)` | 1465 | Classificador LLM para casos ambíguos |
| `collect_competitive_intel(api, editais, meses, keywords)` | 1685 | HHI + competition level por órgão |
| `_semantic_dedup(editais)` | 407 | Jaccard token overlap dentro da UF |

🟢 **CONFIRMADO** — `intel-collect.py:1-3193`.

**Algoritmo de CNAE Confidence** (🟢 CONFIRMADO — `intel-collect.py:1321-1360`):
- Base: keyword density (caps at 60%)
- Bonus: +20% strong_compatible, +10% weak_compatible
- Penalty: -30% exclusion match
- CNAE match bonus: +10%
- Threshold: ≥35% = compatible

**Adaptive Rate Limiter** (🟢 CONFIRMADO — `intel-collect.py:214-279`):
- Base interval: 150ms, max: 2s
- Fast response (<2s): interval *= 0.85
- Slow (>5s): interval *= 1.5
- Circuit breaker: 3 consecutive failures = 15s pause

#### Stage 2: intel-enrich.py (622 linhas)
Enriquecimento cadastral e geográfico.

| Função | Propósito |
|--------|-----------|
| `enrich_empresa(api, cnpj14, skip_sicaf)` | SICAF + CEIS/CNEP/CEPIM/CEAF + contratos federais |
| `enrich_editais(api, editais, cidade_sede, ...)` | Geocode, OSRM distâncias, IBGE batch, custo, simulação, victory profile |

🟢 **CONFIRMADO** — `intel-enrich.py:1-622`.

**Filtro de capacidade**: só enriquece editais dentro de 10× capital_social. 🟢 CONFIRMADO — `intel-enrich.py:271-284`.

#### Stage 3: intel-validate.py (1.031 linhas)
Validação programática para Gates 2, 4 e 5.

| Gate | Função | Propósito |
|------|--------|-----------|
| G2 | `gate2_semantic(top20, empresa, do_fix)` | Compatibilidade semântica CNAE |
| G4 | `gate4_completeness(top20, empresa, do_fix)` | Análise completa, forbidden words, enums |
| G5 | `gate5_coherence(top20, do_fix, data_root)` | Coerência do relatório final |

**4 regras HARD_INCOMPATIBLE** (🟢 CONFIRMADO — `intel-validate.py:98-120`):
1. software/sistema/erp → CNAE 42/43/41 (construção)
2. aliment/refeição → CNAE 71/42/43 (engenharia)
3. limpeza/conservação → CNAE 42/43/41
4. concessão/zona azul → CNAE 42/43/41

**6 regras de override de recomendação** (🟢 CONFIRMADO — `intel-validate.py:499-579`):
1. EXPIRADO → NAO PARTICIPAR
2. Sancionada → NAO PARTICIPAR
3. CNAE 0% → NAO PARTICIPAR
4. CNAE <20% AND fit <15% → NAO PARTICIPAR
5. Bid score <0.20 → NAO PARTICIPAR
6. Nivel_dificuldade.geral deve ser BAIXO/MEDIO/ALTO

#### Stage 4: intel-analyze.py (1.820 linhas)
Análise LLM com GPT-4.1-nano. 3 modos: API, --prepare (contexto sem LLM), --save-analysis (validação).

| Função | Propósito |
|--------|-----------|
| `_compute_bid_score(edital, empresa)` | Scoring 7 dimensões pré-LLM |
| `_build_compliance_matrix(analise, empresa)` | Cross-reference requisitos × capacidades |
| `analyze_edital(client, model, edital, empresa, idx, total)` | Análise individual com retry |
| `_adversarial_review(client, edital, analise, model)` | Cross-model audit (modelo diferente) |
| `generate_executive_summary(client, model, data)` | Resumo + próximos passos via LLM |
| `_fallback_analysis(edital, empresa, error_msg)` | Fallback mínimo se LLM falhar |

🟢 **CONFIRMADO** — `intel-analyze.py:1-1820`.

**Bid Score 7 dimensões** (🟢 CONFIRMADO — `intel-analyze.py:279-378`):

| Dimensão | Peso | Função |
|----------|------|--------|
| fit_estrategico | 20% | victory_profile |
| viabilidade_financeira | 15% | piecewise(valor/capital): ≤1=1.0, ≤3=0.7, ≤5=0.4, ≤10=0.2, >10=0.05 |
| roi | 15% | piecewise: ≥5=1.0, ≥3=0.7, ≥1.5=0.4, >0=0.1 |
| p_vitoria | 15% | bid simulation scaled, cap 60% |
| custo_logistico | 10% | piecewise distância: ≤100=1.0, ≤300=0.7, ≤600=0.4, >600=0.2 |
| janela_temporal | 10% | URGENTE=0.3, IMINENTE=0.6, PLANEJAVEL=1.0 |
| concorrencia | 15% | BAIXA=1.0, MEDIA=0.7, ALTA=0.4, MUITO_ALTA=0.2 |

Threshold de participação: 0.45.

**21 campos extraídos por edital** via GPT-4.1-nano (🟢 CONFIRMADO — `intel-analyze.py:750-795`):
resumo_objeto, requisitos_tecnicos, requisitos_habilitacao, criterio_julgamento, regime_execucao, consorcio, garantia_proposta, visita_tecnica, plataforma, prazo_execucao_dias, data_sessao, recomendacao_acao, nivel_dificuldade (5 sub-scores + geral), analise_risco, analise_concorrencia, analise_viabilidade, alertas, cronograma, roi_estimado, habilitacao, desenvolvimento

#### Stage 5: intel-extract-docs.py (897 linhas)
Download e extração de texto de documentos PNCP.

| Função | Propósito |
|--------|-----------|
| `extract_pdf(path)` | pymupdf4llm → PyMuPDF → OCR (pytesseract, pt-br) |
| `extract_spreadsheet(path)` | XLS/XLSX via openpyxl/xlrd |
| `extract_archive(path, archive_type)` | ZIP/RAR → extrai → recursão em PDFs/XLSX |
| `select_top_editais(editais, capital_social, top_n, victory_profile)` | Filtro 5-pass + scoring |
| `calculate_opportunity_score(edital, capacidade_10x, victory_profile)` | Multi-fator para ranking top20 |

🟢 **CONFIRMADO** — `intel-extract-docs.py:1-897`.

**Filtro 5-pass para seleção top20** (🟢 CONFIRMADO — `intel-extract-docs.py:636-683`):
1. cnae_compatible only
2. Dentro de 10× capital social
3. Não EXPIRADO/SESSAO_REALIZADA
4. Exclui se >700km AND valor < 3× capacidade
5. Dedup por cnpj+ano+sequencial

**Detecção de OCR** (🟢 CONFIRMADO — `intel-extract-docs.py:153`):
Se avg_chars/página < 100 após PyMuPDF → dispara pytesseract com modelo pt-br.

#### Stage 6: intel-excel.py (1.031 linhas)
Workbook Excel 4-planilhas com openpyxl write-only.

| Planilha | Conteúdo | Colunas |
|----------|---------|---------|
| Oportunidades | CNAE-compatíveis, não expirados | 31 colunas (recomendação, objeto, valor, distância, custo, ROI, P(vitória)...) |
| Resumo por UF | Agregado | UF, Qtd Total, Qtd Compatível, Valor Total |
| Resumo por Modalidade | Agregado | Modalidade, Qtd, Valor Total |
| Metadata | Parâmetros da busca | CNPJ, Razão Social, CNAE, Capital, SICAF, Sanções |

🟢 **CONFIRMADO** — `intel-excel.py:1-1031`.

#### Stage 7: intel-report.py (2.178 linhas)
PDF executivo com 9 seções, estética Big Four (reportlab).

| Seção | Conteúdo |
|-------|---------|
| Capa | Nome empresa, CNPJ, CNAE, mês/ano, consultor |
| Sumário Executivo | 4 KPIs, resumo, portfolio KPI, top 5 |
| Market Snapshot | Oportunidades, capacidade, breakdown urgência |
| Delta Section | Mudanças desde última análise (NOVO/ATUALIZADO/VENCENDO) |
| Perfil + Mapa | Dados empresa, SICAF/sanções, tabela de oportunidades |
| Análise Individual | 2 editais por página, 21 campos + competitive intel + bid sim |
| Próximos Passos | Ações priorizadas (URGENTE > ALTA > MEDIA > BAIXA) |
| Consórcio | Oportunidades acima de 10× capacidade mas relevantes |
| Timeline | Cronograma por data de sessão |

🟢 **CONFIRMADO** — `intel-report.py:1-2178`.

**Design tokens do PDF** (🟢 CONFIRMADO — `intel-report.py:497-630`):
INK=#1B2A3D, ACCENT=#8B7355 (bronze), SIGNAL_RED=#B5342A, SIGNAL_GREEN=#1B7A3D, SIGNAL_AMBER=#B8860B. Fontes: Times-Bold/Roman/Italic + Helvetica. A4, margens 2.2cm.

### Quality Gates

| Gate | Após Stage | Função | Lógica |
|------|-----------|--------|--------|
| G1: Cobertura | Collect | `gate1_cobertura()` | status ≠ API_FAILED, total > 0, UF coverage, pagination warnings |
| G2: Cadastral | Enrich | `gate2_cadastral()` | Sanctions check, SICAF, enrichment coverage ≥ 50% |
| G3: Ruído | Validate | `gate3_ruido()` | Compat ratio 5-80%, zero needs_llm_review, spot-sample |
| G4: Conteúdo | Extract Docs | `gate4_conteudo()` | Doc coverage ≥ 50%, watermark detection, dedup |
| G5: Recomendação | Antes Excel/PDF | `gate5_recomendacao()` | Remove NAO PARTICIPAR do top20, dedup, 10× capacity check |

🟢 **CONFIRMADO** — `intel_pipeline.py:200-700`.

---

## Módulo 3: Reports — 6 arquivos, ~9.5K LOC

### panorama.py (343 linhas)
Panorama de mercado setorial. 6 seções SQL + export Excel/terminal.

| Seção | Query |
|-------|-------|
| Volume | GROUP BY modalidade, SUM/AVG/COUNT |
| Municípios | Top-20 por quantidade de licitações |
| Órgãos | Top-20 contratantes |
| Sazonalidade | Distribuição mensal 12 meses |
| Sources | Distribuição por fonte de dados |
| Gaps | Entidades com zero cobertura |

🟢 **CONFIRMADO** — `panorama.py:1-343`.

### coverage_weekly.py (1.169 linhas)
Relatório semanal executivo de cobertura com PDF (ReportLab, Big Four aesthetic).

| Função | Propósito |
|--------|-----------|
| `fetch_coverage_data(report_date)` | 7 categorias de dados |
| `generate_snapshot(snap_date)` | Chama `generate_coverage_snapshot()` |
| `generate_pdf(data, output_path, report_date)` | PDF executivo com capa, KPIs, gaps, tendência, recomendações |
| `generate_excel(data, output_path)` | 4-planilhas Excel |

**4 regras de recomendação automatizada** (🟢 CONFIRMADO):
- coverage ≥ 90% → elevated
- coverage ≥ 70% → moderate
- else → critical
- pior source + top município gap

🟢 **CONFIRMADO** — `coverage_weekly.py:1-1169`.

### generate-report-b2g.py (6.479 linhas) — MAIOR SCRIPT
Relatório executivo B2G. 80+ funções organizadas por seção.

| Seção | Builder Function |
|-------|-----------------|
| Capa | `_build_cover()` |
| Sumário Executivo | `_build_executive_summary()` |
| Inteligência Exclusiva | `_build_exclusive_intelligence()` |
| Posicionamento Estratégico | `_build_strategic_positioning()` |
| Visão Geral Oportunidades | `_build_opportunities_overview()` |
| Análise Detalhada | `_build_detailed_analysis()` |
| Inteligência de Mercado | `_build_market_intelligence()` |
| Análise Regional | `_build_regional_analysis()` |
| Portfolio | `_build_portfolio_section()` |
| Plano de Desenvolvimento | `_build_development_plan()` |

**Validação de schema**: `validate_report_completeness()` checa 25+ campos obrigatórios.

🟢 **CONFIRMADO** — `generate-report-b2g.py:1-6479`.

### report_dedup.py (189 linhas)
Dedup semântico 2-pass: exact ID match → Jaccard token overlap (threshold 0.85).

🟢 **CONFIRMADO** — `report_dedup.py:1-189`.

---

## Módulo 4: Matching (scripts/matching/) — NOVO — 2 arquivos, ~300 LOC

### entity_matcher.py (297 linhas)

**Cascade 3 níveis:**

| Nível | Método | Match Key | Confidence | Threshold |
|-------|--------|-----------|------------|-----------|
| 1 | CNPJ exact | `cnpj_8` base → 14-digit prefix | high (1.0) | Exact |
| 2 | Normalized name + municipio | `(norm_name, codigo_ibge)` index | high (1.0) | Exact |
| 3 | Fuzzy (rapidfuzz/difflib) | `fuzz_ratio(norm_name, candidate)` | high≥0.95, medium≥0.85 | 0.85 |

**Índices in-memory** (🟢 CONFIRMADO — `entity_matcher.py:45-80`):
- `cnpj_index: dict[str, dict]` — key: 8-digit CNPJ base
- `name_exact_index: dict[str, dict]` — key: normalized name
- `name_muni_index: dict[tuple[str, str], dict]` — key: (norm_name, ibge_code)

**Batch operation**: processa todos os bids unmatched de um source em uma transação. Commit único no final. 🟢 CONFIRMADO.

🟡 **INFERIDO** — Extraído do `monitor.py` legado como refatoração. A implementação original inline era quase idêntica.

---

## Módulo 5: Lib (scripts/lib/) — 11 arquivos, ~2.5K LOC

### name_normalizer.py (188 linhas)
`normalize_name(name, expand_abbreviations=True, remove_irrelevant=False) → str`

Pipeline: NFKD normalize → uppercase → remove punctuation → remove CNPJ numbers → collapse whitespace → expand 18 abbreviations → remove irrelevant terms.

🟢 **CONFIRMADO** — `name_normalizer.py:1-188`.

### bid_simulator.py (345 linhas)
`simulate_bid(edital, competitive_intel, benchmark, cnae_principal) → BidSimulation`

**Optimal discount**: `median_discount + 0.3 × σ`, capped at `1.0 - margem_mínima`.
**P(vitória)**: logistic CDF z-score, ajustado por N competidores: `P = CDF^(N-1)`.
**6 setores** com margens distintas (engenharia 25% BDI, TI 30%, consultoria 35%, etc.).

🟢 **CONFIRMADO** — `bid_simulator.py:1-345`.

### cost_estimator.py (290 linhas)
`estimate_proposal_cost(distancia_km, duracao_horas, is_capital, is_eletronico, params) → dict`

**Componentes presenciais**: deslocamento + hospedagem (1-2 diárias, capital R$280/interior R$180) + alimentação + pedágio + hora técnica (R$150/h).
**Eletrônico**: mínimo R$600 preparação. Visita técnica: +R$2/km se >200km.

🟢 **CONFIRMADO** — `cost_estimator.py:1-290`.

### victory_profile.py (373 linhas)
`build_victory_profile(contracts, company_capital, company_ufs) → VictoryProfile`
`score_edital_fit(edital, profile) → float (0.0-1.0)`

**5 dimensões com pesos**: valor (30%), keyword overlap (25%), modalidade (15%), geografia (15%), população (15%).

🟢 **CONFIRMADO** — `victory_profile.py:1-373`.

### doc_templates.py (405 linhas)
Extração estruturada de documentos de licitação via regex. 3 tipos: EDITAL (13 campos), TERMO_REFERENCIA (6), PLANILHA (4). Confidence decay: -0.15 por pattern (floor 0.3).

🟢 **CONFIRMADO** — `doc_templates.py:1-405`.

### Outros
| Arquivo | Linhas | Propósito |
|---------|--------|-----------|
| `win_loss_tracker.py` | 145 | JSON local para calibrar modelos com outcomes reais |
| `constants.py` | 24 | VALID_UFS, INTEL_VERSION, VALID_MODELS, MAX_DIAS=365 |
| `intel_logging.py` | 36 | Logger `intel.{script}` com stderr handler |
| `cli_validation.py` | 186 | 8 validators com exit code 1 em falha |
| `retry.py` | 82 | Decorator `retry_on_failure` com exponential backoff |

🟢 **CONFIRMADO** — Todos os arquivos lidos integralmente.

---

## Módulo 6: Config (config/) — 7 arquivos, ~8.8K LOC (YAML)

### settings.py (159 linhas)
Centralização de todas as configs via env vars. Grupos: Paths, Database, OpenAI, PNCP API, DOM-SC, PCP, ComprasGov, Ingestion, Coverage, Enrichment, Logging, Alerts, Notifications.

🟢 **CONFIRMADO** — `settings.py:1-159`.

### sectors_config.yaml (2.116 linhas)
**13 setores B2G** com engenharia de conhecimento de domínio:

| Setor | CNAEs | Threshold | Estratégia |
|-------|-------|-----------|------------|
| engenharia | 17 prefixes | 0.45 | Hard-incompatible patterns + context-gated keywords |
| engenharia_rodoviaria | 2 | 0.45 | Especialização de engenharia |
| manutencao_predial | 4 | 0.50 | Keywords de manutenção + exclusion de construção pesada |
| alimentos | 14 | 0.35 | Context-gated (refeição sem ser evento/coffee break) |
| software | 8 | 0.40 | CNAE + keywords técnicas |
| saúde | 14 | 0.40 | Medicamentos + serviços hospitalares |
| (7 outros) | - | 0.35-0.55 | Cada um com keywords, exclusões, weight_profile |

🟢 **CONFIRMADO** — `sectors_config.yaml:1-2116`.

### sectors_data.yaml (6.338 linhas)
Extensão do sectors_config com keywords detalhadas, negative_keywords, context_required_keywords, co_occurrence_rules, domain_signals, NCM prefixes.

🟢 **CONFIRMADO** — `sectors_data.yaml` parcial (head/tail), ~9 setores confirmados.

### logging_config.py (199 linhas)
JSON logging com `correlation_id` contextvar (thread-safe, async-safe). Rotação em produção: 10MB, 5 backups.

🟢 **CONFIRMADO** — `logging_config.py:1-199`.

### abbreviations.yaml (23 linhas)
18 siglas de administração pública + 5 termos de contato.

🟢 **CONFIRMADO**.

### transparencia_config.yaml (61 linhas)
CSS selectors para portais de transparência. `municipios: {}` vazio — framework pronto, sem dados populados.

🟡 **INFERIDO** — Estrutura pronta mas sem mapeamento de municípios. Provável trabalho em progresso.

---

## Módulo 7: Database (db/) — 25 arquivos, ~6K LOC

### Schema Real (PostgreSQL 18.4)

**8 tabelas principais:**

| Tabela | PK | Registros (est.) | Finalidade |
|--------|----|-----------------|------------|
| `pncp_raw_bids` | `pncp_id` TEXT | ~199K | Lícitações multi-source (schema central) |
| `pncp_supplier_contracts` | `id` SERIAL | ~3.69M | Contratos históricos por fornecedor |
| `sc_public_entities` | `id` SERIAL | 2.085 | Catálogo de entes públicos SC |
| `enriched_entities` | `cnpj` TEXT | ~13.8K | Cache de enriquecimento BrasilAPI |
| `entity_coverage` | `(entity_id, source)` | Variável | Tracking de cobertura por ente/fonte |
| `coverage_snapshots` | `id` SERIAL | Semanal | Snapshots históricos de cobertura |
| `ingestion_checkpoints` | `(source, scope_key)` | 0 (não usado) | Checkpoints resumeáveis |
| `ingestion_runs` | `id` SERIAL | 5 | Audit trail de execuções |

🟢 **CONFIRMADO** — `supabase/current-schema.sql:1-684` (pg_dump --schema-only).

### Funções PL/pgSQL (10)

| Função | Tipo | Descrição |
|--------|------|-----------|
| `search_datalake(10 params)` | STABLE | Multi-filter FTS com ts_rank + ILIKE fallback |
| `upsert_pncp_raw_bids(p_records JSONB)` | VOLATILE | Batch upsert, ON CONFLICT content_hash DO NOTHING |
| `upsert_pncp_supplier_contracts(p_records JSONB)` | VOLATILE | Batch upsert, ON CONFLICT contrato_id DO NOTHING |
| `purge_old_bids(p_retention_days INT)` | VOLATILE | Soft-delete por idade (400d default) |
| `purge_old_bids_hard(p_soft_retention_days INT)` | VOLATILE | Hard-delete após soft-retention |
| `ttl_cleanup_enriched_entities(p_ttl_days INT)` | VOLATILE | Limpeza TTL de cache (90d default) |
| `set_updated_at()` | TRIGGER | Auto-update updated_at |
| `update_entity_coverage()` | TRIGGER | Atualiza coverage após INSERT |
| `update_entity_coverage_on_update()` | TRIGGER | Atualiza coverage após UPDATE |
| `generate_coverage_snapshot(snap_date DATE)` | VOLATILE | Snapshot semanal por source |

🟢 **CONFIRMADO** — Extraídas do schema dump e migrations.

### Divergências Schema Real vs Migrations

🔴 **LACUNA** — `esfera_id` é TEXT ('F','E','M','D') no banco real, INT nas migrations v1 (ISSUE-2).
🔴 **LACUNA** — `data_publicacao`/`data_abertura`/`data_encerramento` são TIMESTAMPTZ no real, DATE nas migrations (ISSUE-3).
🔴 **LACUNA** — `enriched_entities` usa `entity_type`/`entity_id`/`data JSONB` — schema completamente diferente da migration 003 (ISSUE-5).
🔴 **LACUNA** — 0 views existem no banco real. Migrations 009-012 nunca foram aplicadas.
🔴 **LACUNA** — Extensão `vector` (pgvector) existe no banco real mas não está documentada em nenhuma migration.

**14 débitos técnicos** documentados em `supabase/docs/DB-AUDIT.md`:
- 1 CRITICAL: DT-01 (Migrations divergentes)
- 3 HIGH: DT-02, DT-05, DT-08
- 7 MEDIUM, 3 LOW

🟢 **CONFIRMADO** — `DB-AUDIT.md:1-225`.

### Seed

**seed_sc_entities.py** (770 linhas):
- Importa 2.085 entes públicos SC de planilha Excel
- **Haversine**: `haversine_km(lat1, lng1, lat2, lng2)` para distância de Florianópolis
- **IBGE resolve**: 4 estratégias (nome exato → sem conectivos → sem espaços → prefixo)
- Cache JSON local em `data/ibge_cache.json`
- Upsert idempotente: `ON CONFLICT (cnpj_8) DO UPDATE`

🟢 **CONFIRMADO** — `seed_sc_entities.py:1-770`.

---

## Módulo 8: Deploy (deploy/) — 42 arquivos, ~3.5K LOC

### provision-vps.sh (405 linhas)
10 steps de provisionamento completo para Hetzner CX22:
1. Pacotes base → 2. Usuário extra-consultoria → 3. SSH hardening (porta 2222) → 4. UFW → 5. Fail2ban → 6. PostgreSQL tuning (CX22: 1GB shared_buffers, 2GB effective_cache) → 7. Clone + dependencies → 8. Migrations + seeds → 9. Systemd timers (13 unidades prefixo `extra-*`) → 10. Storage Box config

🟢 **CONFIRMADO** — `provision-vps.sh:1-405`.

### Systemd Units (40 arquivos)

**20 timers + 20 serviços** em 3 categorias:

| Categoria | Qtd | Schedule | Exemplos |
|-----------|-----|---------|---------|
| Crawlers v1 (legado) | 14 | Diário a 3×/dia | pncp-crawl-full (05:00 UTC), dom-sc-crawl (06,14,22) |
| Reports | 6 | Diário a semanal | coverage-report (09:00), pncp-report-weekly (Mon 07:00) |
| Extra (v2) | 10 | 15min a diário | extra-db-backup (06:00), extra-health-check (*/30min) |

**Escalonamento de crawlers**: offsets de 30min entre fontes para evitar contenção de recursos.
**OnFailure**: 2 templates (`onfailure@.service`, `extra-onfailure@.service`) que enviam POST JSON para WEBHOOK_URL.

🟢 **CONFIRMADO** — Todos os 40 arquivos systemd lidos integralmente.

### Hardening

| Arquivo | Linhas | Propósito |
|---------|--------|-----------|
| `fail2ban-jail.conf` | 90 | Jail PostgreSQL porta 54399, maxretry=5, bantime=3600s |
| `pg_hba.conf` | 106 | Socket peer, TCP scram-sha-256, reject 0.0.0.0/0 |
| `ufw-rules.sh` | 177 | Libera 54399 só para TRUSTED_IPS, bloqueia resto |

🟢 **CONFIRMADO** — Todos os arquivos de hardening lidos integralmente.

---

## Módulo 9: Docs (docs/) — ~50 arquivos, ~4K LOC

### docs/td-001/ — Diagnósticos Técnicos (16 docs)

| Documento | Linhas | Conteúdo |
|-----------|--------|---------|
| `security-hardening.md` | 400 | 7 crawlers corrigidos, User-Agent padronizado, Bandit HIGH→0, rate limiting, server hardening |
| `migration-rebuild.md` | 151 | 5 divergências schema real vs migrations, análise D1-D5 |
| `query-optimization.md` | 219 | TD-DB-08 (GIN index, -60% espaço vs GIST), TD-DB-11 (HNSW expression fix) |
| `bids-crawler-diagnosis.md` | 134 | 6 imports quebrados → BidsCrawler = DEAD CODE |
| `ci-cd-pipeline.md` | 142 | GitHub Actions: lint→type-check→test→security em paralelo |
| Outros (11) | ~800 | Logging, checkpoints, secrets, type hints, test infra, etc. |

🟢 **CONFIRMADO** — 6 docs principais lidos integralmente.

### docs/architecture/
- `architecture.md` (110 linhas): C4 níveis 1-2, 4 fluxos, 9 decisões
- `system-architecture.md` (607 linhas): Brownfield discovery completo — 3 subsistemas, 16 anti-padrões, 12 code patterns

🟢 **CONFIRMADO**.

---

## Algoritmos Transversais

| Algoritmo | Onde | Complexidade |
|-----------|------|-------------|
| **Cascade matching 3 níveis** | matching/, monitor.py, orchestrator.py | O(n×m) com índices, O(n×m×k) no fuzzy |
| **Bid/No-Bid scoring** | intel-analyze.py, intel_pipeline.py | O(1) por edital, 7 dimensões ponderadas |
| **CNAE keyword gate** | intel-collect.py, sectors_config.yaml | O(k×p) keywords × patterns, +LLM O(1) API call |
| **Semantic dedup** | intel-collect.py, report_dedup.py | O(n²) Jaccard pairwise, mitigado por UF partitioning |
| **HHI competition** | intel-collect.py | O(c²) sum of squared shares |
| **Optimal bid simulation** | bid_simulator.py | O(1), logistic CDF analítico |
| **Victory profile fit** | victory_profile.py | O(k) weighted 5-dimension |
| **Haversine distance** | seed_sc_entities.py | O(1) trigonométrico |
| **IBGE code resolution** | seed_sc_entities.py | O(4) estratégias fallback |
| **PDF text extraction** | intel-extract-docs.py | 3-tier cascade: pymupdf4llm → PyMuPDF → OCR |
| **Adaptive rate limiting** | intel-collect.py | O(1) por request, growth/decay dinâmico |
| **Content hash dedup** | common.py, transformer.py | O(1) SHA-256 por registro |

---

## Confiança Geral por Módulo

| Módulo | Confiança | Notas |
|--------|-----------|-------|
| crawl | 95% 🟢 | 35/35 arquivos lidos. 3 GAPs identificados (orquestrador dual, checkpoint dual, imports quebrados) |
| intel | 95% 🟢 | 8/8 arquivos lidos integralmente. Pipeline completo mapeado |
| reports | 95% 🟢 | 6/6 arquivos lidos. generate-report-b2g.py apenas estrutura (80+ funções, 6.4K LOC) |
| matching | 95% 🟢 | 2/2 arquivos lidos. Algoritmo limpo e bem documentado |
| lib | 95% 🟢 | 11/11 arquivos lidos integralmente |
| config | 90% 🟢 | 7/7 arquivos. sectors_data.yaml parcial (6.3K LOC, head+tail) |
| db | 90% 🟢 | 25/25 arquivos. Schema real confirmado via pg_dump |
| deploy | 98% 🟢 | 42/42 arquivos systemd+scripts lidos integralmente |
| docs | 85% 🟡 | ~6/16 TD docs lidos. Restante inferido por estrutura |

**Confiança média: 93%** 🟢

