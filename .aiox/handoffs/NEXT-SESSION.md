# Handoff — Extra Consultoria (2026-07-15)

**De:** @aiox-master (Orion) → **Para:** próxima sessão
**HEAD:** `cc1969a` (main, pushed)
**Working tree:** limpo (+ SOURCE_BLOCKERS fix pendente commit)

---

## 1. Ciclos Completados

### CM-08: PNCP API Validation
- Page size real: contratações max=50, contratos max=500
- UF filter contratos quebrado → post-filtro client-side
- `crawl_contracts()` + `transform_contracts()` + `transform_with_uf_filter()`
- QA: CONCERNS (TST-001), commit: 9a6698a

### CM-09: ComprasGov V3 Validation
- API funcional sem geo-restrição — 52 SC/6meses
- QA: PASS, commit: 2b49be2

---

## 2. Estado das Fontes

| Fonte | Status | Volume | Blocker |
|-------|--------|--------|---------|
| **PCP** | ✅ Ativa | 1.9k SC | Nenhum |
| **ComprasGov V3** | ✅ Validada | 52/6meses SC | Nenhum |
| **CIGA CKAN** | ✅ Validada | 30.904/mês | Nenhum |
| **PNCP Contratos** | 🟡 Pronto | 244k nacional | VPS Brasil |
| **PNCP Editais** | 🟡 Pronto | 1.2k SC/15d | VPS Brasil |
| **DOM-SC** | 🟡 Pronto | ? | Credenciais API v2 |
| **TCE-SC** | ⬜ Pendente | ? | Não validado |
| **DOE-SC** | 🔴 Bloqueado | — | Selenium + certificado |
| **Transparência** | 🔴 Bloqueado | — | 295+ portais |
| **Mides BigQuery** | 🔴 Bloqueado | — | Credencial GCP |
| **SC Compras** | 🔴 Bloqueado | — | API instável |

---

## 3. DOM-SC: Credenciais

**SOURCE_BLOCKERS corrigido** (era "Selenium", agora "Aguardando credenciais API REST v2")

**Como obter:**
- Email: dom@consorciociga.gov.br
- WhatsApp: (48) 98406-1060
- Enviar CNPJ da Extra Consultoria, solicitar acesso à API `?r=remote/list`
- Homologação: domscdev.beta.consorciociga.gov.br

---

## 4. Próximo Incremento

| # | Incremento | ROI | Blocker |
|---|-----------|-----|---------|
| **1** | CM-10: CIGA CKAN 30k/mês | ALTO | Nenhum |
| **2** | Ativar ComprasGov no orchestrator | ALTO | Nenhum |
| **3** | Validar TCE-SC | ALTO | Nenhum |
| **4** | Obter credenciais DOM-SC | ALTO | Email CIGA |
| **5** | Contratos 244k | ALTÍSSIMO | VPS Brasil |

---

## 5. Comandos

```bash
# CIGA CKAN (funciona já):
python3 -m scripts.crawl.ciga_ckan_crawler --all-months

# ComprasGov (funciona já):
python3 scripts/crawl/monitor.py --source compras_gov --mode full

# DOM-SC (após obter credenciais):
export DOM_SC_CPF=... DOM_SC_CNPJ=... DOM_SC_API_KEY=...
python3 scripts/crawl/monitor.py --source dom_sc --mode full

# DB:
PGPASSWORD=test psql -h 127.0.0.1 -p 5433 -U test -d pncp_datalake
```

---

## 6. Classificação: GO_WITH_CONDITIONS

**Condições:**
1. VPS Brasil → desbloqueia PNCP (maior fonte)
2. Credenciais DOM-SC → email dom@consorciociga.gov.br
3. Ativar fontes validadas (ComprasGov, CIGA) no orchestrator
