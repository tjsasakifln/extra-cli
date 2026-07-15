# Source Failure Runbook — Extra Consultoria

**Versão:** 1.0 | **Data:** 2026-07-15 | **Autor:** AIOX Master (Orion)

---

## 1. Diagnóstico Rápido

```bash
# Verificar status de todas as fontes
python scripts/opportunity_intel/cli.py source-health

# Verificar freshness
python scripts/freshness_gate.py

# Últimas execuções dos crawlers
systemctl list-timers 'extra-*' --no-pager

# Logs de erro recentes
journalctl -u 'extra-*.service' --since '24 hours ago' -p err
```

---

## 2. Cenários de Falha

### PNCP sem dados novos (>48h)

**Sintomas:** `freshness_gate.py` exit code 2. `source-health` mostra PNCP "stale".

**Diagnóstico:**
```bash
# Testar API diretamente
curl -s "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao?dataInicial=20260701&dataFinal=20260715&uf=SC&pagina=1&tamanhoPagina=10" | python3 -m json.tool | head -20

# Verificar circuit breaker
python3 -c "from scripts.crawl.circuit_breaker import get_breaker; print(get_breaker('pncp').state)"

# Verificar último checkpoint
cat data/intel_pncp_checkpoint.json
```

**Resolução:**
1. Se API offline → aguardar, alerta já disparado
2. Se circuit breaker aberto → reset: `python3 -c "from scripts.crawl.circuit_breaker import get_breaker; get_breaker('pncp').reset()"`
3. Se mudança de schema → ver `docs/operations/pncp-schema-change.md`
4. Se rate limited → reduzir `PNCP_REQUEST_DELAY` temporariamente

---

### Crawler retornando HTTP 200 mas 0 registros

**Sintomas:** `source-health` mostra `COLLECTED_EMPTY`.

**Diagnóstico:**
```bash
# Verificar resposta real
python3 << 'EOF'
import requests
r = requests.get("https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao",
    params={"dataInicial": "20260714", "dataFinal": "20260715", "uf": "SC", "pagina": 1, "tamanhoPagina": 10})
print(f"Status: {r.status_code}")
print(f"Body preview: {r.text[:500]}")
EOF
```

**Resolução:**
1. Verificar se `dataFinal` >= `dataInicial`
2. Verificar se UF = "SC" (não "sc" ou "Santa Catarina")
3. Tentar sem filtro de UF para isolar o problema
4. Se API mudou formato → atualizar parser
5. Se realmente não há dados no período → registrar `NOT_PUBLISHED` (não erro)

---

### Paginação truncada

**Sintomas:** Log mostra `Collected 500/500 (max_pages reached)`. `paginasRestantes` > 0 no último request.

**Diagnóstico:**
```bash
# Contar páginas reais
python3 << 'EOF'
import requests
page, total = 1, None
while True:
    r = requests.get("https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao",
        params={"dataInicial": "20260701", "dataFinal": "20260715", "uf": "SC", "pagina": page, "tamanhoPagina": 50})
    data = r.json()
    if total is None:
        total = data.get("totalRegistros") or data.get("totalPaginas")
        print(f"Total estimado: {total}")
    print(f"Page {page}: {len(data.get('data', []))} records, paginasRestantes={data.get('paginasRestantes')}")
    if data.get('paginasRestantes', 0) == 0 or page > 300:
        break
    page += 1
EOF
```

**Resolução:**
1. Aumentar `PNCP_MAX_PAGES` (atual: 200)
2. Reduzir janela de datas (7 dias → 3 dias)
3. Se `totalRegistros` > 10.000 → quebrar em janelas menores

---

### DOM-SC falha de autenticação

**Sintomas:** `dom_sc_crawler.py` retorna 401.

**Diagnóstico:**
```bash
# Testar credenciais
curl -s -u "$DOM_SC_CPF:$DOM_SC_CNPJ" \
  -H "X-API-Key: $DOM_SC_API_KEY" \
  "https://diariomunicipal.sc.gov.br/?r=remote/list&page=1&count=1"
```

**Resolução:**
1. Verificar `DOM_SC_CPF`, `DOM_SC_CNPJ`, `DOM_SC_API_KEY` no `.env`
2. Credenciais expiram? Solicitar renovação ao DOM-SC
3. Fallback: desabilitar DOM-SC até novas credenciais

---

### Browser (Selenium/Playwright) não inicia

**Sintomas:** `selenium_smoke_test.py` falha. Erro: `chromedriver not found` ou `chrome not found`.

**Diagnóstico:**
```bash
google-chrome --version
chromedriver --version
python3 -c "from selenium import webdriver; print('selenium OK')"
python3 -c "from playwright.sync_api import sync_playwright; print('playwright OK')"
```

**Resolução:**
1. `sudo apt install google-chrome-stable`
2. `pip install selenium chromedriver-binary-auto`
3. Para Playwright: `playwright install chromium`
4. Verificar `--no-sandbox` em container Docker

---

### Disco cheio

**Sintomas:** Qualquer crawler falha com `OSError: [Errno 28] No space left on device`.

**Diagnóstico:**
```bash
df -h /opt/extra-consultoria
du -sh /opt/extra-consultoria/data/*
```

**Resolução:**
1. Limpar logs antigos: `journalctl --vacuum-time=7d`
2. Limpar cache: `python3 -c "from scripts.crawl.enricher import _ibge_cache; _ibge_cache.clear()"`
3. Rodar purge: `python3 scripts/crawl/monitor.py --purge`
4. Se ainda crítico: expandir disco na VPS

---

## 3. Alertas Configurados

| Alerta | Gatilho | Severidade | Ação |
|--------|--------|-----------|------|
| PNCP stale > 48h | freshness_gate exit 2 | CRITICAL | Verificar API, reset breaker |
| Crawler zero anômalo | Média > 0 ∧ atual = 0 | HIGH | Diagnóstico HTTP, parser |
| Disco > 80% | df -h | HIGH | Limpeza de cache/logs |
| DB offline | pg_isready fail | CRITICAL | Restart PostgreSQL |
| Backup falhou | extra-db-backup exit ≠ 0 | HIGH | Verificar Storage Box |
| Migration pending | _migrations count < expected | MEDIUM | Executar migration |

---

## 4. Contatos de Emergência

| Sistema | Contato | Canal |
|---------|---------|-------|
| PNCP API | suporte@pncp.gov.br | Email |
| DOM-SC | suporte@fecam.org.br | Email |
| Hetzner VPS | console.hetzner.com | Painel |
| Storage Box | robot@hetzner.com | Email |

---

*Source Failure Runbook v1.0 — 2026-07-15*
