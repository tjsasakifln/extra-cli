# Handoff pointer — leia primeiro

> **Atual (2026-07-23):** Netcup VPS + snapshot backfill  
> - Humano: [`docs/ops/handoff-2026-07-23-netcup-vps-backfill.md`](../../docs/ops/handoff-2026-07-23-netcup-vps-backfill.md)  
> - Máquina: [`handoff-2026-07-23-netcup-vps-backfill.yaml`](handoff-2026-07-23-netcup-vps-backfill.yaml)  
> - Runbook migração: `docs/ops/vps-backfill-migration.md`  
> - SSH: `ssh ec-prod` (159.195.18.88:2222)  
> - Writer canônico: pilot local PID (contratos 3y) — VPS snapshot 3 337 776 rows; **não** dual-write  

---

# Handoff — Extra Consultoria (2026-07-15 sessão goal)

**De:** @aiox-master (Orion) → **Para:** próxima sessão  
**HEAD:** `70a4755` (main)  
**Working tree:** fix safe_int pendente commit + freshness-gate untracked  
*(histórico abaixo; prevalece o handoff 2026-07-23 para VPS/backfill)*

---

## 1. Descobertas da Sessão

### PNCP NÃO é geo-bloqueado
- Diagnóstico anterior ERRADO. Railway costa leste EUA sempre funcionou.
- API responde do WSL: 0.5s, 49 registros SC/dia, 546 nacional/dia.
- Erro real: `tamanhoPagina=5` < mínimo 10 → HTTP 400. Timeout por rate limit.

### Bug safe_int corrigido
- `modalidade_id` e `esfera_id` vinham como string ("M"=Municipal) → upsert quebrava.
- Adicionado `safe_int()` em `scripts/crawl/common.py`.
- Aplicado em `pncp_crawler_adapter.py` linhas 457, 460, 634.
- **221 registros PNCP fetched mas 0 inseridos** por causa desse bug. Correção aplicada.

### CIGA CKAN é coverage_only
- `transform()` retorna `[]` por design. Não produz bids.
- API CKAN funciona: 578 packages, dados DOM/SC.
- `run_month()` disponível para entity_coverage direto.

### ComprasGov API 404
- `dadosabertos.compras.gov.br` retorna 404 do Azure para endpoints documentados.
- Swagger mostra módulos mas API não está deployed ou rotas diferentes.

---

## 2. Estado Real da Cobertura

| Métrica | Valor |
|----------|-------|
| Entes planilha Extra | 2.085 |
| Dentro raio 200km | 1.093 |
| **Editais — SC total** | **171 / 2.085 = 8,2%** |
| **Editais — dentro 200km** | **34 / 1.093 = 3,1%** |
| **Contratos** | **0%** |
| Bids no banco | 1.976 (todos PCP) |
| Entidades cobertas | 171 (34 no raio) |

---

## 3. Estado das Fontes (Runtime Confirmado)

| Fonte | Status | Evidência | Blocker |
|-------|--------|-----------|---------|
| **PCP** | ✅ Ativa | 1.976 bids, 171 entes | Nenhum |
| **PNCP** | 🟡 Bug fix pendente | API responde, 221 fetched | safe_int corrigido, re-roDar |
| **CIGA CKAN** | 🟡 coverage_only | 578 packages | Implementar run_month() |
| **ComprasGov** | 🔴 API offline | Azure 404 | Aguardar deploy |
| **DOM-SC** | 🟡 Pronto | API REST v2 | Credenciais (dom@consorciociga.gov.br) |
| **TCE-SC** | ⬜ Não validado | — | Validar |
| **DOE-SC** | 🔴 Bloqueado | — | Selenium + certificado |
| **Transparência** | 🔴 Bloqueado | — | 295+ portais |
| **Mides BigQuery** | 🔴 Bloqueado | — | Credencial GCP |
| **SC Compras** | 🔴 Bloqueado | — | API instável |

---

## 4. Ranking Próximas Ações

| # | Ação | ROI | Blocker |
|---|------|-----|---------|
| **1** | Rodar PNCP com safe_int fix | ALTÍSSIMO | Nenhum |
| **2** | Obter credenciais DOM-SC | ALTO | Email CIGA |
| **3** | CIGA CKAN run_month() | MÉDIO | coverage_only |
| **4** | Corrigir CNPJ no PCP crawler | MÉDIO | Nenhum |
| **5** | Provisionar Railway/VPS para PNCP full | ALTO | Setup |
| **6** | Fechar stories administrativas (CM-08, CM-09, CM-06-PCP-fix) | BAIXO | Nenhum |

---

## 5. Comandos

```bash
# PNCP (após safe_int fix):
PNCP_PAGE_SIZE=50 PNCP_READ_TIMEOUT=30 PNCP_REQUEST_DELAY=0.2 \
INGESTION_DATE_RANGE_DAYS=7 \
DATABASE_URL="postgresql://test:test@127.0.0.1:5433/pncp_datalake" \
python3 scripts/crawl/monitor.py --source pncp --mode full

# PCP (funcionando):
DATABASE_URL="postgresql://test:test@127.0.0.1:5433/pncp_datalake" \
python3 scripts/crawl/monitor.py --source pcp --mode full

# DB:
PGPASSWORD=test psql -h 127.0.0.1 -p 5433 -U test -d pncp_datalake

# Cobertura:
python3 scripts/coverage_truth.py
```

---

## 6. Bugs Conhecidos

1. **safe_int** — `modalidade_id` e `esfera_id` quebram upsert (CORRIGIDO, não commitado)
2. **match_method** — sempre vazio no `entity_coverage`
3. **PCP CNPJ** — 100% `orgao_cnpj` NULL (API PCP não retorna CNPJ)
4. **config.settings** — fallback DSN aponta porta 54399 sem senha
5. **freshness_gate** — não detecta dados PCP (só busca source='pncp')

---

## 7. Classificação: GO_WITH_CONDITIONS

**Condições:**
1. Commit + push do safe_int fix (esta sessão)
2. Rodar PNCP crawl com correção → esperado +200 bids SC/dia
3. Credenciais DOM-SC → email dom@consorciociga.gov.br
4. ComprasGov API voltar ao ar → monitorar

**Métrica alvo próxima sessão:** cobertura editais > 15% dentro 200km (vs 3.1% atual)
