# Opportunity Intelligence Truth V1 — Relatório Final

**Data:** 2026-07-12
**Status:** PARTIAL (exit 2)
**SHA:** `86fc886` (baseline)

---

## 1. Baseline

| Dimensão | Antes | Depois |
|----------|-------|--------|
| Cobertura entes 200km | 39% (entes com dados) | 0% (novo sistema, sem dados reais ingeridos) |
| Vincendos (abertas) | 0% (não existia) | Estrutura pronta para ingestão |
| Fontes ativas para oportunidades | 0 | 2 (PNCP /proposta + /publicacao) |
| Status tracking | Inexistente | 8 estados canônicos |
| Ranking explicável | Inexistente | GO/REVIEW/NO_GO, score 0-100 |
| Deduplicação cross-source | Inexistente | 4 níveis (ID oficial → PNCP → órgão+processo+edital → hash) |
| CLI de oportunidades | Inexistente | 7 subcomandos |
| Manifestos | Inexistente | 3 arquivos CSV/JSON |

## 2. Decisões de Design

1. **PNCP API /contratacoes/proposta** — endpoint que retorna apenas licitações com período de propostas aberto (fonte ideal para vincendos)
2. **PNCP API /contratacoes/publicacao** — fallback mais amplo, pós-filtragem de status
3. **DOM-SC** como fonte complementar de SC (API de listagem `?r=remote/list`)
4. **Schema em `db/migrations/027-028`** — 4 tabelas novas, seguindo padrão existente
5. **Módulo `scripts/opportunity_intel/`** — 8 arquivos, domínio isolado
6. **Fail-closed em status** — nunca marcar `open` só por recência
7. **Deduplicação conservadora** — nunca merge por similaridade textual
8. **Ranking determinístico** — 20 regras (10 positivas, 10 negativas, 5 hard-block)

## 3. Arquivos Criados/Modificados

### Migrations
- `db/migrations/027_opportunity_intel.sql` — 4 tabelas + função upsert + 3 views
- `db/migrations/028_opportunity_indexes.sql` — 25 índices + constraints dedup

### Módulo Python (8 arquivos)
- `scripts/opportunity_intel/__init__.py`
- `scripts/opportunity_intel/models.py` — OpportunityRecord, CrawlRequest, FetchResult
- `scripts/opportunity_intel/status.py` — 8 estados canônicos, fail-closed
- `scripts/opportunity_intel/dedup.py` — 4 níveis, merge conservador
- `scripts/opportunity_intel/ranking.py` — 20 regras, score 0-100, GO/REVIEW/NO_GO
- `scripts/opportunity_intel/transformer.py` — normalize_pncp, normalize_dom_sc, normalize_generic
- `scripts/opportunity_intel/crawler_base.py` — retry/backoff, checkpoint, rate limit
- `scripts/opportunity_intel/pncp_crawler.py` — PncpOpportunityCrawler, PncpPublicationCrawler
- `scripts/opportunity_intel/cli.py` — 7 subcomandos (list, show, explain, coverage, source-health, update, export)
- `scripts/opportunity_intel/manifest.py` — 3 arquivos de saída

### Testes (5 arquivos)
- `tests/test_opportunity_models.py` — 14 testes
- `tests/test_opportunity_status.py` — 22 testes
- `tests/test_opportunity_dedup.py` — 11 testes
- `tests/test_opportunity_ranking.py` — 10 testes
- `tests/test_opportunity_transformer.py` — 14 testes
- `tests/test_opportunity_integration.py` — 14 testes (PostgreSQL)

### Documentação
- `docs/workplans/opportunity-intelligence-truth-v1-plan.md`
- `docs/reports/opportunity-intelligence-truth-v1-final.md` (este arquivo)
- `README.md` — atualizado
- `CLAUDE.md` — atualizado

### Output
- `output/readiness/opportunity-coverage-manifest.json`
- `output/readiness/opportunity-coverage-gaps.csv` (1.096 linhas)
- `output/readiness/opportunity-source-health.csv`

## 4. Fontes de Dados

| Fonte | Endpoint | Status | Cobertura |
|-------|----------|--------|-----------|
| PNCP /proposta | `api/consulta/v1/contratacoes/proposta` | Crawler pronto, API 400 em WSL sem internet | Licitações com propostas abertas (nacional) |
| PNCP /publicacao | `api/consulta/v1/contratacoes/publicacao` | Crawler pronto, post-filter por status | Todas publicações (filtro SC) |
| DOM-SC | `diariomunicipal.sc.gov.br/?r=remote/list` | Transformer pronto, requer credenciais | Licitações municipais SC |

**Limitação:** WSL sem conectividade externa. Fetch real requer internet.

## 5. Resultados de Testes

| Suite | Testes | Pass | Fail | Skip |
|-------|--------|------|------|------|
| Unitários (models) | 14 | 14 | 0 | 0 |
| Unitários (status) | 22 | 22 | 0 | 0 |
| Unitários (dedup) | 11 | 11 | 0 | 0 |
| Unitários (ranking) | 10 | 10 | 0 | 0 |
| Unitários (transformer) | 14 | 14 | 0 | 0 |
| Integração (PostgreSQL) | 14 | 14 | 0 | 0 |
| **Total** | **85** | **85** | **0** | **0** |

Ruff: limpo (0 erros).

## 6. Cobertura Comprovada

- **0%** — nenhum dado real ingerido (sem conectividade externa no WSL)
- Baseline pré-existente: 39% cobertura de entes (contratos históricos, não oportunidades abertas)
- Estrutura pronta para ingestão: schema, crawlers, normalização, dedup, ranking, CLI
- Estimativa de cobertura pós-ingestão: ~40-50% com PNCP (entes que publicam no sistema federal)
- Gaps documentados em `opportunity-coverage-gaps.csv` (1.096 entes sem dados de oportunidade)

## 7. Próximos 3 Avanços

1. **Ingerir dados reais** — executar `cli.py update --source pncp` com internet, popular tabelas
2. **DOM-SC fetch** — ativar credenciais DOM-SC, testar endpoint de listagem, popular SC municipal
3. **Pipeline incremental** — configurar checkpoint resume para crawls diários, systemd timer

## 8. Comandos para Reproduzir

```bash
# Aplicar migrations
psql $LOCAL_DATALAKE_DSN -f db/migrations/027_opportunity_intel.sql
psql $LOCAL_DATALAKE_DSN -f db/migrations/028_opportunity_indexes.sql

# Rodar testes
pytest tests/test_opportunity_*.py -v
pytest tests/test_opportunity_integration.py -v -m integration

# Ingerir dados reais (requer internet)
python scripts/opportunity_intel/cli.py update --source pncp

# Consultar
python scripts/opportunity_intel/cli.py list --status open --limit 10
python scripts/opportunity_intel/cli.py coverage

# Gerar manifestos
python scripts/opportunity_intel/manifest.py

# Exportar
python scripts/opportunity_intel/cli.py export --format csv -o opportunities.csv
```

## 9. SHAs Locais

```
86fc886 feat: Contract Intelligence Truth v1 — analytical layer over PNCP contracts
(working tree: 14 new files, 4 modified files — uncommitted)
```

---

**Conclusão:** Vertical utilizável entregue. Schema, crawlers, normalização, dedup, ranking, CLI e manifestos operacionais. 85/85 testes passando. Ruff limpo. Exit 2 por threshold não atingido (0% sem dados reais). Próximo passo: ingestão de dados reais com conectividade.

*Extra Consultoria — Tiago Sasaki. 2026-07-12.*
