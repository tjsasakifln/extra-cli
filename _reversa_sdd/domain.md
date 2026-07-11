# Domínio — Extra Consultoria

> Gerado pelo Detective em 2026-07-11T14:00:00Z
> doc_level: completo

---

## Glossário

| Termo | Definição | Fonte |
|-------|-----------|-------|
| **Licitação** | Processo formal de contratação pública. Registrado em `pncp_raw_bids`. | PNCP, DOM-SC, PCP, ComprasGov |
| **Edital** | Documento que define o objeto, regras e condições da licitação. | PNCP |
| **Órgão público** | Entidade publicante (prefeitura, secretaria, autarquia). 2.085 cadastrados em SC. | `sc_public_entities` |
| **Modalidade** | Tipo de licitação: 4=Concorrência, 5=Pregão Eletrônico, 6=Pregão Presencial, 7=Dispensa, 8=Inexigibilidade, etc. | PNCP |
| **Esfera** | Nível de governo: 1=Federal, 2=Estadual, 3=Municipal. | PNCP |
| **CNPJ base (8 dígitos)** | Prefixo de 8 dígitos do CNPJ que identifica a entidade matriz. Usado para entity matching. | BrasilAPI |
| **Raio 200km** | Distância de Florianópolis. Órgãos dentro deste raio são prioridade máxima (cobertura 100%). | `sc_public_entities.raio_200km` |
| **Cobertura** | Percentual de órgãos SC que tiveram pelo menos 1 licitação capturada nos últimos 90 dias. Meta: 100%. | `entity_coverage` |
| **CNAE** | Classificação Nacional de Atividades Econômicas. Usado para filtrar licitações relevantes por setor. | Receita Federal |
| **Setor** | Categoria de negócio com CNAEs, heurísticas e perfis de peso próprios. 13 setores configurados. | `sectors_config.yaml` |
| **Pipeline Intel** | Fluxo de 7 estágios que coleta e analisa licitações para 1 CNPJ alvo, gerando relatório PDF+Excel. | `intel_pipeline.py` |
| **Entity Matching** | Processo de associar uma licitação (`pncp_raw_bids`) a um órgão cadastrado (`sc_public_entities`). Cascade de 3 níveis. | `monitor.py:_match_entities_cascade` |
| **Ingestion Run** | Execução individual de um crawler, registrada em `ingestion_runs` para auditoria. | `monitor.py` |
| **Content Hash** | SHA-256 do conteúdo canonicalizado (objeto+valor+situação). Evita upserts redundantes. | `transformer.py` |
| **Purge** | Limpeza de registros com mais de 400 dias (`INGESTION_PURGE_GRACE_DAYS`). | `purge_rpc` |
| **Gap Fill** | Estratégia de buscar licitações em portais de transparência para órgãos não cobertos pelas fontes principais. | `transparencia_crawler.py` |
| **Zero Noise** | Filosofia: na dúvida, REJECT. Classificação LLM só aprova com alta confiança. Fallback = rejeitar. | `intel_llm_gate.py` |
| **BDI** | Bonificação e Despesas Indiretas. Percentual sobre custo direto que cobre overhead + lucro. Referência: 25% para engenharia. | `bid_simulator.py` |
| **HHI** | Herfindahl-Hirschman Index. Medida de concentração de mercado usada para estimar número de concorrentes. | `bid_simulator.py` |
| **HETZNER** | Provedor de VPS (Nuremberg, Alemanha). Plano CX43 (€15.99/mo, 8GB RAM, 160GB SSD). | `docs/guides/hetzner-supabase-plan.md` |

---

## Regras de Negócio

### R1 — Cobertura 100% raio 200km
🟢 **CONFIRMADO** — `monitor.py:348-414`, `config/settings.py:110-111`

Todos os 2.085 órgãos públicos de SC dentro do raio de 200km de Florianópolis devem ser monitorados. Cobertura abaixo de 100% gera alerta (`report_coverage` retorna exit code 1 se uncovered > 0). Janela de 90 dias (`COVERAGE_WINDOW_DAYS`).

### R2 — Cascade de Entity Matching
🟢 **CONFIRMADO** — `monitor.py:142-341`

Toda licitação ingerida passa por matching em 3 níveis sequenciais:
1. **CNPJ** (score 1.0, confidence "high") — match exato pelo prefixo de 8 dígitos
2. **Nome normalizado + IBGE** (score 1.0, confidence "high") — nome normalizado com constraint de município
3. **Fuzzy** (threshold 0.85, confidence "high"/"medium"/"low") — similaridade de string com candidatos filtrados por IBGE

Bids sem match são marcados `match_method="unmatched"` e aparecem em `v_unmatched_bids`.

### R3 — Dedup por Content Hash
🟢 **CONFIRMADO** — `transformer.py:30-44`, `db/migrations/001:18`

Licitações com mesmo `content_hash` (SHA-256 de objeto+valor+situação canonicalizados) são tratadas como duplicatas. A RPC `upsert_pncp_raw_bids` usa `ON CONFLICT (content_hash) DO UPDATE`.

### R4 — Retenção de 400 dias
🟢 **CONFIRMADO** — `config/settings.py:92`

Registros com mais de 400 dias (`INGESTION_PURGE_GRACE_DAYS`) são removidos pela RPC `purge_old_records()` executada diariamente às 04:00 UTC.

### R5 — Zero Noise na Classificação LLM
🟢 **CONFIRMADO** — `intel_llm_gate.py`, `sectors_config.yaml:2097-2115`

Classificação de editais via LLM adota filosofia "na dúvida, rejeite". Fallback em caso de erro na API = REJECT. Threshold de confiança configurável por setor (default 0.40-0.55). Só passa se o LLM responder "SIM".

### R6 — Classificação Setorial em 2 Camadas
🟢 **CONFIRMADO** — `sectors_config.yaml`

1. **Camada 1 (heurísticas):** Patterns `strong_compat`, `strong_incompat`, `weak_compat` e `cross_sector_exclusions` aplicados ao objeto da licitação
2. **Camada 2 (LLM fallback):** Acionada quando a confiança da Camada 1 fica abaixo de `cnae_gate_threshold`

Cada setor tem seu próprio threshold e padrões independentes.

### R7 — Modalidades Prioritárias por Setor
🟢 **CONFIRMADO** — `sectors_config.yaml`

Cada setor define `priority_modalidades`. Engenharia prioriza [4,5,6,7] (Concorrência, Pregão Eletrônico, Pregão Presencial, Dispensa). Software prioriza [5,4,8] (Pregão, Concorrência, Inexigibilidade).

### R8 — Soft Delete
🟢 **CONFIRMADO** — `db/migrations/001:30,50-51`

Registros nunca são deletados fisicamente em operação normal. Usam `is_active = FALSE` (soft delete). Views e queries filtram `WHERE is_active = TRUE`.

### R9 — Staggered Crawl Schedule
🟢 **CONFIRMADO** — `deploy/systemd/*.timer`

Crawlers têm horários escalonados para evitar sobreposição e rate limiting das APIs:
- PNCP full: 05:00 UTC (diário)
- PNCP inc: 11:00, 17:00, 23:00 UTC
- DOM-SC: 06:00, 14:00, 22:00 UTC
- Purge: 04:00 UTC
- Reports: 07:00-09:00 UTC

`RandomizedDelaySec=300` em todos os timers para evitar picos exatos.

### R10 — Enriquecimento com TTL de 30 dias
🟢 **CONFIRMADO** — `config/settings.py:116`

Entidades enriquecidas via BrasilAPI têm TTL de 30 dias (`ENTITY_ENRICHMENT_TTL_DAYS`). Após esse período, são re-enriquecidas para refletir mudanças cadastrais.

### R11 — 5 Dimensões de Scoring
🟢 **CONFIRMADO** — `sectors_config.yaml` (weight_profile por setor)

Todo edital analisado recebe score em 5 dimensões com pesos configuráveis por setor:
- **HAB** (habilitação): capital mínimo, atestados, certificações
- **FIN** (financeiro): valor do edital vs capital, margem esperada
- **GEO** (geográfico): distância, raio de atuação
- **PRAZO** (timeline): tempo até abertura, compatibilidade com cronograma
- **COMP** (competitivo): número esperado de concorrentes, HHI

### R12 — Timeline Rules por Setor
🟢 **CONFIRMADO** — `sectors_config.yaml` (timeline_rules por setor)

Prazo mínimo para participação varia por faixa de valor e setor:
- Até R$500k: 7-30 dias (depende do setor)
- R$500k-R$2M: 10-60 dias
- Acima de R$2M: 15-90 dias

### R13 — Single-User, Sem Auth
🟢 **CONFIRMADO** — PRD, `config/settings.py`

Sistema single-user (Tiago Sasaki). Acesso direto ao PostgreSQL sem RLS. Sem autenticação, sem RBAC, sem multi-tenancy. Decisão explícita de arquitetura: "Single user, sem REST overhead".

### R14 — Exclusividade CLI
🟢 **CONFIRMADO** — PRD (W1: Won't Have)

Interface web explicitamente excluída do escopo. Toda interação via terminal (SSH no Hetzner ou WSL local). Relatórios em PDF para apresentação ao decisor.

---

## Decisões Extraídas do Git

| Decisão | Commit | Data | Impacto |
|---------|--------|------|---------|
| Migração smartlic.tech → standalone | `ceecf7b` | 2026-07-10 | Remove SaaS multi-tenant, adota PostgreSQL direto |
| Remove Supabase, usa só psycopg2 | `4aa9e4f` | 2026-07-10 | Simplifica stack: sem REST, sem Supabase |
| Sync HTTP em vez de async/ARQ | `352dac5` | 2026-07-10 | Crawlers usam urllib sync. Motivo: "Simples, sem asyncio para cron" |
| PNCP chunking 1-dia com delay 150ms | `c5df622` | 2026-07-10 | Evita 429 Too Many Requests da API PNCP |
| Entity matching com rapidfuzz | `5359cdb` | 2026-07-10 | Substitui CNPJ-only por cascade 3 níveis. Fallback difflib se rapidfuzz indisponível |
| Systemd em vez de Redis/ARQ | `c062f0a` | 2026-07-10 | "Nativo Linux, sem Redis/ARQ" |
| Filtro keywords engenharia no crawler | `352dac5` | 2026-07-10 | Reduz ruído: só coleta licitações com keywords de engenharia civil |
| Template onFailure para webhook | `c150922` | 2026-07-10 | Notificação de falha em qualquer serviço systemd |
| QA gates CONCERNS → Done | `92c458a` | 2026-07-10 | 28 issues documentados, 0 críticos. Todas as 7 stories aprovadas |

---

## Lacunas Identificadas 🔴

| ID | Descrição | Localização | Severidade |
|----|-----------|-------------|------------|
| L1 | AC7 e AC8 do Story 001.3 requerem validação manual com DB real — fuzzy matching não verificado em produção | `story-001.3-entity-name-matching.md` | MÉDIA |
| L2 | 🟡 Cobertura de testes <30% — plano definido: Claude gera suíte completa para crawl/intel/reports/lib | Projeto inteiro | ALTA → planejada |
| L3 | 🟡 SICAF ativado — Playwright será instalado, sanctions.py ativo | `scripts/crawl/sanctions.py` | BAIXA → planejada |
| L4 | 🟡 Dashboard TUI priorizado; Alertas Telegram postergado | PRD (Could Have) | BAIXA → planejada |
| L5 | 🟡 Integração DOE-SC priorizada para próximo ciclo | PRD (Could Have) | MÉDIA → planejada |
| L6 | 🟡 Sazonalidade: heatmap por setor + previsão de volume definidos | PRD (Should Have) | BAIXA → planejada |
| L7 | 🟡 Dashboard completo de health dos crawlers planejado (web ou TUI) | `deploy/systemd/` | MÉDIA → planejada |
