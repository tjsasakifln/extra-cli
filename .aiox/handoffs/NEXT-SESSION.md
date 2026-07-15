# Handoff — Extra Consultoria (2026-07-15)

**De:** @aiox-master (Orion) → **Para:** próxima sessão
**HEAD:** `2b49be2` (main, pushed)
**Working tree:** limpo (2 untracked: output/readiness/freshness-gate.*)

---

## 1. Ciclos Completados

### CM-08: PNCP API Validation (9a6698a)
- Page size real ≠ docs: contratações max=50, contratos max=500
- UF filter contratos quebrado server-side → post-filtro client-side
- `crawl_contracts()` + `transform_contracts()` + `transform_with_uf_filter()`
- QA: CONCERNS (TST-001: testes unitários pendentes)

### CM-09: ComprasGov V3 Validation (2b49be2)
- API funcional **sem geo-restrição** — 52 SC registros em 6.5 meses
- Crawler completo, zero alterações de código
- QA: PASS

---

## 2. Estado das Fontes

| Fonte | Status | Volume | Blocker |
|-------|--------|--------|---------|
| **PCP** | ✅ Ativa | 1.9k bids SC | Nenhum |
| **ComprasGov V3** | ✅ Validada | 52/6meses SC | Nenhum (ativar no orchestrator) |
| **CIGA CKAN** | ✅ Validada | 30.904/mês SC | Nenhum (578 pacotes) |
| **PNCP Contratos** | 🟡 Crawler pronto | 244k nacional | VPS Brasil |
| **PNCP Editais** | 🟡 Crawler pronto | 1.2k SC/15d | VPS Brasil |
| **DOM-SC** | 🟡 Crawler pronto | ? | Credenciais API v2 |
| **TCE-SC** | ⬜ Pendente | ? | Não validado |
| **DOE-SC** | 🔴 Bloqueado | — | Selenium + certificado digital |
| **Transparência** | 🔴 Bloqueado | — | 295+ portais individuais |
| **Mides BigQuery** | 🔴 Bloqueado | — | Credencial GCP |
| **SC Compras** | 🔴 Bloqueado | — | API instável |

### DOM-SC: SOURCE_BLOCKERS desatualizado
SOURCE_BLOCKERS diz "Portal requer navegação interativa (Selenium)" mas crawler já migrou para REST API v2 (`diariomunicipal.sc.gov.br/?r=remote/list`). Bloqueio real: credenciais (DOM_SC_CPF, DOM_SC_CNPJ, DOM_SC_API_KEY).

---

## 3. Cobertura

- **Geral:** 8% (166/2085) — só PCP
- **Potencial pós-ativação:** ~15-20% com ComprasGov + CIGA + TCE-SC
- **Contratos:** 0 rows (244k disponíveis, bloqueados por VPS)

---

## 4. Ranking Próximo Incremento

| # | Incremento | ROI | Blocker |
|---|-----------|-----|---------|
| **1** | Corrigir SOURCE_BLOCKERS dom_sc | ALTO | Nenhum |
| **2** | Story CM-10: CIGA CKAN (30k/mês) | ALTO | Nenhum |
| **3** | Story CM-11: TCE-SC validação | ALTO | Nenhum |
| **4** | Ativar ComprasGov no orchestrator | ALTO | Nenhum |
| **5** | Validar códigos modalidade PNCP | MÉDIO | Rate limit |
| **6** | Story CM-09: crawl contratos 244k | ALTÍSSIMO | VPS Brasil |

---

## 5. Comandos

```bash
# CIGA CKAN (funciona já!):
python3 -m scripts.crawl.ciga_ckan_crawler --month 12-2025

# ComprasGov (funciona já!):
python3 scripts/crawl/monitor.py --source compras_gov --mode full

# DOM-SC (precisa credenciais):
# export DOM_SC_CPF=... DOM_SC_CNPJ=... DOM_SC_API_KEY=...
python3 scripts/crawl/monitor.py --source dom_sc --mode full

# Conexão DB:
PGPASSWORD=test psql -h 127.0.0.1 -p 5433 -U test -d pncp_datalake
```

---

## 6. UNKNOWN

- Códigos modalidade PNCP exatos que a API aceita (docs divergem da API real)
- Se VPS Brasil resolveria geo-restrição (tudo indica que sim)
- Volume real TCE-SC (não validado)
- Se `/api/pncp` (nova API) tem endpoints equivalentes funcionais

## 7. Classificação: GO_WITH_CONDITIONS

**Condições pendentes:**
1. VPS Brasil → desbloqueia PNCP (maior fonte)
2. Credenciais DOM-SC → ativa cobertura municipal
3. Ativar fontes já validadas (ComprasGov, CIGA) no orchestrator
