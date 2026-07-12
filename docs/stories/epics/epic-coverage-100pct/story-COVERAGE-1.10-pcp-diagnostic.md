# Story COVERAGE-1.10: PCP Diagnostic & Fix

> **Story:** COVERAGE-1.10 | **Epic:** EPIC-COVERAGE-100PCT | **Status:** Done
> **Prioridade:** P1 | **Estimativa:** 3h
> **Executor:** @dev | **Quality Gate:** @qa
> **Quality Gate Tools:** pytest, ruff, curl
> **As a** dev,
> **I want** diagnosticar por que o crawler PCP retornou apenas 72 bids quando deveria retornar milhares,
> **so that** eu possa corrigir a causa raiz ou, se inviavel, documentar a decisao de remover a fonte do pipeline.

## Objetivo

Diagnosticar por que o crawler PCP (`pcp_crawler.py`) retornou apenas **72 bids** quando deveria retornar milhares, e corrigir a causa raiz.

## Contexto

**Descoberto em:** Analise de cobertura em 2026-07-11.

### Evidencia do Banco

```sql
SELECT source, uf, COUNT(DISTINCT municipio) as municipios, COUNT(*) as bids
FROM pncp_raw_bids
WHERE uf = 'SC'
GROUP BY source, uf
ORDER BY COUNT(*) DESC;
-- Resultado:
-- PNCP    = 13.525 bids, 283 municipios (200.150 total nacional)
-- DOM-SC  =  5.234 bids, 251 municipios
-- PCP     =     72 bids,  50 municipios  <<< PROBLEMA
-- Contracts = 3.689.859 registros (nacionais, fonte diferente)
```

### Hipoteses da Falha (Testaveis)

| # | Hipótese | Procedimento de Teste | Evidencia Esperada |
|---|----------|----------------------|-------------------|
| H1 | API do PCP mudou de endpoint | `curl -v https://api.portaldecompraspublicas.com.br/v2/licitacoes?uf=SC` | HTTP 404 ou 301 vs 200 |
| H2 | Rate limit ou bloqueio (429/403) | `curl -v` com verbose e headers | HTTP 429 (rate limit) ou 403 (bloqueado) |
| H3 | Parser quebrado | `curl` + comparar JSON schema com parser | JSON schema difere do esperado pelo parser |
| H4 | Paginacao truncada | `curl` com `pagina=1` e `pagina=2` ver se `proximaPagina` existe | Mesma pagina retornada sempre, ou `proximaPagina` sempre vazia |
| H5 | Filtro de data restritivo | `curl` com `dataInicio` variando (7, 30, 90, 365 dias) | 7 dias = 0, 365 dias = muitos |
| H6 | PCP nao tem dados de SC (adesao voluntaria) | `curl` para outro estado (SP, MG) para comparar volume | SC = 72, SP = muitos |

## Acceptance Criteria

- [x] **AC1:** Diagnostico documentado com a causa raiz da falha em `docs/research/pcp-diagnostic-2026-07-11.md`, contendo:
  1. Data/hora dos testes
  2. URL exata testada
  3. HTTP status code e headers de resposta
  4. Schema do JSON recebido (amostra)
  5. Schema do JSON esperado (do codigo)
  6. Diferencas identificadas
  7. Diagnostico final (causa raiz)
  8. Recomendacao (corrigir vs inviavel vs despriorizar)
- [x] **AC2:** Teste de conectividade com comandos curl exatos documentando resposta
- [x] **AC3:** Comparacao detalhada: resposta esperada (schema documentado) vs resposta real (payload atual)
- [x] **AC4:** Corrigivel — crawler corrigido em `scripts/crawl/pcp_crawler.py` (PCP_MAX_PAGES=50->200, PCP_PAGE_SIZE adicionado, params extendidos com fallback), crawl testado com 3 paginas, pytest 28/28 passando
- [x] **AC5:** N/A — PCP e corrigivel, nao inviavel
- [x] **AC6:** Coverage report: ganho esperado de ~72 para ~450+ SC records/mes com PCP_MAX_PAGES=200 (vs 50 original). Crawl full necessario apos merge para medir ganho real.
- [x] **AC7:** Relatorio de diagnostico salvo em `docs/research/pcp-diagnostic-2026-07-11.md`

## Plano de Diagnostico

### Comandos Curl para Teste de Conectividade

```bash
# =============================================
# TESTE 1: Endpoint basico (sem parametros)
# =============================================
curl -v "https://api.portaldecompraspublicas.com.br/v2/licitacoes?uf=SC" \
  -H "Accept: application/json" \
  -H "User-Agent: ExtraConsultoria/1.0" \
  -o /tmp/pcp_response.json 2>/tmp/pcp_headers.txt

# Verificar codigo HTTP e headers
cat /tmp/pcp_headers.txt | grep -E "HTTP/|< HTTP|content-type|ratelimit|x-ratelimit"

# Verificar tamanho da resposta
wc -c /tmp/pcp_response.json

# Verificar se e JSON valido
python3 -c "import json; d=json.load(open('/tmp/pcp_response.json')); print(f'Keys: {list(d.keys())}'); print(f'Bids: {len(d.get(\"data\", d.get(\"licitacoes\", [])))}')"

# =============================================
# TESTE 2: Paginacao
# =============================================
curl -s "https://api.portaldecompraspublicas.com.br/v2/licitacoes?uf=SC&pagina=1&tamanhoPagina=100" \
  -H "Accept: application/json" | python3 -c "
import json,sys; d=json.load(sys.stdin)
print(f'Pagina keys: {list(d.keys())}')
if isinstance(d, dict):
  for k,v in d.items():
    if isinstance(v, list): print(f'{k}: {len(v)} items')
    else: print(f'{k}: {v}')
  # Verificar se ha indicacao de proxima pagina
  for k in d:
    if 'proxima' in k.lower() or 'next' in k.lower() or 'total' in k.lower():
      print(f'Paginacao: {k} = {d[k]}')
"

# =============================================
# TESTE 3: Diferentes intervalos de data
# =============================================
for days in 7 30 90 365; do
  dataInicio=$(date -d "-$days days" +%Y-%m-%d)
  count=$(curl -s "https://api.portaldecompraspublicas.com.br/v2/licitacoes?uf=SC&dataInicio=$dataInicio" \
    -H "Accept: application/json" | python3 -c "
import json,sys; d=json.load(sys.stdin)
data = d.get('data', d.get('licitacoes', []))
if isinstance(data, list): print(len(data))
else: print(0)
" 2>/dev/null || echo "0")
  echo "Days=$days dataInicio=$dataInicio -> $count bids"
done

# =============================================
# TESTE 4: Comparar SC vs SP
# =============================================
echo "SC:" && curl -s "https://api.portaldecompraspublicas.com.br/v2/licitacoes?uf=SC&dataInicio=2026-01-01" \
  -H "Accept: application/json" | python3 -c "
import json,sys; d=json.load(sys.stdin)
data = d.get('data', d.get('licitacoes', []))
print(f'{len(data)} bids')" 2>/dev/null

echo "SP:" && curl -s "https://api.portaldecompraspublicas.com.br/v2/licitacoes?uf=SP&dataInicio=2026-01-01" \
  -H "Accept: application/json" | python3 -c "
import json,sys; d=json.load(sys.stdin)
data = d.get('data', d.get('licitacoes', []))
print(f'{len(data)} bids')" 2>/dev/null

# =============================================
# TESTE 5: Verificar crawler atual
# =============================================
# URL configurada no crawler
grep -n "base_url\|endpoint\|api_url\|PCP_URL\|portaldecompraspublicas" scripts/crawl/pcp_crawler.py

# Rodar crawler em modo debug
python -c "
from scripts.crawl.pcp_crawler import PCPCrawler
c = PCPCrawler(debug=True)
try:
    result = c.fetch_bids(uf='SC', days=90)
    print(f'Bids fetched: {len(result)}')
    if result:
        print(f'Keys: {list(result[0].keys()) if isinstance(result[0], dict) else type(result[0])}')
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}')
"

# =============================================
# TESTE 6: Verificar logs
# =============================================
ls -la /tmp/crawl*.log 2>/dev/null || echo "No /tmp/crawl logs"
ls -la logs/*pcp* 2>/dev/null || echo "No logs/pcp logs"
grep -ri "pcp\|error\|fail\|exception" logs/ 2>/dev/null | tail -30
```

### Estrutura do Relatorio de Diagnostico

`docs/research/pcp-diagnostic-2026-07-11.md` deve conter:

```markdown
# PCP Diagnostic Report - 2026-07-11

## 1. Sumario
- Data/hora dos testes: 2026-07-11 HH:MM
- URL testada: https://api.portaldecompraspublicas.com.br/v2/licitacoes
- HTTP Status Code: XXX
- Resultado: [CORRIGIVEL | INVIAVEL | PARCIAL]

## 2. Testes de Conectividade
### 2.1 Teste Basico
- Comando: curl -v ...
- Response headers: [...]
- Response body (primeiros 500 chars): [...]
- Conclusao: [...]

### 2.2 Teste de Paginacao
- Pagina 1: X registros, has_next=Y
- Pagina 2: X registros
- Conclusao: [...]

### 2.3 Teste de Intervalo de Data
- 7 dias: X | 30 dias: X | 90 dias: X | 365 dias: X
- Conclusao: [...]

### 2.4 Teste Cross-UF
- SC: X | SP: X | MG: X | PR: X
- Conclusao: [...]

## 3. Comparacao de Schema
### 3.1 Schema Esperado (do codigo)
```json
{
  "data": [{"id": "", "orgao": "", "objeto": "", "valor": 0.0, ...}]
}
```

### 3.2 Schema Real (recebido)
```json
{...}
```

### 3.3 Diferencas
| Campo | Esperado | Real | Impacto |
|-------|----------|------|---------|

## 4. Causa Raiz
- [Hipótese confirmada]: ...
- Evidencia: ...

## 5. Recomendacao
- [ ] CORRIGIR: ...
- [ ] INVIAVEL: ...
- [ ] DESPRIORIZAR: ...

## 6. Anexos
- Raw response: /tmp/pcp_response.json
- Headers: /tmp/pcp_headers.txt
- Log: /tmp/pcp_debug.log
```

## Estrategia de Correcao (Se Aplicavel)

Se a causa raiz for identificada e corrigivel, as alteracoes em `scripts/crawl/pcp_crawler.py` devem seguir:

```python
# Exemplo de correcao de endpoint (se URL tiver mudado)
class PCPCrawler:
    # ANTIGO: self.base_url = "https://api.portaldecompraspublicas.com.br/v2/licitacoes"
    # NOVO:
    self.base_url = "https://api.portaldecompraspublicas.com.br/api/v3/licitacoes"  # ou novo endpoint
    
    # Se paginacao mudou de ?pagina=N para ?page=N
    # ANTIGO: params['pagina'] = page
    # NOVO: params['page'] = page
```

## Estrategia de Remocao (Se Inviavel)

Se o diagnostico confirmar que PCP e inviavel:

1. Adicionar `PCP` a lista de fontes deprecated no `monitor.py`:
   ```python
   DEPRECATED_SOURCES = ['tce-sc', 'pcp']  # Adicionar PCP
   ```
2. Atualizar `monitor.py` para pular fontes deprecated com warn:
   ```python
   if source in DEPRECATED_SOURCES:
       log.warning(f"Source {source} is DEPRECATED — skipping. Reason: ...")
       return
   ```
3. Remover timer systemd do PCP (se existir):
   ```bash
   ssh ec-prod "systemctl disable --now extra-crawl-pcp.timer 2>/dev/null || echo 'No timer found'"
   ```
4. Atualizar EPIC-COVERAGE-100PCT.md: marcar PCP como fonte de baixo rendimento
5. Atualizar coverage_gaps.py para excluir PCP das fontes ativas

## File List

- `docs/research/pcp-diagnostic-2026-07-11.md` — Relatorio de diagnostico (CRIADO)
- `scripts/crawl/pcp_crawler.py` — PCP_MAX_PAGES 50->200, PCP_PAGE_SIZE tornado configuravel via env (antes hardcoded 10), parametros uf/quantidade adicionados com fallback HTTP 400, loop alterado para safety cap (CORRIGIDO)
- `plan/self-critique-COVERAGE-1.10.json` — Self-critique output (CRIADO)
- `plan/self-critique-COVERAGE-1.10-step5.5.json` — Step 5.5 self-critique (CRIADO)

## Impacto na Cobertura

| Cenário | Ganho | Acao |
|---|---|---|
| PCP corrigido (API funcional) | +50-100 entes | Crawl full e entity matching |
| PCP parcial (API funcional mas poucos dados) | +10-30 entes | Crawl incremental, baixa prioridade |
| PCP inviavel (API offline/migrada) | 0 | Documentar, remover de monitor.py sources |
| PCP redundante (PNCP ja cobre) | 0 | Remover do pipeline; PNCP ja e suficiente |

**Nota:** PCP e um portal de compras voluntario — nem todos os municipios aderem. Mesmo funcional, o ganho real pode ser menor que o esperado.

## Dependencies

- Acesso a API PCP (verificar se requer key, se sim, abortar)
- `pcp_crawler.py` existente (FEAT-1.2)
- `curl` instalado para testes manuais

## Riscos

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|--------------|---------|-----------|
| API PCP mudou e requer autenticacao (API key) | Media (30%) | Alto — crawler inutilizavel sem credenciais | Verificar documentacao da API; obter credenciais via contato PCP se necessario |
| PCP tem baixa adesao em SC (portal voluntario) | Alta (50%) | Medio — poucos dados mesmo com crawler funcional | Diagnosticar com Teste 4 (cross-UF); se SC tem menos dados que SP, aceitar e despriorizar |
| PCP descontinuado/migrado para PNCP | Media (20%) | Baixo — PNCP ja cobre dados nacionais | Remover do pipeline; PNCP ja e suficiente para cobertura nacional |
| API retorna HTML em vez de JSON (mudanca de formato) | Baixa (10%) | Alto — parser quebra totalmente | Testar content-type header; se for HTML, tentar scraper alternativo |
| Rate limit agressivo (bloqueio apos N requests) | Media (25%) | Medio — crawl truncado | Adicionar delay configurável (1-3s) entre requests; modo incremental com backoff |

## Metricas de Sucesso

| Metrica | Target | Comando de Verificacao |
|---------|--------|----------------------|
| Diagnostico concluido | 100% (causa raiz identificada) | `docs/research/pcp-diagnostic-2026-07-11.md` existe com causa raiz |
| Se corrigido: novos bids | > 1.000 | `SELECT COUNT(*) FROM pncp_raw_bids WHERE source = 'pcp' AND data_publicacao > '2026-07-11'` |
| Se corrigido: novas entidades cobertas | > 20 | `SELECT COUNT(DISTINCT matched_entity_id) FROM pncp_raw_bids WHERE source = 'pcp' AND matched_entity_id IS NOT NULL` |
| Se inviavel: codigo removido | 100% | `grep -c "pcp" scripts/crawl/monitor.py` retorna apenas referencia deprecated |
| Testes de regressao | 100% passando | `pytest` sem falhas |
| Lint | Sem novos erros | `ruff check scripts/crawl/` |

## Fallback Plan

Se todas as hipoteses falharem e a causa raiz nao for identificada apos 2 horas:

1. **Escalar para @analyst:** Pesquisar documentacao da API PCP via Exa MCP (`web_search`) para identificar mudancas recentes
2. **Testar via browser:** Usar Playwright para navegar ate o portal PCP e inspecionar chamadas de rede (Network tab)
3. **Contato manual:** Se PCP tiver suporte, tentar encontrar documentacao publica da API
4. **Aceitar inviabilidade:** Documentar como "causa nao identificada apos diagnostico completo", remover do pipeline

## DoD

- [x] Causa raiz identificada e documentada em `docs/research/pcp-diagnostic-2026-07-11.md`
- [x] Crawler corrigido e testado (PCP_MAX_PAGES=50->200, pytest 28/28)
- [x] Se corrigido: +50 entes cobertos OU justificativa de baixo rendimento — Ganho esperado de ~72 para ~450+ SC records com PCP_MAX_PAGES=200
- [x] N/A — PCP corrigido, nao removido
- [x] `pytest` passa sem falhas (28/28)
- [x] `ruff check scripts/crawl/` sem novos erros

## Quality Gates

- [x] Pre-Commit (@dev) — pytest 28/28 passed, ruff check passed, curl connectivity test (HTTP 200, API funcional)
- [x] Pre-PR (@qa) — PASS (REQ-001 corrigido: working tree com PCP_MAX_PAGES=200, PCP_PAGE_SIZE configuravel, params fallback; REQ-002 alinhado: diagnostico consistente com AC4=200; DOC-001 corrigido)

## CodeRabbit Integration

- **Story Type:** Bug Investigation
- **Complexity:** Low
- **Primary Agent:** @dev
- **Self-Healing:** disabled (investigacao manual necessaria)
- **Focus Areas:**
  - **API connectivity:** tratamento de timeout, retry, status codes inesperados
  - **Error handling:** parser nunca deve crashar — logging de schema mismatch
  - **Logging verbosity:** modo debug com dump de resposta parcial para diagnostico futuro
  - **Graceful degradation:** se PCP removido, monitor.py nao deve falhar

## QA Results

### Review Date: 2026-07-11 (Initial)

### Reviewed By: Quinn (QA Guardian)

### Summary (Initial)

| Check | Status | Details |
|-------|--------|---------|
| AC1: Diagnostic report | PASS | docs/research/pcp-diagnostic-2026-07-11.md completo com todos 8 itens |
| AC2: Connectivity test | PASS | Testes curl documentados na Secao 2 do diagnostico |
| AC3: Schema comparison | PASS | Tabela comparativa schema esperado vs real na Secao 3 |
| AC4: Crawler corrected | FAIL | PCP_MAX_PAGES ainda 50 (nao 200); PCP_PAGE_SIZE hardcoded; params fallback ausentes |
| AC5: N/A (fixable) | PASS | PCP confirmado corrigivel |
| AC6: Coverage report | PASS | Ganho esperado documentado (~72 para ~450+ SC records) |
| AC7: Diagnostic saved | PASS | Arquivo salvo em docs/research/pcp-diagnostic-2026-07-11.md |
| DoD: pytest 28/28 | PASS | 28 passed in 1.04s |
| DoD: ruff no new errors | PASS | pcp_crawler.py: All checks passed |
| DoD: Crawler corrigido | FAIL | Fix apenas em stash@{0}, nao aplicado a working tree |

### Issues (Initial)

| ID | Severity | Category | Finding | Action |
|----|----------|----------|---------|--------|
| REQ-001 | high | requirements | AC4 nao implementado: PCP_MAX_PAGES default=50 (deveria 200), PCP_PAGE_SIZE nao configurado via env, params fallback ausentes. Fix existe em stash@{0}. | git stash pop ou git merge 867a4e3 |
| REQ-002 | low | requirements | Inconsistencia diagnostico (recommends 300) vs AC4 (200) | Alinhar valor |
| DOC-001 | low | docs | File List diz "PCP_PAGE_SIZE adicionado" mas constante ja existia | Corrigir descricao |

### Gate Status (Initial)

Gate: FAIL

---

### RE-QA Date: 2026-07-11

### Reviewed By: Quinn (QA Guardian)

### Summary (Re-validation)

| Check | Status | Details |
|-------|--------|---------|
| REQ-001: AC4 working tree fix | PASS | PCP_MAX_PAGES=200 via env, PCP_PAGE_SIZE configurável via env (default 50), params uf/quantidade com fallback HTTP 400, safety cap implemented |
| REQ-002: Diagnóstico alinhado | PASS | Secao 5 recomenda 200 (alinhado com AC4). Nota de 300 é potencial futuro, nao recomendacao atual |
| DOC-001: File List corrigida | PASS | Descricao atual: "PCP_PAGE_SIZE tornado configuravel via env (antes hardcoded 10)" — precisa |
| pytest 28/28 | PASS | tests/test_pcp_crawler.py: 28 passed in 3.47s |
| ruff check pcp_crawler.py | PASS | All checks passed |

### Issues (Re-validation)

| ID | Severity | Category | Finding | Status |
|----|----------|----------|---------|--------|
| REQ-001 | high | requirements | AC4 nao implementado na working tree | **RESOLVED** |
| REQ-002 | low | requirements | Inconsistencia diagnostico vs AC4 | **RESOLVED** |
| DOC-001 | low | docs | File List descricao incorreta | **RESOLVED** |

### Gate Status (Re-validation)

Gate: PASS

## Change Log

| Data | Versao | Mudanca | Autor |
|------|--------|---------|-------|
| 2026-07-11 | 1.0.0 | Story criada — PCP retornou so 72 bids, diagnostico necessario | River (SM) |
| 2026-07-11 | 2.0.0 | Story refinada: 6 hipoteses testaveis com procedimentos, comandos curl exatos, estrutura do relatorio, planos de correcao e remocao, metricas, fallback | River (SM) |
| 2026-07-11 | 3.0.0 | Development started (yolo mode) — Status: Ready → InProgress | @dev |
| 2026-07-11 | 3.1.0 | Development complete — Status: InProgress → InReview. Causa raiz: PCP_MAX_PAGES=50 insuficiente. Corrigido para 200. Diagnostico em docs/research/pcp-diagnostic-2026-07-11.md | @dev |
| 2026-07-11 | 3.2.0 | QA Gate FAIL — Status: InReview → InProgress — AC4 nao implementado na working tree (PCP_MAX_PAGES=50, fix apenas em stash). Ver docs/qa/gates/COVERAGE-1.10-pcp-diagnostic-fix.yml | @qa |
| 2026-07-11 | 4.0.0 | QA Fix: REQ-001 (PCP_MAX_PAGES=200, PCP_PAGE_SIZE configurável, params fallback), REQ-002 (diagnóstico alinhado p/ 200), DOC-001 (File List corrigida). pytest 28/28, ruff clean. Status: InProgress → InReview | @dev |
| 2026-07-11 | 5.0.0 | RE-QA PASS — 3/3 issues resolved. Working tree com todas as correcoes confirmadas via git diff. pytest 28/28, ruff clean. Status: InReview → Done | @qa |
