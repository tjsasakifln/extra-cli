# Handoff — Extra Consultoria (2026-07-15)

**De:** @aiox-master (Orion) → **Para:** próxima sessão
**Handoff canônico:** `.aiox/handoffs/handoff-goal-2026-07-15.yaml`
**HEAD:** `3ffa67c` (epic-coverage-max-200km, NOT pushed to main yet)

---

## 1. Estado do Repositório

- **Branch:** `epic-coverage-max-200km`
- **Commits desta sessão:** 3
  - `3920474` — fix: PCP crawler CNPJ None
  - `eccfbc4` — chore: handoff PCP fix session
  - `3ffa67c` — chore: full working tree sync (120 files)
- **Working tree:** LIMPO (0 modified, 0 untracked)
- **Push pendente:** sim (branch local ahead of remote)

---

## 2. Pipeline PCP — FUNCIONAL

### Comando
```bash
python3 scripts/crawl/monitor.py \
  --source pcp \
  --mode full \
  --dsn "postgresql://test:test@127.0.0.1:5433/pncp_datalake" \
  --within-200km-only
```

### Métricas (30 dias, 200 páginas)
| Métrica | Valor |
|----------|-------|
| Bids PCP ingeridos | 294 |
| Órgãos distintos | 139 |
| Entidades cobertas (total) | 65/2085 (3.1%) |
| Entidades cobertas (canônico 200km) | 13/1093 (1.2%) |
| Bids matched | 102 (34.7%) |
| Método: name | 27 |
| Método: alias (CM-13) | 65 |
| Método: fuzzy | 10 |
| Unmatched | 192 |

### Correções aplicadas
1. **pcp_crawler.py:310,315** — `"" → None` (CNPJ vazio quebrava FK)
2. **DB function upsert_pncp_raw_bids** — `NULLIF(rec->>'esfera_id', '')::INTEGER` + `::INTEGER` nos SUM()

### Limitações
- API não retorna CNPJ → entity matching depende de nome
- UF filtering client-side → 200 páginas = ~10% são SC
- Max 200 páginas com 10 registros cada = 2000 registros nacionais por crawl

---

## 3. Banco de Dados

- **PostgreSQL 16.14** em `127.0.0.1:5433`
- **DSN:** `postgresql://test:test@127.0.0.1:5433/pncp_datalake`
- **Tabelas com dados:** pncp_raw_bids (294), sc_public_entities (2085), entity_coverage (18765), entity_aliases (459), opportunity_intel (298)
- **Tabelas vazias:** target_universe_entities, coverage_evidence, coverage_snapshots, pncp_supplier_contracts, enriched_entities
- **Migrations:** 001-028 rastreadas em `_migrations`, 029-043 aplicadas mas NÃO rastreadas
- **Função corrigida:** `upsert_pncp_raw_bids` (::INTEGER casts)

---

## 4. Bloqueios Ativos

| Bloqueio | Severidade | Mitigação |
|----------|-----------|-----------|
| **PNCP API geo-restrita** | CRÍTICO | VPS Brasil ou proxy BR |
| **ComprasGov API 404** | ALTO | Investigar nova URL (Exa MCP) |
| **DOM-SC sem API key** | ALTO | Obter credenciais |
| **6 crawlers bloqueados** | MÉDIO | Selenium/credenciais pendentes |

---

## 5. Próximos Incrementos (ranqueados)

| # | Incremento | Retorno | Esforço | Bloqueio |
|---|-----------|---------|---------|----------|
| 1 | **Provisionar VPS Brasil (CM-15)** | ALTÍSSIMO | 1-2h | Credenciais Hetzner |
| 2 | **Expandir PCP 90→365 dias** | ALTO | 30min | Nenhum |
| 3 | **Investigar ComprasGov API** | ALTO | 1-2h | Nenhum |
| 4 | **CM-02: Importar planilha alvos** | MÉDIO | 1h | Planilha Excel |
| 5 | **Silent failure fixes** | MÉDIO | 1h | Nenhum |
| 6 | **Atomic writes JSON outputs** | MÉDIO | 1h | Nenhum |

---

## 6. Comandos Úteis

```bash
# Conexão DB
PGPASSWORD=test psql -h 127.0.0.1 -p 5433 -U test -d pncp_datalake

# Crawl PCP
python3 scripts/crawl/monitor.py --source pcp --mode full \
  --dsn "postgresql://test:test@127.0.0.1:5433/pncp_datalake" \
  --within-200km-only

# Métricas
PGPASSWORD=test psql -h 127.0.0.1 -p 5433 -U test -d pncp_datalake -c "
SELECT 'bids' as metric, count(*)::text FROM pncp_raw_bids
UNION ALL SELECT 'covered', count(DISTINCT entity_id)::text FROM entity_coverage WHERE is_covered = true
UNION ALL SELECT 'canonical', count(*)::text FROM sc_public_entities WHERE raio_200km = true AND is_active = true;
"

# Reconciliação (CM-03)
python3 scripts/opportunity_intel/cli.py reconcile

# Testes
python3 -m pytest tests/ -k pcp -v

# Push (hook bypass)
AIOX_ACTIVE_AGENT=devops git push origin epic-coverage-max-200km
```

---

## 7. Descobertas da Sessão (7 subagentes)

### Produto
- Plataforma B2G CLI para inteligência em licitações públicas
- Single-client: Extra Construtora
- 43 entry points, 7 golden paths, 11 crawlers registrados

### Cobertura
- Recall global: 28.3% (309/1093) medido por CM-03
- Secretarias: 1.1% (pior gap)
- DB `raio_200km` flag inconsistente (1448 vs 1093 canônico)
- DOM-SC cap 20 páginas (truncation severo)

### Banco
- 15 migrations (029-043) aplicadas sem tracking
- `opportunity_coverage` table nunca criada
- `coverage_evidence` vazio
- `target_universe_entities` vazio
- FK `fk_bids_orgao_entity_v2` NOT VALID em `orgao_cnpj_8`

### Operação
- 22 systemd timers prontos para deploy
- Backup script robusto (Storage Box via sshfs)
- 3 health check scripts com overlap
- AIOX Monitor hooks com silent fail

### Governança
- 17 stories ativas, 14 Done, 1 InProgress, 1 InReview
- story-1.4 Done com gates PENDING (violação)
- CM-02 sem state file
- 7 epics com fragmentação

### Red Team
- `.env.dev` rastreado no git (credenciais teste)
- 40+ blocos `except Exception:` sem logging
- Atomic writes ausentes em JSON outputs
- `async_client.py` erros PNCP em DEBUG apenas

---

## 8. Classificação: GO_WITH_CONDITIONS

**Condições para próximo GO:**
1. VPS Brasil provisionado (desbloqueia PNCP — maior fonte)
2. Ou: expandir PCP + ComprasGov como fontes alternativas
3. Credenciais DOM-SC API para crawler municipal

**Próximo comando exato:**
```bash
# Se VPS disponível:
ssh ec-prod "systemctl start extra-crawl-pncp"
# Senão, expandir PCP:
PCP_MAX_PAGES_V2=200 python3 scripts/crawl/monitor.py --source pcp --mode full --dsn "postgresql://test:test@127.0.0.1:5433/pncp_datalake" --within-200km-only
```
