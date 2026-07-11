# Domínio — Extra Consultoria

> Gerado pelo Detective em 2026-07-11T21:30:00Z
> doc_level: completo
> Base: commit e9729e1 (EPIC-FEAT-001 + EPIC-TD-001)

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

---

## Fontes de Evidência

| Fonte | Tipo | Artefatos |
|-------|------|-----------|
| Código Python | 🟢 CONFIRMADO | 139 arquivos, 98K LOC |
| Migrations SQL | 🟢 CONFIRMADO | 19 v1 + 5 v2 |
| Git log | 🟢 CONFIRMADO | 20 commits, 3 epics |
| Config YAML | 🟢 CONFIRMADO | 13 setores, 8.8K LOC |
| Systemd units | 🟢 CONFIRMADO | 40 arquivos |
| Docs | 🟡 INFERIDO | nem todos os docs lidos |

---

## Lacunas 🔴

1. **LACUNA** — Não há documentação explícita do modelo de negócio da Extra Consultoria (quem são os clientes, como o serviço é vendido, ticket médio). O sistema sabe gerar propostas mas o contexto comercial está implícito.
2. **LACUNA** — Transição `monitor.py` → `orchestrator.py` não tem decisão documentada. Dois orquestradores coexistem sem critério claro de qual usar.
3. **LACUNA** — Schema real do banco diverge das migrations em 5 pontos críticos. Não há plano de reconciliação documentado.
