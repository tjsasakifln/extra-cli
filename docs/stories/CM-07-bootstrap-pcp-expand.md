# CM-07 — Bootstrap Local DB e Expansao de Cobertura PCP

**Epic:** EPIC-COVERAGE-MAX-200KM | **Onda:** 2 — Correcoes de Alto Retorno
**Risk:** STANDARD | **Status:** Ready
**Asymmetric Score:** 72 | **Recall gain estimado:** +5% (35% -> 40%)

---

## Problema Economico

Tres problemas independentes mas convergentes bloqueiam o golden path de ingestao:

**1. DB local PostgreSQL estava offline** (container parado, tmpfs -> dados perdidos).
O bootstrap parcial revelou multiplos problemas: migrations aplicadas apenas em
`extra_test` (7 de 37), `pncp_datalake` vazio (sem tabelas), e seed de entidades SC
falhou por path incorreto (`scripts/db/` vs `db/seed/`) e uso de `python` vs `python3`.

**2. PCP classificado incorretamente como bloqueado.** O dicionario `SOURCE_BLOCKERS`
em `coverage_truth.py` linha 48 lista `"pcp": "Portal requer Selenium + CAPTCHA"`,
mas a API do Portal de Compras Publicas v2 e aberta e funcional (confirmado via
runtime: 55 registros retornados em teste). Isso faz o sistema de metricas reportar
PCP como blocked quando nao deveria — mascarando a cobertura real.

**3. Janela de crawl PCP subotima.** O crawler usa padrao de 30 dias (`mode="full"`).
Expandir para 365 dias aumenta significativamente o numero de entidades SC cobertas,
especialmente orgaos municipais e estaduais que publicam com frequencia menor.

O custo da inacao: DB quebrado bloqueia todas as stories dependentes de banco local,
PCP classificado como blocked distorce metricas de source health, e janela curta
deixa bids SC de orgaos menos frequentes invisiveis.

## Hipotese

Correcoes cirurgicas no bootstrap (path seed, python3), aplicacao de migrations ao
`pncp_datalake`, remocao do bloqueio falso do PCP em `SOURCE_BLOCKERS` e expansao
da janela de crawl para 365 dias restauram o golden path de ingestao, corrigem as
metricas de cobertura e aumentam a cobertura SC via PCP.

---

## Escopo (IN)

1. Aplicar migrations ao banco `pncp_datalake` (identicas as ja aplicadas em `extra_test`)
2. Corrigir `bootstrap_local.sh`: `python` -> `python3`, path seed script `scripts/db/` -> `db/seed/`
3. Executar seed de `sc_public_entities` via `db/seed/seed_sc_entities.py`
4. Remover entrada `'pcp'` do dicionario `SOURCE_BLOCKERS` em `coverage_truth.py`
5. Expandir janela padrao do PCP crawler de 30 para 365 dias (parametro `days=365` no `crawl()`)
6. Rodar PCP crawl completo e ingerir no banco `pncp_datalake`
7. Medir metricas antes/depois: bids SC, entidades cobertas
8. Testes: rodar `pytest tests/ -k pcp` para verificar regression

## Fora de Escopo (OUT)

- Alterar logica de matching/deduplicacao
- Alterar outros crawlers (PNCP, DOM-SC, DOE-SC, etc.)
- Mexer em API PNCP (bloqueada externamente)
- Alterar schema do banco (migrations ja existentes)
- Adicionar novas fontes de dados

---

## Arquivos Provaveis

| Arquivo | Acao |
|---------|------|
| `scripts/coverage_truth.py` | Remover linha 48 `'pcp'` do dicionario `SOURCE_BLOCKERS` |
| `scripts/bootstrap_local.sh` | `python` -> `python3`, path seed `scripts/db/` -> `db/seed/` |
| `scripts/crawl/pcp_crawler.py` | `days` default 30 -> 365 no `crawl()` |
| `supabase/migrations/*` | Aplicar migrations ao banco `pncp_datalake` |
| `db/seed/seed_sc_entities.py` | Executar (ja existe, path correto) |

## Dependencias

- Nenhuma (DB local, PCP API aberta)

---

## Criterios de Aceite

### AC-1: Migrations aplicadas ao pncp_datalake
**Given** banco `pncp_datalake` vazio (sem tabelas)
**When** executo `bootstrap_local.sh` (ou aplico migrations manualmente)
**Then** todas as 20+ tabelas do schema existem em `pncp_datalake`

### AC-2: Bootstrap funcional
**Given** `bootstrap_local.sh` com bugs de path e comando python
**When** corrigido com `python3` e path `db/seed/`
**Then** `bootstrap_local.sh --dry-run` executa 4 passos sem erro

### AC-3: SOURCE_BLOCKERS corrigido
**Given** `SOURCE_BLOCKERS` com entrada `'pcp'` classificando como "Selenium + CAPTCHA"
**When** entrada removida
**Then** `coverage_truth.py` reporta PCP como functional (nao blocked)

### AC-4: PCP crawl com janela expandida
**Given** PCP crawler com `days=365`
**When** executo `python scripts/crawl/pcp_crawler.py` (ou via monitor.py)
**Then** retorna >100 registros (vs 55 com 30 dias)

### AC-5: Cobertura SC mensurada
**Given** bids PCP ingeridos no banco
**When** metricas calculadas
**Then** cobertura SC > 0% medida e documentada

### AC-6: Testes PCP passam
**Given** alteracoes implementadas
**When** executo `pytest tests/ -k pcp`
**Then** todos os testes passam sem regression

---

## Testes

1. **Unit:** `test_bootstrap_dry_run` — `--dry-run` executa 4 steps sem erro
2. **Integration:** `test_pcp_crawl_days` — crawler com days=365 retorna registros
3. **Integration:** `test_coverage_truth_blockers` — PCP nao aparece como blocked
4. **Smoke:** Seed `sc_public_entities` executa e popula tabela

## Evidencias Obrigatorias

- [ ] `SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'` > 20 em `pncp_datalake`
- [ ] `bootstrap_local.sh --dry-run` exit code 0
- [ ] `coverage_truth.py` nao lista PCP em `SOURCE_BLOCKERS`
- [ ] PCP crawl retorna >100 registros com days=365
- [ ] `pytest tests/ -k pcp` — todos PASS

---

## Rollback

```bash
# Restaurar SOURCE_BLOCKERS
git revert <commit para coverage_truth.py>

# Restaurar days default
git revert <commit para pcp_crawler.py>

# Limpar dados PCP ingeridos (se necessario)
TRUNCATE pncp_raw_bids WHERE source = 'pcp';
```

## Comando de Validacao

```bash
# Dry-run bootstrap
./scripts/bootstrap_local.sh --dry-run

# Verificar migrations
psql -h localhost -p 5433 -U test -d pncp_datalake -c "\dt" | wc -l

# Coverage truth sem blocker
python scripts/coverage_truth.py report --radius-km 200 | grep pcp

# PCP crawl expandido
python -c "
from scripts.crawl.pcp_crawler import crawl
records = crawl('full')
print(f'Records with default days: {len(records)}')
"
# (ou via monitor.py)
python scripts/crawl/monitor.py --source pcp --mode full

# Testes
pytest tests/ -k pcp -v
```

---

## Definition of Done

- [ ] AC-1 a AC-6 atendidos
- [ ] Testes PCP passam (`pytest -k pcp`)
- [ ] Metricas antes/depois documentadas
- [ ] Commit atomico com mensagem convencional
- [ ] QA gate aprovado
- [ ] State file AIOX atualizado

---

*CM-07 — River (SM), 2026-07-15*

---

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-07-15 | 1.0.0 | Validated GO (8.0/10) — Status: Draft → Ready. Condicao: alinhar epic (CM-07 escopo vs descricao epic). | @po |
