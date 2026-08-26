# Extra Consultoria — Guia canônico de desenvolvimento

**Path canônico:** `docs/DEVELOPMENT.md`  
**Status:** canônico (DoD §32.1)  
**Atualizado:** 2026-08-26
**Precedência em conflito:** `DOD.md` → ADR vigente → código testado → evidência reproduzível.  
**Contrato de entry-points:** `docs/canonical-entry-points.yaml`  
**Onboarding / visão de produto:** `README.md`  
**Hub de docs:** `docs/INDEX.md`

Este documento é a **fonte compartilhada** de setup, validação e operação local.  
Arquivos de ferramenta (`CLAUDE.md`, `AGENTS.md`, regras de editor) são **adaptadores finos** e devem apontar para cá — não inventar requisitos paralelos.

---

## 1. Documentos canônicos

| Artefato | Papel |
|----------|--------|
| `DOD.md` | Definition of Done e gates (`LOCAL_READY`, `VPS_OPERATIONAL`, …) |
| `README.md` | Visão, estado honesto, onboarding |
| `docs/INDEX.md` | Mapa living vs histórico vs evidência |
| `docs/prd/` | Requisitos de produto |
| `docs/architecture/` + ADRs | Arquitetura e decisões |
| `docs/ops/` + runbooks | Operação, campanhas, evidências |
| `docs/GLOSSARY.md` | Termos e contagens que não se misturam |
| `db/migrations/` | Schema |
| `scripts/` | Código operacional CLI-first |
| `specs/` | Spec Kit (capabilities / campanhas) |
| `tests/` | Suíte de verificação |
| `squads/extra-dod-roi/` | Campanha ROI / force-next |
| `tools/dod_controller.py` | Convergência DOD |

**Proibido:** decisões obrigatórias só em chat, memória de agente, prompt oculto ou sessão local.

---

## 2. Comandos canônicos (setup / validação / golden path / weekly)

```bash
# Setup local (PostgreSQL de teste exemplo)
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"

# Dependências
pip install -r requirements.txt

# Migrations
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"

# Validação rápida (modo canônico: sem REQUIRE_REAL_DB)
python3 -m pytest tests/ -q --tb=no -x
ruff check .
python3 -m scripts.ops.source_contract_tests --json

# Testes @pytest.mark.real_db — NUNCA recebem MagicMock (#285)
# Política única (REAL_DB_MOCK_ALLOWED=false sob opt-in):
#   REQUIRE_REAL_DB=1 + DSN explícito (LOCAL_DATALAKE_DSN ou DATABASE_URL):
#     psycopg2 real obrigatório; MagicMock é recusado; ausência de conexão/schema
#     é preflight acionável (DB_UNAVAILABLE / DB_REACHABLE_SCHEMA_MISSING), não skip.
#   Sem opt-in: skip rápido com o reason code nomeado (nunca hang, nunca UndefinedTable tardio).
#   Banco plenamente migrado: DB_READY e os testes reais executam.
# O entrypoint cria um banco local irmão por execução, aplica todas as migrations
# e seeds obrigatórias, valida conexão/ledger/fixtures e executa a seleção duas
# vezes: ordem normal e inversa. O usuário do DSN precisa de CREATEDB.
# `psql` não é requisito: a administração usa o psycopg2 canônico.
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.ops.run_full_suite --real-db-only --repeat 2

# Diagnóstico equivalente dentro de um DSN isolado já migrado/semeado:
# REQUIRE_REAL_DB=1 python3 -m pytest tests/ -m real_db -q --tb=short

# Golden path (fail-closed — prova técnica de pipeline)
python3 -m scripts.golden_path --dsn "$LOCAL_DATALAKE_DSN"
# ou: make golden-path

# Ciclo semanal canônico Extra Construtora (produto consultivo)
# Único entry point operacional semanal — não criar concorrentes.
make extra-weekly
# equivalente:
python3 -m scripts.ops.weekly_cycle --strict
# flags úteis: WEEKLY_FLAGS="--force-collect" | "--skip-collect" | "--lookback-days 7"

# Workspace (facade diária — ADR-017)
python3 -m scripts.workspace today
python3 -m scripts.workspace coverage

# Coverage / operational outputs (componentes internos)
python3 -m scripts.reports.operational_outputs --dsn "$LOCAL_DATALAKE_DSN" --out output/ops-lists --json
python3 -m scripts.coverage.applicability_matrix --limit-entities 50 --out output/applicability --json
python3 -m scripts.coverage.coverage_contract_cli report --format table

# DOD convergence + campanha ROI
python3 tools/dod_controller.py status
python3 tools/dod_controller.py next
python3 squads/extra-dod-roi/scripts/cli.py status
python3 squads/extra-dod-roi/scripts/cli.py force-next
```

Os pontos de entrada (Claude / Codex-compat / Cursor) **devem** citar: setup → validação → golden path → **extra-weekly** → workspace (quando operação diária).

---

## 3. Escopo, arquitetura e operação

- **Escopo produto:** `DOD.md` + PRD sharded  
- **Arquitetura:** `docs/architecture/` e ADRs (028 freshness, 029 full suite, 030 dual coverage)  
- **Operação:** `docs/ops/`, runbooks, `deploy/systemd/`  
- **Universo:** planilha R-0 / seed canônica → **1.093** entes (200 km). CSV auxiliar: `config/target_entities_200km.csv`  
- **Fontes:** `scripts/crawl/registry.py` + `config/source_applicability.yaml`  
- **Host de record:** Netcup RS 2000 · Debian 13 · PostgreSQL 17 · `ssh ec-prod` · `/opt/extra-consultoria`  
  (existência do host **não** implica `VPS_OPERATIONAL` / `LOCAL_READY` / `PROJECT_DONE`)

---

## 4. Regras de verdade (anti falso-verde)

1. Fixture ≠ prova live.  
2. Presença de registro ≠ cobertura operacional.  
3. PR aberta ≠ código integrado.  
4. Teste skipped ≠ aprovado.  
5. Documento descrevendo comando ≠ comando funciona.  
6. Não marcar `LOCAL_READY` / 95% open_tenders / `PRE_VPS_FINAL_READY` / `VPS_OPERATIONAL` / `PROJECT_DONE` sem evidência no HEAD.  
7. Dual `historical_contracts` 100% ≠ cobertura total de produto e ≠ `VPS_OPERATIONAL`.  
8. Contagem ~2.085 (SC amplo) ≠ denominador 1.093.

---

## 5. Adaptadores de ferramenta

| Arquivo | Papel |
|---------|--------|
| `CLAUDE.md` / `.claude/CLAUDE.md` | Adaptador Claude Code → deve referenciar este guia |
| `AGENTS.md` | Adaptador Codex/agentes → referencia este guia |
| regras Cursor | Adaptador editor → referencia este guia |

Remover um adaptador **não** remove requisitos de produto: eles vivem em `DOD.md`, código e testes.

---

## 6. Branch e publicação

- Trabalho de produto: branch de feature / épica — **nunca** commitar produto direto na `main` durante campanha sem processo.  
- Push/PR: autoridade `@devops` / gates AIOX.  
- Specs de campanha: `specs/001-dual-capability-coverage-truth/`, `specs/002-historical-contracts-operational-coverage/`.

## 7. Private assets

Ver [docs/ops/private-assets.md](ops/private-assets.md).  
`EXTRA_TARGET_SPREADSHEET` para a planilha privada (não no git público).

## 8. Campanhas e host (snapshot 2026-07-25 / `main`)

- **Host de record:** Netcup / `ssh ec-prod` / PG 17.  
- **HC:** `HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01` — dual historical_contracts 100%; backfill 3y; **BLOCKED** soak 7d.  
- **Open tenders:** `OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01` — dual open_tenders 100%; weekly timer; **BLOCKED** soak 7d + recall residual.  
- **Recall:** `STRATIFIED-RECALL-SOURCE-RESILIENCE-01` — não claimar 95% sem strata.  
- **Próximo passo vivo:** [docs/ops/NEXT-DEV-STEP.md](ops/NEXT-DEV-STEP.md).  
- **Non-claims:** não declarar `LOCAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE` sem gates + evidência.
