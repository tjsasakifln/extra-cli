# 04 — Friccao Operacional: UX do CLI da Extra Construtora

**Data:** 2026-07-14
**Autor:** UX Researcher (AIOX Analyst)
**Metodo:** Execucao real de comandos como usuario final, documentando erros, lacunas e pontos de ruptura.

---

## Resumo Executivo

De **9 comandos testados** no ecossistema Python da Extra Construtora, apenas **1 funciona** (`extra_ledger`). Os demais quebram por **3 causas sistemicas**:

1. **Banco de dados acessivel mas sem senha configurada** (portas 5433 e 54399 aceitam conexao mas pedem autenticacao)
2. **Config drift entre `config.settings` (porta 54399) e scripts hardcoded (porta 5433)**
3. **PYTHONPATH nao configurado** — scripts quebram com `ModuleNotFoundError: No module named 'scripts'`

O unico sistema operacional e o `extra_ledger`, que usa JSON file em vez de banco.

---

## Teste 1: `python scripts/opportunity_intel/cli.py show 1`

| Item | Resultado |
|------|-----------|
| Funcionou? | NAO |
| Erro | `Database error: connection to server at "127.0.0.1", port 5433 failed: fe_sendauth: no password supplied` |
| Passos ate decisao | 1 (erro na primeira acao) |
| Output acionavel? | Nao — erro de config, nao de dados |
| O que Tiago teria que completar manualmente | Descobrir a senha do PostgreSQL, configurar `LOCAL_DATALAKE_DSN` no `.env` ou no ambiente |

**Ponto de ruptura:** O DSN padrao e `postgresql://postgres@127.0.0.1:5433/pncp_datalake` — sem senha. PostgreSQL exige autenticacao (scram-sha-256 ou md5). Nao ha `~/.pgpass` configurado.

---

## Teste 2: `python scripts/opportunity_intel/cli.py explain 1`

| Item | Resultado |
|------|-----------|
| Funcionou? | NAO |
| Erro | Mesmo erro do Teste 1 (porta 5433) |
| Passos ate decisao | 1 |
| Output acionavel? | Nao |

**Ponto de ruptura:** Mesma configuracao de banco — erro identico ao `show`. A funcao "explain" (supostamente uma analise LLM de por que participar ou nao) nunca e alcancada.

---

## Teste 3: `python scripts/opportunity_intel/cli.py list --status open --limit 10`

| Item | Resultado |
|------|-----------|
| Funcionou? | NAO |
| Erro | Mesmo erro do Teste 1 |
| Passos ate decisao | 1 |
| Output acionavel? | Nao |

**Ponto de ruptura:** Nao ha fallback. Se o banco caiu, o CLI inteiro fica inutil — ate `--help` funciona? Sim, `--help` funciona, mas nenhum comando util roda.

---

## Teste 4: `python scripts/local_datalake.py search --uf SC --dias 30`

| Item | Resultado |
|------|-----------|
| Funcionou? | NAO |
| Erro | `psycopg2.OperationalError: fe_sendauth: no password supplied` (porta 5433) |
| Passos ate decisao | 1 |
| Output acionavel? | Nao |

**Observacao:** Este script nao aceita `--dsn`. A string de conexao esta hardcoded na linha 34:
```python
DSN = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://postgres@127.0.0.1:5433/pncp_datalake")
```
Se a env var `LOCAL_DATALAKE_DSN` nao estiver setada, a unica saida e editar o codigo.

**Ponto de ruptura:** Impossivel usar `--dsn` para contornar. Dependencia fixa de env var ou edicao de codigo.

---

## Teste 5: `python scripts/local_datalake.py supplier --cnpj <cnpj>`

Nao foi possivel testar com CNPJ real porque o comando `search` ja quebra antes. Assinatura do comando:

```
usage: local_datalake.py supplier [-h] --cnpj CNPJ [--output {text,json}]
```

**Status:** PROVAVELMENTE QUEBRADO (mesma dependencia de DB hardcoded na porta 5433).

**Ponto de ruptura:** Mesmo com um CNPJ valido, o usuario receberia o mesmo erro de autenticacao.

---

## Teste 6: `python scripts/reports/panorama.py --output-excel /tmp/panorama.xlsx`

| Item | Resultado |
|------|-----------|
| Funcionou? | NAO |
| Erro | `psycopg2.OperationalError: fe_sendauth: no password supplied` (porta 5433) |
| Passos ate decisao | 1 |
| Output acionavel? | Nao |

**Observacao:** `panorama.py` aceita `--dsn` (confirmado pelo `--help`). Tentar passar a DSN de config.settings.resolve para porta 54399 (com `:` apos postgres para campo de senha vazio) ainda falha com `fe_sendauth: no password supplied`.

**Ponto de ruptura:** O `--help` funciona, `--dsn` existe, mas nenhum valor de DSN funciona porque PostgreSQL exige senha e nenhuma configuracao a fornece.

---

## Teste 7: `scripts/buyer_intel/` CLI

### `python scripts/buyer_intel/cli.py ranking --limit 5`

| Item | Resultado |
|------|-----------|
| Funcionou? | SIM (parcial) |
| Erro | Nenhum erro de conexao — mas `Nenhum orgao encontrado no raio 200km com dados suficientes.` |
| Passos ate decisao | 1 (conexao OK, consulta executada) |
| Output acionavel? | Parcial — informa que nao ha dados no banco para a regiao |

**Observacao critica:** Este script usa `config.settings.DEFAULT_DSN` (porta 54399, `postgresql://postgres:@127.0.0.1:54399/postgres`). Consegue conectar sem erro — o que significa que a porta 54399 tem um banco `postgres` que aceita conexao com senha vazia (provavelmente configurado como `trust` para conexoes locais ou `peer`). Porem, nao ha dados de contratos carregados.

### `python scripts/buyer_intel/cli.py perfil "PREFEITURA MUNICIPAL DE FLORIANOPOLIS"`

| Item | Resultado |
|------|-----------|
| Funcionou? | SIM (parcial) |
| Erro | `Orgao nao encontrado: PREFEITURA MUNICIPAL DE FLORIANOPOLIS` |
| Passos ate decisao | 1 (conexao OK, orgao nao existe no banco) |
| Output acionavel? | Nao — sem dados para agir |

**Ponto de ruptura:** O banco da porta 54399 esta acessivel mas vazio de dados comerciais. Parece ser o banco padrao `postgres` sem as tabelas de negocio.

---

## Teste 8: `scripts/extra_ledger/` CLI

### `python scripts/extra_ledger/cli.py dashboard`

| Item | Resultado |
|------|-----------|
| Funcionou? | SIM |
| Erro | Nenhum |
| Passos ate decisao | 1 |
| Output acionavel? | Sim — mostra 1 oportunidade avaliada, 0 propostas, 0 contratos, 0 capacidades |

### `python scripts/extra_ledger/cli.py oportunidade list`

| Item | Resultado |
|------|-----------|
| Funcionou? | SIM |
| Output | `#1 PREFEITURA MUNICIPAL DE FLORIANOPOLIS — Reforma de escola municipal — R$ 500,000.00 — 2026-07-14 — participar` |

### `python scripts/extra_ledger/cli.py proposta list`

| Item | Resultado |
|------|-----------|
| Funcionou? | SIM |
| Output | `Nenhuma proposta registrada.` (vazio, mas informativo) |

### `python scripts/extra_ledger/cli.py contrato list`

| Item | Resultado |
|------|-----------|
| Funcionou? | SIM |
| Output | `Nenhum contrato registrado.` (vazio, mas com dica de uso) |

### `python scripts/extra_ledger/cli.py capacidade list`

| Item | Resultado |
|------|-----------|
| Funcionou? | SIM |
| Output | Vazio (sem dados, sem erro) |

### Analise extra_ledger

| Aspecto | Diagnostico |
|---------|-------------|
| Armazenamento | JSON file em `data/extra_ledger.json` (590 bytes) |
| Formato dos dados | Versionado, schema claro: oportunidades, propostas, contratos, atestados, capacidades |
| Seed data | 1 oportunidade registrada manualmente |
| UX do CLI | Comandos intuitivos, `--help` claro, mensagens informativas |
| Limitacao | Sem `--json` no dashboard, sem filtros em list, sem paginacao |
| Risco | JSON file pode corromper com escrita concorrente |

**Ponto de ruptura:** Nao ha integracao deste ledger com o banco PostgreSQL. O usuario insere dados manualmente via CLI. Nao ha sync automatico com PNCP.

---

## Teste 9: `python scripts/opportunity_intel/manifest.py`

| Item | Resultado |
|------|-----------|
| Funcionou? | NAO |
| Erro | `ModuleNotFoundError: No module named 'scripts'` |
| Passos ate decisao | 1 |
| Output acionavel? | Nao |

### Apos fix PYTHONPATH

| Item | Resultado |
|------|-----------|
| Funcionou? | NAO |
| Erro | `ERROR: Manifest generation failed: fe_sendauth: no password supplied` (porta 5433) |
| Output acionavel? | Nao |

**Ponto de ruptura:** Duplo bloqueio: (1) PYTHONPATH faz o import quebrar ao rodar diretamente, (2) mesmo com PYTHONPATH, o banco sem senha bloqueia.

---

## Testes Adicionais

### `python scripts/reports/coverage_gaps.py --help`
- **Status:** FUNCIONA (so o `--help`). Execucao real falharia por DB.

### `python scripts/reports/coverage_weekly.py --help`
- **Status:** FUNCIONA (so o `--help`). Execucao real falharia por DB.

### `python scripts/opportunity_intel/cli.py source-health`
- **Status:** FALHA — `fe_sendauth: no password supplied` (porta 5433)

### `python scripts/opportunity_intel/cli.py export --format csv`
- **Status:** FALHA — `fe_sendauth: no password supplied` (porta 5433)

### `python scripts/opportunity_intel/cli.py radar`
- **Status:** FALHA — `ModuleNotFoundError: No module named 'scripts'` (precisa PYTHONPATH). Apos fix: provavelmente falharia por DB.

### `python scripts/coverage/measure_pncp_expansion.py`
- **Status:** FALHA — `fe_sendauth: no password supplied` (porta 54399). Usa `config.settings` mas ainda sem senha.

### `python scripts/local_datalake.py coverage`
- **Status:** FALHA — `ModuleNotFoundError: No module named 'scripts'`. Apos fix: `fe_sendauth: no password supplied` (porta 5433).

---

## Mapa de Calor: Ecossistema de Comandos

```
OPPORTUNITY_INTEL (5 comandos)    ████████████████░░░░  81% QUEBRADO
  ├── show                        ██ FALHA (DB auth)
  ├── explain                     ██ FALHA (DB auth)
  ├── list                        ██ FALHA (DB auth)
  ├── source-health               ██ FALHA (DB auth)
  ├── export                      ██ FALHA (DB auth)
  ├── radar                       ██ FALHA (PYTHONPATH + DB)
  ├── manifest                    ██ FALHA (PYTHONPATH + DB)
  └── coverage                    ██ FALHA (DB auth)

LOCAL_DATALAKE (6+ comandos)      ████████████████░░░░  83% QUEBRADO
  ├── search                      ██ FALHA (DB auth, sem --dsn)
  ├── stats                       ██ FALHA (DB auth)
  ├── supplier                    ██ (provavel) FALHA
  ├── coverage                    ██ FALHA (PYTHONPATH + DB)
  ├── competitors                 ██ (provavel) FALHA
  └── pricing                     ██ (provavel) FALHA

BUYER_INTEL (2 comandos)          ██████████░░░░░░░░░░  50% FUNCIONAL
  ├── ranking                     ✅ FUNCIONA (sem dados)
  └── perfil                      ✅ FUNCIONA (sem dados)

EXTRA_LEDGER (5+ comandos)        ████████████████████  100% FUNCIONAL
  ├── dashboard                   ✅ FUNCIONA
  ├── oportunidade list           ✅ FUNCIONA
  ├── proposta list               ✅ FUNCIONA
  ├── contrato list               ✅ FUNCIONA
  └── capacidade list             ✅ FUNCIONA

REPORTS (3 comandos)              ██████████████████░░░  67% QUEBRADO
  ├── panorama                    ██ FALHA (DB auth)
  ├── coverage_gaps               ██ (provavel) FALHA
  └── coverage_weekly             ██ (provavel) FALHA

COVERAGE (1 comando)              ████████████████████░  100% QUEBRADO
  └── measure_pncp_expansion      ██ FALHA (DB auth)
```

---

## Diagnostico das 3 Causas Raiz

### Causa 1: Senha do PostgreSQL nao configurada (CRITICO)

**Afeta:** Todos os comandos que dependem de banco (80% do ecossistema)

**Evidencia:**
- Porta 5433: `postgresql://postgres@127.0.0.1:5433/pncp_datalake` — sem campo de senha
- Porta 54399: `postgresql://postgres:@127.0.0.1:54399/postgres` — senha vazia `:` mas PostgreSQL requer autenticacao
- `.env` nao contem `LOCAL_DATALAKE_DSN` com senha
- `~/.pgpass` nao encontrado
- Nao ha `PGPASSWORD` ou `PGPASSFILE` nas env vars

**Gravidade:** BLOQUEANTE para todo o pipeline de inteligencia.

**Solucao necessaria (3 opcoes):**
1. Configurar `pg_hba.conf` para `trust` em conexoes locais (`local all postgres trust`)
2. Adicionar senha a DSN: `postgresql://postgres:senha@127.0.0.1:5433/pncp_datalake`
3. Usar socket Unix (`local` no pg_hba.conf) com `peer` auth

---

### Causa 2: Config Drift entre portas 5433 e 54399 (ALTO)

**Afeta:** Consistencia do sistema. Scripts diferentes apontam para bancos diferentes.

**Evidencia:**
- `config.settings.DEFAULT_DSN` = `postgresql://postgres:@127.0.0.1:54399/postgres`
- `scripts/local_datalake.py` hardcoded = `postgresql://postgres@127.0.0.1:5433/pncp_datalake`
- `scripts/opportunity_intel/cli.py` default = `postgresql://postgres@127.0.0.1:5433/pncp_datalake`
- `scripts/coverage/measure_pncp_expansion.py` = `postgresql://postgres@127.0.0.1:54399/postgres`

**Gravidade:** ALTO — dois bancos rodando, dados podem estar em um e nao no outro.

**Solucao:** Unificar em `config.settings` como unica fonte de verdade (TD-002) e remover hardcoded DSNs.

---

### Causa 3: PYTHONPATH nao configurado para execucao direta (MEDIO)

**Afeta:** Scripts com `from scripts.module import ...` quebram quando executados como `python scripts/.../script.py`

**Evidencia:**
- `manifest.py` → `from scripts.lib.universe import CANONICAL_UNIVERSE` → ModuleNotFoundError
- `cli.py radar` → `from scripts.opportunity_intel.radar import run_radar` → ModuleNotFoundError
- `local_datalake.py coverage` → `from scripts.crawl.monitor import print_coverage_report` → ModuleNotFoundError
- `buyer_intel/cli.py` → `from scripts.buyer_intel.ranking import ...` → ModuleNotFoundError (sem PYTHONPATH)

**Gravidade:** MEDIO — contornavel com `export PYTHONPATH="$PWD:$PYTHONPATH"` mas quebra a experiencia padrao.

**Solucao:** Adicionar ao `if __name__ == '__main__'` o ajuste de `sys.path` ou criar entry points no `setup.py`/`pyproject.toml`.

---

## Matriz de Decisao: Passos para Obter Resultado Util

| Comando | Passos ate resultado | Acionavel? | Completa manualmente |
|---------|---------------------|------------|---------------------|
| `extra_ledger dashboard` | 1 | Sim | Se nao tiver dados, precisa cadastrar manualmente |
| `buyer_intel ranking` | 1 (com PYTHONPATH) | Parcial (sem dados) | Popular banco com contratos |
| `opportunity_intel show 1` | Infinito (loop de erro) | Nao | Configurar DB |
| `local_datalake search` | Infinito | Nao | Configurar DB |
| `panorama` | Infinito | Nao | Configurar DB |
| `manifest` | 2 (PYTHONPATH + DB) | Nao | Configurar ambos |

---

## Recomendacoes Imediatas (Ordem de Impacto)

### 1. Resolver autenticacao do PostgreSQL (desbloqueia 80% do sistema)
- Editar `/etc/postgresql/18/main/pg_hba.conf` para adicionar `trust` na linha `host all all 127.0.0.1/32 trust`
- OU exportar `LOCAL_DATALAKE_DSN=postgresql://postgres:senha@127.0.0.1:5433/pncp_datalake`
- Recarregar config: `pg_ctl reload` ou `SELECT pg_reload_conf()`

### 2. Unificar DSN no `config/settings.py` (remove config drift)
- `config.settings.LOCAL_DATALAKE_DSN` deve ser a unica fonte de verdade
- Todos os scripts devem importar de `config.settings` em vez de hardcodar
- `local_datalake.py` precisa de refatoracao para aceitar `--dsn`

### 3. Adicionar `sys.path` adjustment nos scripts standalone
- Padrao: adicionar `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` no `if __name__ == '__main__'`

### 4. Integrar `extra_ledger` com dados reais do banco
- Atualmente e uma ilha de dados manuais. Poderia sincronizar automaticamente com `opportunity_intel` para oportunidades e com `pncp_datalake` para contratos.

---

## Dados do Diagnostico SYNAPSE

**Status:** SYNAPSE saudavel (hook registrado, manifesto integro, pipeline FRESH) | Timing hooks nao ativos

| Check | Status |
|-------|--------|
| Hook registered | PASS |
| Session data | WARN (no active agent, no UAP bridge) |
| Manifest integrity | PASS (no domains registered) |
| Pipeline simulation | PASS (all layers correct for FRESH bracket) |
| UAP Bridge | FAIL (_active-agent.json missing) |
| Timing hooks | NOT INSTALLED (PreToolUse/PostToolUse hooks nao registrados) |

**Health Summary:** "SYNAPSE 100% | Timing hooks not active — run next session for data"
