# Domínio — Extra Consultoria

> Gerado pelo Detective em 2026-07-13T17:00:00Z
> doc_level: completo
> Base: commit 249340d (QW-01 Radar + Competitive Intel + Readiness Gates)
> Delta: 30 commits desde e9729e1 (182 arquivos, +47K/-20K LOC)

---

## Glossário de Domínio

| Termo | Definição | Fonte |
|-------|----------|-------|
| **Edital** | Licitação pública registrada no sistema. Unidade central de análise. | `pncp_raw_bids` |
| **Ente público** | Órgão da administração pública (prefeitura, câmara, fundo, autarquia) de Santa Catarina. | `sc_public_entities` |
| **Modalidade** | Tipo de licitação: Concorrência(4), Pregão Eletrônico(5), Pregão Presencial(6), Contratação Direta(7), Inexigibilidade(8), Credenciamento(12) | `modalidade_id` |
| **Esfera** | Nível de governo: Federal(F), Estadual(E), Municipal(M), Distrital(D) | `esfera_id` |
| **Coverage** | Percentual de entes públicos monitorados que tiveram licitações capturadas nos últimos 90 dias por fonte | `entity_coverage` |
| **CNAE** | Classificação Nacional de Atividades Econômicas. Prefixos de 4 dígitos mapeiam empresa a setores de licitação | `sectors_config.yaml` |
| **Intel Pipeline** | Pipeline de 7 estágios que transforma CNPJ em relatório executivo de inteligência de mercado | `intel_pipeline.py` |
| **Quality Gate** | Ponto de validação entre estágios do pipeline. 5 gates bloqueiam progressão se critérios não atendidos | `intel_pipeline.py:gates` |
| **Content Hash** | SHA-256 de campos-chave do edital para deduplicação cross-source | `common.py:generate_content_hash` |
| **Entity Match** | Vinculação de um edital ao ente público correspondente via cascade 3 níveis | `entity_matcher.py` |
| **Bid Score** | Score 0-1 de adequação estratégica de um edital para uma empresa, calculado em 7 dimensões | `intel-analyze.py:_compute_bid_score` |
| **HHI** | Índice Herfindahl-Hirschman de concentração de mercado. Soma dos quadrados das fatias de mercado | `intel-collect.py:_compute_intel_metrics` |
| **Soft-delete** | Marcação `is_active=FALSE` em vez de DELETE físico. Retenção de 400 dias antes de hard-delete | `purge_old_bids()` |
| **Source** | Fonte de dados de licitações: pncp, dom_sc, doe_sc, pcp, compras_gov, sc_compras, tce_sc, transparencia, contracts | `monitor.py:SOURCES` |
| **Checkpoint** | Marcação de progresso de crawler para retomada após interrupção. Evita re-processamento | `ingestion_checkpoints` |
| **Snapshot** | Registro semanal de cobertura para análise de tendência temporal | `coverage_snapshots` |
| **Coverage Truth** | Auditoria determinística de cobertura: cada (entity, source) tem estado de evidência auditável no ledger. NUNCA infere cobertura sem registro | `coverage_evidence` |
| **Evidence Ledger** | Tabela imutável `coverage_evidence` que registra cada tentativa de crawl por (entity, source, data_type, run_id). Fonte única de verdade sobre cobertura | `coverage_evidence` |
| **Canonical Universe** | Planilha seed "Extra - alvos de licitação. R-0.xlsx" como autoridade única de membership. DB radius flags são dados diagnósticos, NUNCA denominador | `scripts/lib/universe.py` |
| **QW-01 Radar** | Pipeline operacional de oportunidades abertas: crawl → dedup → status canônico → ranking → scoring → CSV auditável. PostgreSQL-only, determinístico | `scripts/opportunity_intel/radar.py` |
| **Deságio** | Desconto entre valor estimado (edital) e valor homologado/contratado. Fórmula: (estimado − homologado) / estimado. NUNCA entre global e outro estágio semântico | `scripts/lib/value_semantics.py` |
| **HHI** | Índice Herfindahl-Hirschman de concentração de mercado. ≤2=BAIXA, ≤5=MEDIA, ≤10=ALTA, >10=MUITO_ALTA. Calculado global + por entidade | `scripts/opportunity_intel/ranking.py` |
| **Readiness Gate** | Gate CI: coverage ≥ 95% → exit 0; coverage < 95% → exit 2 (fail-closed). Bloqueia deploy se cobertura insuficiente | `scripts/consulting_readiness.py` |
| **Freshness Gate** | Gate CI: verifica SLA de frescor por fonte crítica. PNCP: 24h, Contracts: 24d. Exit 0 se todas fresh, exit 2 se stale | `scripts/freshness_gate.py` |
| **Fail-Closed** | Padrão arquitetural: na dúvida, falha. Status desconhecido → `unknown`. Cobertura não verificada → `not_investigated`. Nunca assume sucesso por default | Cross-cutting |
| **SOURCE_BLOCKERS** | 7 fontes com bloqueio documentado (Selenium, CAPTCHA, GCP creds, etc.). Sobrescrevem qualquer status do DB. Impedem falsos positivos de cobertura | `consulting_readiness.py` |
| **Conservative Denominator** | Denominador sempre inclui entidades não resolvidas. `conservative_monitoring_population = resolved + unresolved`. Nunca subestima população | `lib/universe.py` |
| **Value Semantics** | 5 estágios semânticos de valor: ESTIMADO → HOMOLOGADO → CONTRATADO → PAGO → GLOBAL. Cada source expõe valor em estágio específico. Proibido comparar estágios diferentes | `lib/value_semantics.py` |
| **Triage** | Classificação final da oportunidade: GO (score ≥ 70), REVIEW (40-69), NO_GO (< 40). Sempre triagem para humano — NUNCA decisão autônoma de participar | `opportunity_intel/scoring.py` |
| **Client Profile** | YAML de perfil do cliente com CNAEs, keywords, municípios prioritários, limites financeiros. Alimenta scoring contextualizado. Ex: `config/client_profiles/extra.yaml` | `opportunity_intel/profile.py` |

---

## Regras de Negócio Implícitas

### R1: Filtro de Engenharia (Crawl)
**Regra:** Licitações do PNCP são filtradas por 17 keywords de engenharia civil. Registros sem match em `objeto_compra` são descartados.

🟢 CONFIRMADO — `pncp_crawler_adapter.py:_transform_record()`. Keywords: "construç", "obra", "engenharia", "paviment", "infraestrutura", "edificaç", "saneamento", "drenagem", "terraplanagem", "fundação", "estrutural", "rodovi", "pontilh", "concreto", "asfal", "manutenção predial", "reforma".

### R2: Janela de Cobertura (Coverage)
**Regra:** Um ente público é considerado "coberto" por uma fonte se teve pelo menos 1 licitação capturada nos últimos 90 dias. A janela é calculada via `GREATEST(last_seen_at, CURRENT_DATE - 90)`.

🟢 CONFIRMADO — `update_entity_coverage()` trigger function, `COVERAGE_WINDOW_DAYS=90`.

### R3: Raio de 200km (Geo-foco)
**Regra:** Entes públicos são classificados como `within_200km` se sua distância de Florianópolis (calculada via Haversine) for ≤ 200km. Usado como filtro primário de relevância geográfica.

🟢 CONFIRMADO — `seed_sc_entities.py:haversine_km()`, `sc_public_entities.raio_200km`.

### R4: Capacidade Financeira 10× (Intel Pipeline)
**Regra:** Apenas licitações com valor estimado ≤ 10× o capital social da empresa são consideradas viáveis. As que excedem vão para "consórcio" ou são descartadas.

🟢 CONFIRMADO — `intel-enrich.py:271-284`, `intel-extract-docs.py:select_top_editais()`.

### R5: Threshold de Participação (Bid/No-Bid)
**Regra:** Score combinado < 0.45 força recomendação "NAO PARTICIPAR". Scores são calculados em 7 dimensões ponderadas.

🟢 CONFIRMADO — `intel-analyze.py:BID_SCORE_THRESHOLD=0.45`.

### R6: Override de Recomendação (Intel Pipeline)
**Regra:** 6 regras mandatórias que sobrescrevem qualquer análise LLM:
1. Status EXPIRADO → NAO PARTICIPAR
2. Empresa sancionada (CEIS/CNEP) → NAO PARTICIPAR
3. CNAE confidence = 0% → NAO PARTICIPAR
4. CNAE < 20% AND victory_fit < 15% → NAO PARTICIPAR
5. Bid score < 0.20 → NAO PARTICIPAR
6. Nivel_dificuldade.geral ∉ {BAIXO, MEDIO, ALTO} → inválido

🟢 CONFIRMADO — `intel-validate.py:499-579`.

### R7: Hard Incompatible Patterns (CNAE Gate)
**Regra:** 4 combinações CNAE+regex que forçam INCOMPATÍVEL independente de outras evidências:
1. software/sistema/erp quando CNAE é construção (42/43/41)
2. alimentação/refeição quando CNAE é engenharia (71/42/43)
3. limpeza/conservação quando CNAE é construção (42/43/41)
4. concessão/zona azul quando CNAE é construção (42/43/41)

🟢 CONFIRMADO — `intel-validate.py:HARD_INCOMPATIBLE_PATTERNS`.

### R8: Dedup Cross-Source (Crawl)
**Regra:** Registros de fontes diferentes representando a mesma licitação são identificados via content_hash SHA-256 e unificados no upsert (ON CONFLICT DO NOTHING).

🟢 CONFIRMADO — `upsert_pncp_raw_bids()`, `common.py:generate_content_hash()`.

### R9: Retenção e Purge (Database)
**Regra:** Licitações são soft-deletadas após 400 dias da data de publicação. Após +90 dias em soft-delete, são removidas permanentemente (hard-delete).

🟢 CONFIRMADO — `purge_old_bids(400)`, `purge_old_bids_hard(90)`.

### R10: Cache de Enriquecimento (Database)
**Regra:** Dados de enriquecimento (BrasilAPI, IBGE) têm TTL de 90 dias. Registros stale (>30 dias sem update) são re-enriquecidos.

🟢 CONFIRMADO — `ttl_cleanup_enriched_entities(90)`, `ENTITY_ENRICHMENT_TTL_DAYS=30`.

### R11: Limite de Documentos por Edital (Intel Pipeline)
**Regra:** Máximo de 3 documentos baixados por edital (prioridade: edital > termo de referência > planilha). Download limitado a 50MB por arquivo. Texto extraído limitado a 60K caracteres por edital.

🟢 CONFIRMADO — `intel-extract-docs.py:MAX_DOCS_PER_EDITAL=3, MAX_DOWNLOAD_BYTES=50MB, MAX_TEXT_PER_EDITAL=60000`.

### R12: Frequência de Crawl por Fonte (Deploy)
**Regra:** Cada fonte tem frequência de atualização específica baseada na criticidade e volume:
- PNCP: full diário (05:00 UTC) + incremental 3×/dia
- DOM-SC: 3×/dia (06, 14, 22 UTC)
- DOE-SC: diário (03:00 UTC)
- TCE-SC: diário (05:30 UTC)
- Contratos: 3×/semana (Mon, Wed, Fri)
- Transparência: semanal (domingo)

🟢 CONFIRMADO — 20 systemd timer files.

### R13: Isolamento de Schema por Source (Database)
**Regra:** Cada fonte de dados tem seu próprio schema de validação e transformação, mas todos convergem para `pncp_raw_bids` unificado. A coluna `source` preserva a proveniência.

🟢 CONFIRMADO — Todos os crawlers implementam `transform() → pncp_raw_bids schema`.

### R14: Keyword Gate Probabilístico (Intel Pipeline)
**Regra:** A compatibilidade CNAE de um edital é calculada probabilisticamente:
- Base: densidade de keywords no objeto (cap 60%)
- Bônus: +20% strong_compatible, +10% weak_compatible
- Penalidade: -30% exclusion match
- Bônus CNAE: +10% se prefix match
- Threshold: ≥ 35% = COMPATÍVEL, < 35% = INCOMPATÍVEL
- Casos ambíguos (confidence < 40%): fallback para GPT-4.1-nano

🟢 CONFIRMADO — `intel-collect.py:apply_cnae_keyword_gate()`.

### R15: Competição por HHI (Intel Pipeline)
**Regra:** Nível de concorrência classificado por HHI: ≤2=BAIXA, ≤5=MEDIA, ≤10=ALTA, >10=MUITO_ALTA. Afeta P(vitória) e recomendação.

🟢 CONFIRMADO — `intel-collect.py:_compute_intel_metrics()`.

### R16: Zero False Negative Philosophy (Intel Pipeline)
**Regra:** Pipeline de coleta prioriza recall sobre precision. Prefere incluir editais borderline e deixar o CNAE gate + LLM filtrar, a arriscar perder oportunidades por filtragem precoce.

🟡 INFERIDO — Consistente com 12 sub-etapas de coleta, keyword gate probabilístico, e LLM fallback. Não declarado explicitamente, mas evidente no design.

### R17: Single Tenant (Arquitetura)
**Regra:** Sistema opera como single-tenant para Extra Construtora. Não há isolamento multi-cliente. Configurações de setor, CNAE e keywords são específicas para engenharia civil.

🟡 INFERIDO — Hardcoded "Extra Construtora" em PDFs, keywords de engenharia, foco SC. Adaptável via config, mas não multi-tenant.

### R18: Deságio — Estágios Semânticos de Valor (Regra #8)
**Regra:** Deságio só pode ser calculado entre ESTIMADO e HOMOLOGADO (ou CONTRATADO) da MESMA licitação. NUNCA entre `valor_global` (PNCP contracts) e `valor_total_estimado` (PNCP bids) sem verificar que são a mesma licitação. Os 5 estágios semânticos são imutáveis: ESTIMADO → HOMOLOGADO → CONTRATADO → PAGO → GLOBAL. `valor_global` do PNCP NÃO é "preço praticado" — é teto contratual máximo.

🟢 CONFIRMADO — `scripts/lib/value_semantics.py:calculate_desagio()`, `compute_bid_contract_desagio()`. Enum `ValorSemantica` com 5 estágios. `SOURCE_VALUE_TYPES` mapeia cada (source, entity_type) ao seu estágio semântico. Reclassificado como LIMITED em 2026-07-12 (commit 132df3e).

### R19: Competitive Intelligence — Market Share e HHI (Regra #9)
**Regra:** Market share é calculado como `share = valor_fornecedor / valor_total_entidade` usando apenas contratos CONFIRMADOS. HHI é calculado globalmente e por entidade. Ranking de fornecedores por: (1) número de contratos, (2) valor total, (3) número de entidades distintas servidas. Win rate permanece NOT_READY — métricas alternativas disponíveis (market share, award share, supplier ranking). TOP 20 fornecedores por valor. Ordenação: `ORDER BY total_value DESC`.

🟢 CONFIRMADO — `scripts/opportunity_intel/ranking.py:_compute_market_share()`, `_compute_hhi()`, `_compute_supplier_ranking()`. Commit 77265b5.

### R20: QW-01 Radar — Threshold e Exit Codes
**Regra:** QW-01 radar operacional com 3 métricas de readiness:
1. `universe_resolution`: % de entidades do universo canônico resolvidas no DB
2. `monitoring_coverage`: % de entidades com evidência de monitoring success na janela
3. `data_presence`: % de entidades com pelo menos 1 registro em `pncp_raw_bids`

Monitoring threshold: **95%**. Abaixo disso → exit code 2. Radar NUNCA emite veredito definitivo de participação — sempre triagem para humano.

🟢 CONFIRMADO — `scripts/opportunity_intel/radar.py:MONITORING_THRESHOLD=95.0`, `build_monitoring_metrics()`. Commit ce55095, 249340d.

### R21: Coverage Truth — Evidence Ledger Imutável
**Regra:** Toda alegação de cobertura deve ser rastreável a uma linha em `coverage_evidence`. 10 estados possíveis: `success_with_data`, `success_zero`, `partial`, `connection_failed`, `auth_failed`, `parse_failed`, `transform_failed`, `persist_failed`, `not_applicable`, `not_investigated`. Mapeamento determinístico: `monitor_status + error_code → evidence_state`. Estado default para fonte nunca investigada: `not_investigated`. Estado para fonte bloqueada: `not_applicable`.

🟢 CONFIRMADO — `scripts/crawl/monitor.py:_map_evidence_state()`, `_project_entity_evidence()`. `supabase/migrations/006-v3-unified-schema.sql:391` (enum definition). Commits a91ccfd, 0ee490b.

### R22: Consulting Readiness Gate — Fail-Closed
**Regra:** Gate de CI que bloqueia deploy se cobertura < 95%. Calcula cobertura como `entidades_com_evidencia / conservative_monitoring_population`. Nunca marca fonte bloqueada como "coberta" — `SOURCE_BLOCKERS` sobrescreve qualquer status do DB. Exit 0 = pronto para consultoria, Exit 2 = dados insuficientes, Exit 1 = falha técnica.

🟢 CONFIRMADO — `scripts/consulting_readiness.py:main()`. 7 fontes em `SOURCE_BLOCKERS`. Commit 9e2ff90, 1195495.

### R23: Freshness Gate SLA — Configurável por Fonte
**Regra:** Cada fonte crítica tem SLA de frescor independente, configurável via env vars:
- PNCP (editais abertos): `FRESHNESS_SLA_PNCP_HOURS` (default 24h), `FRESHNESS_RECENT_WINDOW_PNCP_HOURS` (default 24h)
- Contracts (histórico): `FRESHNESS_SLA_CONTRACTS_HOURS` (default 576h = 24 dias), `FRESHNESS_RECENT_WINDOW_CONTRACTS_HOURS` (default 168h = 7 dias)

Gate verifica `MAX(last_run_at) ≥ NOW() - SLA` para cada critical source. Exit 0 se todas fresh.

🟢 CONFIRMADO — `scripts/freshness_gate.py:CRITICAL_SOURCES`. Commits 15177dc, 3eeb4d6, 1c8b63f.

### R24: CI Fail-Closed — Gates Bloqueiam Progressão
**Regra:** Todos os gates de CI seguem padrão fail-closed: na dúvida, falha. Readiness gate + Freshness gate são pré-condições para deploy. Restaurados como críticos após remediação P1 (commit 0fef9de). Nenhum gate pode ser bypassed sem documentar justificativa.

🟢 CONFIRMADO — `scripts/consulting_readiness.py` exit codes, `scripts/freshness_gate.py` exit codes. Commits 0fef9de, 824af88.

### R25: Canonical Universe — Planilha como Autoridade
**Regra:** A planilha "Extra - alvos de licitação. R-0.xlsx" é a ÚNICA autoridade para membership no universo alvo. Coluna `COL_RAIO200` (index 9) com valor "SIM ✓" é o flag autoritativo de raio. DB radius flags (`sc_public_entities.raio_200km`) são dados diagnósticos, NUNCA denominador. Hash SHA-256 do arquivo seed registrado em todo artefato para auditabilidade. Constante `CANONICAL_UNIVERSE = 1093` é valor histórico legado — código novo DEVE derivar de `load_canonical_universe()`.

🟢 CONFIRMADO — `scripts/lib/universe.py:load_canonical_universe()`, `CanonicalEntity`, `sha256_file()`. Commit 824af88.

### R26: Conservative Denominator — População Nunca Subestimada
**Regra:** `conservative_monitoring_population = resolved + unresolved`. Entidades não resolvidas (sem CNPJ8 match no DB) contam no denominador. Isso garante que cobertura nunca seja superestimada por excluir entidades que o sistema não conseguiu encontrar. Entidades com `COL_RAIO200 != "SIM ✓"` são excluídas (fora do raio), não unresolved.

🟢 CONFIRMADO — `scripts/lib/universe.py:CanonicalUniverse.conservative_monitoring_population`. `scripts/opportunity_intel/radar.py:build_monitoring_metrics()`.

---

## Eventos de Negócio Monitorados

| Evento | Onde | Severidade |
|--------|------|-----------|
| Crawl concluído com sucesso | `ingestion_runs.status='completed'` | INFO |
| Crawl falhou (API fora, timeout) | `ingestion_runs.status='failed'` + webhook | HIGH |
| Circuit breaker aberto para fonte | `circuit_breaker.degraded` | MEDIUM |
| Entidade sancionada detectada | `sanctions.py:is_sanctioned=True` | HIGH |
| Cobertura abaixo do target | `coverage_weekly.py:gap detection` | MEDIUM |
| Disco baixo (<10%) | `check-alerts.py` | CRITICAL |
| Backup falhou | `backup-database.sh` exit ≠ 0 + webhook | CRITICAL |
| API key inválida/expirada | Crawlers 401 → log ERROR | HIGH |
| Documento corrompido/OCR trigger | `intel-extract-docs.py: avg_chars<100` | LOW |
| Migration pendente | `verify-schema-divergence.sh` | MEDIUM |
| Delta detectado (NOVO/ATUALIZADO) | `intel-collect.py:_detect_delta()` | INFO |
| Readiness gate FAIL | `consulting_readiness.py` exit 2 | CRITICAL |
| Freshness gate STALE | `freshness_gate.py` exit 2 | CRITICAL |
| QW-01 radar abaixo 95% | `radar.py:monitoring_coverage < 95%` | HIGH |
| Evidência de cobertura projetada | `coverage_evidence` INSERT | INFO |
| Fonte bloqueada reportada como coberta | `SOURCE_BLOCKERS` override | CRITICAL |

---

## Constantes de Domínio

| Constante | Valor | Significado |
|-----------|-------|------------|
| `COVERAGE_WINDOW_DAYS` | 90 | Janela para considerar ente "coberto" |
| `INGESTION_MODALIDADES` | {4,5,6,7} | Modalidades buscadas (exclui inexigibilidade e credenciamento) |
| `INGESTION_UFS` | ['SC'] | UFs monitoradas |
| `BID_SCORE_THRESHOLD` | 0.45 | Nota mínima para recomendar participação |
| `CNAE_CONFIDENCE_THRESHOLD` | 0.35 | Confiança mínima para classificar como compatível |
| `ENTITY_MATCH_FUZZY_THRESHOLD` | 0.85 | Similaridade mínima para match fuzzy |
| `MAX_CAPACITY_MULTIPLIER` | 10 | Teto de valor de edital como múltiplo do capital social |
| `PURGE_RETENTION_DAYS` | 400 | Dias antes de soft-delete |
| `PURGE_HARD_RETENTION_DAYS` | 90 | Dias em soft-delete antes de hard-delete |
| `ENRICHMENT_TTL_DAYS` | 90 | TTL do cache de enriquecimento |
| `SANCTIONS_CACHE_TTL_HOURS` | 24 | TTL do cache de sanções |
| `MAX_DOCS_PER_EDITAL` | 3 | Máximo de documentos baixados por edital |
| `MAX_DOWNLOAD_BYTES` | 50MB | Limite de download por arquivo |
| `MAX_TEXT_PER_EDITAL` | 60K chars | Limite de texto extraído por edital |
| `MONITORING_THRESHOLD` | 95.0% | Threshold mínimo de cobertura para QW-01 radar |
| `FRESHNESS_SLA_PNCP_HOURS` | 24 | SLA de frescor para editais abertos PNCP |
| `FRESHNESS_SLA_CONTRACTS_HOURS` | 576 | SLA de frescor para contratos históricos (24 dias) |
| `CANONICAL_UNIVERSE` | 1093 | Tamanho legado do universo canônico (não usar como denominador) |
| `DEFAULT_RADIUS_KM` | 200.0 | Raio padrão a partir de Florianópolis |
| `READINESS_THRESHOLD` | 0.95 | Threshold mínimo para consulting readiness gate |
| `RANKING_GO_THRESHOLD` | 70 | Score mínimo para triagem GO |
| `RANKING_REVIEW_MIN` | 40 | Score mínimo para triagem REVIEW (abaixo = NO_GO) |
| `FLORIANOPOLIS_LAT` | -27.5954 | Latitude do centro geo de referência |
| `FLORIANOPOLIS_LON` | -48.5480 | Longitude do centro geo de referência |

---

## Fontes de Evidência

| Fonte | Tipo | Artefatos |
|-------|------|-----------|
| Código Python | 🟢 CONFIRMADO | 277 arquivos, 137K LOC |
| Migrations SQL | 🟢 CONFIRMADO | 41 migrations (v1+v2+v3) |
| Git log | 🟢 CONFIRMADO | 30 novos commits (e9729e1..249340d), 4 epics |
| Config YAML | 🟢 CONFIRMADO | 13 setores, 8.8K LOC, client profiles |
| Systemd units | 🟢 CONFIRMADO | 40 arquivos |
| Spreadsheet seed | 🟢 CONFIRMADO | "Extra - alvos de licitação. R-0.xlsx", SHA-256 auditável |
| Docs | 🟢 CONFIRMADO | 590+ arquivos, 7 epics, PRDs, runbooks, ADRs |

---

## Lacunas 🔴 (baseline 2026-07-13 — parcialmente superadas em 2026-07-17)

1. **LACUNA** — Modelo comercial humano (ticket, pricing de serviço consultoria) ainda implícito — parcialmente endereçado por ADR-022 Client Profile, mas proposta comercial de serviço da Extra permanece fora do código.
2. ~~Orquestradores duplicados~~ → **RESOLVIDO 🟢**: `orchestrator.py` marcado DEPRECATED; `monitor.py` + registry + resilient_cycle são o caminho vivo.
3. **LACUNA** — Divergência residual schema vs migrations ainda monitorada por `scripts/schema/audit_sql_references.py` e `verify-schema-divergence.sh`.
4. **LACUNA** — Win rate de fornecedores permanece `NOT_READY` (sem resultados oficiais de vencedor em todas as fontes).
5. **PARCIAL** — DOE/DOM/SC Compras com ingestão real de atos; ComprasGov homologado e TCE empenhos ainda limitados.
6. **PARCIAL** — Blockers por fonte migraram para ESR + gap_report; M2 operacional strict ainda 0/1093 na sessão carimbada 2026-07-17.

---

# Escopo almejado (binding 2026-07-17)

> 🟢 **`DOD.md` (raiz do repositório) é a definição de escopo almejado do projeto.**  
> Este `domain.md` descreve regras e glossário **as-is** extraídos do código.  
> Metas de pronto, exclusões de obra física, 95% operacional, gates `LOCAL_READY` / `VPS_OPERATIONAL` / `PROJECT_DONE` e claims permitidos vêm do **DOD**, não deste arquivo.  
> Mapa completo: `_reversa_sdd/target-scope-dod.md`.

---

# Re-extração Detective — 2026-07-17

> HEAD `d3e82ba` | 131 commits | Plataforma B2G operacional + local resilience  
> Fontes: código, migrations 052–054, ADRs 017–022 em `docs/architecture/adr/` + **DOD.md como alvo**

## Glossário adicional

| Termo | Definição | Evidência |
|-------|-----------|-----------|
| **Coverage Contract** | Contrato multi-métrica (M1–M5) com denominador fixo 1093 e dual-headline comercial×operacional | ADR-018, `coverage_contract.py` |
| **M1 Commercial Signal** | Entidades com oportunidade OPEN/UPCOMING/RECENT matched — **não** é meta 95% | ADR-018 |
| **M2 Operational Source Coverage** | Entidades com fonte aplicável + estágios comprovados + proveniência — meta ≥95% proposta | ADR-018 |
| **Entity Source Registry (ESR)** | Binding entidade→fonte→método→status para o universo 1093 | ADR-019, mig 053 |
| **Strict Operational** | Critério falível de “operacional”; proxies de volume no banco **não** contam | `is_strict_operational` |
| **Workspace Facade** | CLI única do consultor (`python -m scripts.workspace`) | ADR-017 |
| **Official Act** | Publicação DOE/DOM/CKAN normalizada com hash e proveniência | mig 052, `schema/official_acts.py` |
| **Deterministic Reconcile** | Match atos×PNCP só por identificadores explícitos (sem fuzzy livre) | `official_acts_reconcile.py` |
| **Adapter Contract** | `FetchResult` tipado: success/empty_confirmed/partial/rate_limited/auth_blocked/error | ADR-021 |
| **Local Resilience** | Checkpoints/raw/DLQ/evidence em filesystem pré-VPS; projeção SQL em mig 054 | `crawl/resilience/`, ADR-021 |
| **Class A–E artifacts** | Código/specs/evidência carimbada vs raw operacional vs segredos | ADR-020 |
| **Client Profile Law** | Perfil YAML é única lei comercial de ranking/triagem | ADR-022 |
| **List Identity** | \|covered\|+\|uncovered\|=denominator e \|covered\|=numerator | ADR-018, testes coverage |
| **Buyer Intel AEC** | Ranking de órgãos por keywords de engenharia/construção | `buyer_intel/ranking.py` |

## Regras de negócio novas / reforçadas

### R27: Dual-metric obrigatória (Coverage Contract)
**Regra:** Todo relatório/CLI de cobertura deve expor **M1 e M2 lado a lado**. Proibido reportar M3/M4 como “cobertura 95% da proposta”. Denominador **fixo 1093**.  
🟢 CONFIRMADO — ADR-018, `coverage_contract.py`, testes de list identity.

### R28: Denominador imutável do universo
**Regra:** 1.093 = entidades ativas raio 200km. Proibido encolher denominador para inflar %.  
🟢 CONFIRMADO — ADR-018, `lib/universe.py`, seed CSV.

### R29: M2 exige evidência completa de estágios
**Regra:** Status `accessible/collected/verified` sem proveniência (`run_id`, raw hash/URI, IDs normalizados) **não** entra em M2.  
🟢 CONFIRMADO — ADR-018, mig 054 `satisfactory` CHECK.

### R30: ESR é SoT entidade→fonte
**Regra:** Cobertura operacional por entidade só é honesta via Entity Source Registry (não só crawl global).  
🟢 CONFIRMADO — ADR-019, `source_registry/*`, mig 053.

### R31: Fail-closed em 429 e bulk incompleto
**Regra:** HTTP 429 → `rate_limited` (não success/empty). `pages_fetched < pages_expected` → `partial`. SC bulk incompleto não promove coverage satisfactory.  
🟢 CONFIRMADO — ADR-021, `resilience/adapters.py`, chaos tests.

### R32: empty_confirmed é o único zero-ok
**Regra:** Zero registros só é sucesso se `empty_confirmed` credível (`supports_zero_proof`).  
🟢 CONFIRMADO — ADR-021, registry `supports_zero_proof`.

### R33: Raw operacional fora do git
**Regra:** JSONL raw, checkpoints quentes e dumps **não** entram no git. Só evidência carimbada mínima em `docs/ops/session-*`.  
🟢 CONFIRMADO — ADR-020.

### R34: Workspace é facade, não reimplementação
**Regra:** `scripts/workspace` orquestra módulos existentes; não reescreve ranking/crawl. Offline → seções UNAVAILABLE com reason.  
🟢 CONFIRMADO — ADR-017, `workspace/queue.py`.

### R35: Client Profile é lei comercial única
**Regra:** Ranking/triagem/filtros default do workspace derivam do Client Profile versionado; labels humanos sobrescrevem modelo.  
🟢 CONFIRMADO — ADR-022 (código parcialmente alinhado via `opportunity_intel/profile.py`).

### R36: Edital/proposta default REVIEW
**Regra:** Scaffolds de edital/proposta **nunca** inventam GO sem evidência; default REVIEW.  
🟢 CONFIRMADO — ADR-017, `workspace/actions.py`.

### R37: Reconciliação de atos só determinística
**Regra:** Match DOE/DOM/Compras SC × PNCP usa RULE_PRIORITY de identificadores; sem fuzzy de texto livre.  
🟢 CONFIRMADO — `matching/official_acts_reconcile.py`.

### R38: valor_global ≠ preço praticado
**Regra:** (reforço de R-value) PNCP contracts = CONTRATADO; proibido tratar GLOBAL como preço pago.  
🟢 CONFIRMADO — `lib/value_semantics.py`, ADR-015.

### R39: List identity de cobertura
**Regra:** Em qualquer lista covered/uncovered, cardinalidades devem fechar com denominador e numerador.  
🟢 CONFIRMADO — testes `tests/unit/coverage`, ADR-018.

### R40: Buyer AEC keyword gate
**Regra:** Contratos classificados AEC se objeto contém keywords de engenharia/construção (lista fixa).  
🟢 CONFIRMADO — `buyer_intel/ranking.py:is_aec`.

## Constantes adicionais (2026-07-17)

| Constante | Valor | Fonte |
|-----------|-------|-------|
| DENOMINADOR_UNIVERSO | 1093 | ADR-018 / seed |
| M1 sessão 2026-07-17 | 116/1093 (10,61%) | ADR-018 verification |
| M2 strict sessão | 0/1093 | ADR-018 verification |
| Sources registry | 11 | `crawl.registry.iter_sources` |
| RULE_PRIORITY acts | 8 regras | official_acts_reconcile |
| systemd services/timers | 25 / 24 | deploy/systemd |

## Fontes de evidência (atualizado)

| Fonte | Tipo | Artefatos |
|-------|------|-----------|
| Código Python | 🟢 | 435 arquivos rastreados, ~179K LOC |
| Migrations SQL | 🟢 | 59 em db/migrations (001–054) |
| Git log | 🟢 | 131 commits desde 2026-07-13 |
| ADRs projeto | 🟢 | ADR-017…022 + legados |
| Testes | 🟢 | 126 arquivos, chaos + unit coverage/registry/workspace |
| DoD sessions | 🟢 | docs/ops/session-* §40–§44 |

## Lacunas 🔴 remanescentes (2026-07-17)

1. M2 operacional strict ainda 0/1093 — meta 95% não atingida (honesto).  
2. M3/M5 completos no backlog do coverage contract.  
3. Win rate / resultados de licitação ainda NOT_READY.  
4. Client Profile como “sole law” documentado; 🟡 aderência 100% de todos os scorers legados a validar.  
5. ComprasGov homologado e TCE PAGO ainda não plenamente ingeridos.
