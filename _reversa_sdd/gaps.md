# Lacunas — Extra Consultoria

> Gerado pelo Reviewer em 2026-07-11T23:00:00Z
> doc_level: completo
> Severidade: 🔴 crítico / 🟠 moderado / 🟢 cosmético

## Lacunas Críticas 🔴

### GAP-00: Convenção Dupla de Nomenclatura (snake_case vs kebab-case) 🆕
**Severidade:** 🔴 CRÍTICO
**Módulo:** intel
**Descoberto por:** SM (Scrum Master) em 2026-07-11
**Descrição:** Scripts intel existem em DUAS convenções. `intel_pipeline.py` referencia snake_case como canônico. Kebab-case é legado. O Scout e Archaeologist do Reversa analisaram APENAS a versão kebab-case (legado), perdendo:
- `intel_collect.py` (138KB snake_case, v1.5) vs `intel-collect.py` (127KB kebab, analisado) — **11KB de upgrades v1.5 perdidos**
- `intel_llm_gate.py` (13KB) — script S3 do pipeline, NUNCA analisado
- `intel_sector_loader.py` (19KB) — 20+ funções de config setorial, NUNCA analisado
- `intel_pipeline.py` (49KB) — orquestrador real, NUNCA analisado em profundidade
**Impacto:** Todos os artefatos do módulo intel (code-analysis, specs, flowcharts, ADRs) são baseados na versão legada/errada dos scripts.
**Mitigação:** Atualizar intel/design.md com pipeline real (snake_case). Análise profunda de `intel_llm_gate.py` e `intel_sector_loader.py` pendente.
**Fonte:** SM report, `intel_pipeline.py:876-1153` (referencia snake_case)

### GAP-01: Schema Real vs Migrations Divergentes
**Severidade:** 🔴 CRÍTICO
**Módulo:** db
**Descrição:** Schema real do PostgreSQL diverge das migrations v1 em 5 pontos:
- `esfera_id` é TEXT ('F','E','M','D') no banco real, INT nas migrations v1
- `data_publicacao`/`data_abertura`/`data_encerramento` são TIMESTAMPTZ no real, DATE nas migrations
- `enriched_entities` usa `entity_type`/`entity_id`/`data JSONB` — schema completamente diferente da migration 003 (colunas planas)
- 0 views existem no banco real (migrations 009-012 nunca foram aplicadas)
- Extensão `vector` (pgvector) existe no banco real mas não está documentada em nenhuma migration v1
**Impacto:** Impossível recriar o banco a partir das migrations v1. Migrations v2 baseline resolvem parcialmente.
**Mitigação:** Baseline v2 (`001-v2_initial_schema.sql`, 840 linhas, pg_dump --schema-only). Manter `verify-schema-divergence.sh`.
**Fonte:** `DB-AUDIT.md:DT-01`, `migration-rebuild.md:D1-D5`

### GAP-02: Orquestrador Dual
**Severidade:** 🔴 CRÍTICO
**Módulo:** crawl
**Descrição:** `monitor.py` (684 linhas, legado) e `orchestrator.py` (306 linhas, refatorado) coexistem sem critério claro de qual usar. Monitor tem entity matching inline; Orchestrator tem checkpoint TD-5.2 e matching externo.
**Impacto:** Mudanças de bugfix precisam ser aplicadas em dois lugares. Systemd timers referenciam `monitor.py` (não `orchestrator.py`).
**Fonte:** `code-analysis.md:GAP`, `ADR-008`

### GAP-03: Sistema de Checkpoint Dual
**Severidade:** 🔴 CRÍTICO
**Módulo:** crawl
**Descrição:** Dois sistemas de checkpoint coexistem: sync (psycopg2, usado por `orchestrator.py`) e async (Supabase, usado por `bids_crawler.py`). A tabela `ingestion_checkpoints` tem schema diferente entre os dois.
**Impacto:** Checkpoints não são compartilhados entre sistemas. `bids_crawler.py` é dead code — seu sistema de checkpoint deveria ser removido.
**Fonte:** `checkpoint.py:1-448`

## Lacunas Moderadas 🟠

### GAP-04: Framework Transparência sem Dados
**Severidade:** 🟠 MODERADO
**Módulo:** config, crawl
**Descrição:** `transparencia_config.yaml` tem estrutura completa de CSS selectors mas `municipios: {}` está vazio. Os 4 templates (Betha, Ipam, E-gov, Genérico) estão implementados e prontos, mas o mapeamento de qual município usa qual plataforma não foi populado.
**Impacto:** Transparência crawler funciona apenas com os 15 municípios hardcoded no fallback.
**Fonte:** `transparencia_config.yaml:1-61`, `transparencia_crawler.py:_load_entities()`

### GAP-05: SICAF via Playwright — Dependência Frágil
**Severidade:** 🟠 MODERADO
**Módulo:** intel
**Descrição:** Verificação SICAF usa Playwright para automação de navegador com captcha. Mudanças no site do SICAF quebram essa integração sem aviso.
**Impacto:** Pipeline Intel perde verificação cadastral federal. Gate 2 (Cadastral) fica incompleto.
**Fonte:** `intel-enrich.py:collect_sicaf()`

### GAP-06: Cobertura de Testes Insuficiente
**Severidade:** 🟠 MODERADO
**Módulo:** todos
**Descrição:** 17 arquivos de teste para 98K LOC Python — cobertura estimada <30%. Módulos críticos (intel, crawl) têm baixa cobertura.
**Impacto:** Refatorações são arriscadas. Regressões não detectadas até falha em produção.
**Fonte:** `surface.json:test_coverage_estimate`

### GAP-07: ARP/PCA Crawlers Incompatíveis
**Severidade:** 🟠 MODERADO
**Módulo:** crawl
**Descrição:** `pncp_arp_crawler.py` (525 linhas) e `pncp_pca_crawler.py` (472 linhas) são async (httpx), incompatíveis com a interface sync `crawl(mode)`/`transform(records)` usada por monitor.py e orchestrator.py.
**Impacto:** Funcionalidades ARP (Atas de Registro de Preço) e PCA (Plano de Contratação Anual) não estão integradas ao pipeline de ingestão principal.
**Fonte:** `code-analysis.md:crawl`

## Lacunas Cosméticas 🟢

### GAP-08: Helpers Duplicados
**Severidade:** 🟢 COSMÉTICO
**Módulo:** crawl
**Descrição:** `_digits_only`, `_safe_float`, `_parse_date` implementadas em múltiplos crawlers em vez de importar de `common.py`.
**Fonte:** `code-analysis.md:anti-patterns`

### GAP-09: Requirements.txt sem Version Pinning
**Severidade:** 🟢 COSMÉTICO
**Módulo:** config
**Descrição:** Dependências sem versões exatas. `httpx>=0.28.1` em vez de `httpx==0.28.1`.
**Fonte:** `requirements.txt`

### GAP-10: Docs Desatualizados Pós-EPIC-TD-001
**Severidade:** 🟢 COSMÉTICO
**Módulo:** docs
**Descrição:** Documentos de arquitetura e TD podem estar desatualizados após as 32 stories do commit e9729e1.
**Fonte:** Inferido — Mudanças massivas (+93% LOC) sem atualização proporcional de docs.

---

## Resumo

| Severidade | Count | Itens |
|-----------|-------|-------|
| 🔴 Crítico | 1 | **GAP-00** (dual naming snake_case vs kebab) |
| 🟠 Moderado | 0 | — |
| 🟢 Cosmético | 3 | GAP-08, GAP-09, GAP-10 |
| ✅ Resolvido | 3 | GAP-01, GAP-02, GAP-07 |
| 🔜 Em plano | 4 | GAP-03, GAP-04, GAP-05, GAP-06 |
| **Total** | **11** | |

## Resoluções (2026-07-11)

| GAP | Decisão | Status |
|-----|---------|--------|
| GAP-01 (Schema) | Aplicar baseline v2 limpa, abandonar v1 | ✅ Decidido |
| GAP-02 (Orquestrador) | Migrar para orchestrator.py, systemd timers atualizados | ✅ Decidido |
| GAP-03 (Checkpoint dual) | Remover async (bids_crawler = dead code), manter sync | 🔜 Pendente |
| GAP-04 (Transparência) | detect_platform em lote para 295 municípios SC | 🔜 Pendente |
| GAP-05 (SICAF) | Degraded mode existe. Migrar Playwright→Selenium | 🔜 Pendente |
| GAP-06 (Testes) | TDD no ciclo forward | 🔜 Pendente (política) |
| GAP-07 (ARP/PCA) | Async é intencional, executar separado na VPS | ✅ Decidido |
