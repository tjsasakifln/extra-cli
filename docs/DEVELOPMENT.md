# Extra Consultoria — Guia canônico de desenvolvimento

**Path canônico:** `docs/DEVELOPMENT.md`  
**Status:** canônico (DoD §32.1)  
**Precedência em conflito:** `DOD.md` → ADR vigente → código testado → evidência reproduzível.  
**Contrato de entry-points:** `docs/canonical-entry-points.yaml`

Este documento é a **fonte compartilhada** de setup, validação e operação local.  
Arquivos de ferramenta (`CLAUDE.md`, `AGENTS.md`, regras de editor) são **adaptadores finos** e devem apontar para cá — não inventar requisitos paralelos.

---

## 1. Documentos canônicos

| Artefato | Papel |
|----------|--------|
| `DOD.md` | Definition of Done e gates (`LOCAL_READY`, etc.) |
| `README.md` | Visão e onboarding |
| `docs/prd/` | Requisitos de produto |
| `docs/architecture/` + ADRs | Arquitetura e decisões |
| `docs/ops/` + runbooks | Operação e evidências |
| `db/migrations/` | Schema |
| `scripts/` | Código operacional CLI-first |
| `tests/` | Suíte de verificação |
| `squads/extra-dod-roi/` | Campanha ROI / force-next |

**Proibido:** decisões obrigatórias só em chat, memória de agente, prompt oculto ou sessão local.

---

## 2. Comandos canônicos (setup / validação / golden path)

```bash
# Setup local (PostgreSQL de teste exemplo)
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"

# Dependências
pip install -r requirements.txt   # ou poetry/pipenv conforme o repo

# Migrations
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"

# Validação rápida
python3 -m pytest tests/ -q --tb=no -x
ruff check scripts/
python3 -m scripts.ops.source_contract_tests --json

# Golden path (fail-closed — prova técnica de pipeline)
python3 -m scripts.golden_path --dsn "$LOCAL_DATALAKE_DSN"

# Ciclo semanal canônico Extra Construtora (produto consultivo)
# Único entry point operacional semanal — não criar concorrentes.
make extra-weekly
# equivalente:
python3 -m scripts.ops.weekly_cycle --strict
# flags úteis: WEEKLY_FLAGS="--force-collect" | "--skip-collect" | "--lookback-days 7"
#
# Engenharia (não substitui o ciclo de produto; ver PR ARCH-RESET #56):
# make verify
#
# Arquitetura-alvo (1 página): docs/architecture/overview.md
# Campanha: docs/ops/campaigns/ARCH-RESET-2026-07-20/FINAL-REPORT.md

# Coverage / operational outputs (componentes internos)
python3 -m scripts.reports.operational_outputs --dsn "$LOCAL_DATALAKE_DSN" --out output/ops-lists --json
python3 -m scripts.coverage.applicability_matrix --limit-entities 50 --out output/applicability --json

# Campanha DoD ROI
python3 squads/extra-dod-roi/scripts/cli.py status
python3 squads/extra-dod-roi/scripts/cli.py force-next
```

Os pontos de entrada (Claude / Codex-compat / Cursor) **devem** citar: setup → validação → golden path → **extra-weekly**.

---

## 3. Escopo, arquitetura e operação

- **Escopo produto:** `DOD.md` + PRD sharded  
- **Arquitetura:** `docs/architecture/` e ADRs  
- **Operação:** `docs/ops/`, runbooks, timers VPS (após PRE_VPS)  
- **Universo:** `config/target_entities_200km.csv` (1093 entes / 200 km)  
- **Fontes:** `scripts/crawl/registry.py` + `config/source_applicability.yaml`

---

## 4. Regras de verdade (anti falso-verde)

1. Fixture ≠ prova live.  
2. Presença de registro ≠ cobertura operacional.  
3. PR aberta ≠ código integrado.  
4. Teste skipped ≠ aprovado.  
5. Documento descrevendo comando ≠ comando funciona.  
6. Não marcar `LOCAL_READY` / 95% / `PRE_VPS_FINAL_READY` / `VPS_OPERATIONAL` / `PROJECT_DONE` sem evidência no HEAD.

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

- Trabalho de produto: branch de feature / épica — **nunca** commitar produto direto na `main` durante campanha.  
- Push/PR: autoridade `@devops` / gates AIOX.  
- Campanha atual: `epic/advance-30d-local-ready-20260718`.
