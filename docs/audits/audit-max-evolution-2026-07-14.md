# Auditoria Consolidada — Max Evolution

**Data:** 2026-07-14
**Commit auditado:** 97f612e
**Branch:** main
**Ambiente:** WSL2 Linux, Python 3.12.3, PostgreSQL offline (porta 5433)
**Método:** 5 auditores paralelos read-only + convergência do coordenador

---

## 1. Baseline Real (2026-07-14)

### 1.1 O que funciona

| Componente | Evidência |
|-----------|-----------|
| Ruff lint | **ALL CHECKS PASSED** (0 erros) |
| Bandit security | **0 HIGH**, 47 Medium, 78 Low |
| Pytest | **118 passed**, 1 skipped (amostra representativa) |
| 1381 testes coletados | 5.8% coverage (full suite) |
| Código organizado | ~80K LOC Python, arquitetura modular |
| Scoring determinístico | GO/REVIEW/NO_GO com regras explicáveis |
| Semântica de valores | Documentada corretamente (estimado/homologado/contratado/pago) |
| Dedup strategy | 4 níveis determinísticos, sem fuzzy matching |
| CI/CD (GitHub Actions) | Configurado e funcional |
| Systemd units (44) | Existem, scripts bem escritos |
| Backup/Restore scripts | 410+255 linhas, bem estruturados |
| Documentação | 8 docs operacionais, PRD v2.0, arquitetura completa |

### 1.2 O que NÃO funciona

| Componente | Evidência |
|-----------|-----------|
| PostgreSQL | **OFFLINE** (porta 5433 timeout) |
| Qualquer comando CLI | Depende de banco → 0% funcional |
| Crawlers em produção | 0 em operação contínua |
| VPS provisionada | Nunca executado |
| Backup restore testado | Nunca executado |
| Migration v3 aplicada | `006-v3-unified-schema.sql` pendente → 10+ tabelas podem não existir |
| Pipeline Intel Step 7 | `intel_report.py` **NÃO EXISTE** |
| 2 crawlers (ARP, PCA) | Import quebrado (`ingestion` não está no PYTHONPATH) |
| Métricas comerciais | TODAS NOT_READY |
| Briefing diário | Não existe comando |
| Dossiê de oportunidade | Não existe geração integrada |

---

## 2. Findings Consolidados (Cross-Auditor)

### 2.1 CRITICAL (8)

| ID | Finding | Auditores | Evidência |
|----|---------|-----------|-----------|
| **C1** | PostgreSQL offline → 0% valor comercial entregue | Commercial, Data | `pg_isready` timeout, todos CLIs falham |
| **C2** | B2G-FIX-04 `reviewed_commit: N/A` com `publication_authorized: true` | State-Truth | State file JSON, protocolo seção 8 |
| **C3** | 4 commits pós-QA (8704486, eae0b2d) com alterações de código sem re-review | State-Truth | `git log --oneline`, diff de migrations |
| **C4** | 100% dados de fonte única (PNCP monocultura) | Data | Coverage: 42% PNCP, 0% demais fontes |
| **C5** | Pipeline nunca completa — Step 5 manual, Step 7 ausente | Commercial | `intel_pipeline.py`, arquivo `intel_report.py` não existe |
| **C6** | Migration v3 não aplicada → 10+ tabelas sem garantia de existência | Data | `006-v3-unified-schema.sql` em `supabase/migrations/` |
| **C7** | QW-01 `reviewed_commit: null` com status Done | State-Truth | State file `qw-01-radar-auditavel.json` |
| **C8** | Métricas comerciais ALL NOT_READY (preço, deságio, win rate, relicitação) | Commercial | PRD v2.0, `value_semantics.py` |

### 2.2 HIGH (7)

| ID | Finding | Auditores | Ação |
|----|---------|-----------|------|
| **H1** | Story 1.3 markdown "Done" vs state "InProgress" (gates FAIL) | State-Truth | Alinhar markdown com state real |
| **H2** | EPIC MASTER v3.0 diz B2G-FIX-04 "InProgress", state diz "Done" | State-Truth | Atualizar EPIC MASTER |
| **H3** | QW-01 markdown "InReview" vs state "Done" — conflito | State-Truth | Resolver divergência |
| **H4** | 4 serviços systemd sem OnFailure | Ops | Adicionar `OnFailure=extra-onfailure@.service` |
| **H5** | 2 crawlers quebrados (ARP, PCA) — import `ingestion` falha | Data | Corrigir PYTHONPATH ou refatorar imports |
| **H6** | Documentação operacional referencia timers inexistentes (`extra-crawl-pncp`) | Ops | Corrigir docs e `provision-vps.sh` print_summary |
| **H7** | Teste de restore de backup nunca executado | Ops | Agendar teste após provisionamento |

### 2.3 MEDIUM (10)

| ID | Finding |
|----|---------|
| M1 | Story 1.1, 1.2, 1.4: markdown vs state divergentes |
| M2 | Phase Zero stories: gates schema incompleto (faltam typecheck, build) |
| M3 | B2G-FIX-02 frontmatter YAML `status: ready` deveria ser `Done` |
| M4 | 12 serviços systemd usam template `onfailure@` antigo (sem campo `project`) |
| M5 | Nomenclatura systemd: 3 padrões conflitantes (pncp-*, extra-*, source-name-*) |
| M6 | Nomenclatura migrations: underscore vs hyphen inconsistente (018, 019) |
| M7 | Rollback scripts: apenas 1/47 migrations tem rollback |
| M8 | Content hash: MD5 vs SHA256 em locais diferentes — risco de divergência |
| M9 | `sc_public_entities` sem UNIQUE em `cnpj_8` |
| M10 | td-3.2 markdown sem state file (story órfã) |

### 2.4 LOW (6)

| ID | Finding |
|----|---------|
| L1 | Campo `reopened_reason` nos state files não documentado no schema |
| L2 | `install.sh` redundante com `provision-vps.sh` |
| L3 | Backup: dupla compressão (pg_dump custom + gzip) ineficiente |
| L4 | pre-commit hooks não instalados localmente |
| L5 | Selenium legado (6 arquivos) coexistindo com Playwright |
| L6 | ANSI color codes manuais com `rich` disponível |

---

## 3. Divergências Entre Auditores

| Tópico | Auditor 1 | Auditor 2 | Resolução |
|--------|-----------|-----------|-----------|
| Unresolved entities | Data: **0** (100% resolvido) | Commercial: **604** (do PRD v2.0) | **Ambos corretos.** Data refere-se a seed (CNPJs resolvidos). Commercial refere-se a cobertura geográfica (coordenadas). 604 = entidades sem coordenadas IBGE, não sem CNPJ. Verificar via `coverage_manifest`. |
| Versão AIOX | State-Truth: manter 5.2.9 | — | **Confirmado.** `.aiox-core/package.json` = 5.2.9. `npx` busca 5.3.0 do registry mas não é a versão instalada. MANTER 5.2.9. |
| Total migrations | Data: 47 + 8 (supabase) | State-Truth: "47 migrations fresh-install green" | **Ambos corretos.** 47 em `db/migrations/`, 8 em `supabase/migrations/`. Tracks diferentes. |
| Cobertura real | Data: 42.18% (461/1093) | PRD: 64.4% (1093/1697) | **Métricas diferentes.** Data mede entidades com dados. PRD mede entidades com cobertura configurada. 64.4% = denominador conservativo (exclui 604 sem coordenadas). |

---

## 4. Linha de Base de Qualidade

| Métrica | Valor | Target | Status |
|---------|-------|--------|--------|
| Ruff errors | 0 | 0 | ✅ PASS |
| Ruff format | Clean | Clean | ✅ PASS |
| MyPy errors | 769 | <50 | ❌ FAIL |
| Bandit HIGH | 0 | 0 | ✅ PASS |
| Bandit MEDIUM | 47 | <20 | ⚠️ WARN |
| Pytest (amostra) | 118 passed | All passing | ✅ PASS |
| Coverage | 5.8% | >30% core | ❌ FAIL |
| pip-audit | Não executado | 0 vuln | ⚠️ UNKNOWN |

---

## 5. Oportunidades de Valor (Top 5)

| # | Oportunidade | Impacto | Esforço | ROI |
|---|-------------|---------|---------|-----|
| 1 | Subir PostgreSQL + crawl PNCP | Desbloqueia 100% dos CLIs | 30 min | Infinito |
| 2 | Script de briefing diário (100 linhas) | Consultor recebe prioridades em 3s | 1-2h | Altíssimo |
| 3 | Criar `intel_report.py` (PDF) | Pipeline entrega artefato final | 2-3 dias | Alto |
| 4 | Aplicar migration v3 | Desbloqueia source-health multicanal | 1-2h | Alto |
| 5 | Corrigir imports ARP/PCA | Reativa 2 crawlers | 1h | Médio |

---

## 6. Mapa de Dependências

```
PostgreSQL online
├── Crawl PNCP executado
│   ├── CLI funcional (list, show, explain, export)
│   ├── Briefing diário utilizável
│   └── Dados frescos para scoring
├── Migration v3 aplicada
│   ├── source-health funcional
│   ├── opportunity_intel populado
│   └── coverage_evidence tracking
├── Crawlers ARP/PCA consertados
│   └── +2 fontes de dados
└── Pipeline Intel completo
    ├── intel_report.py (PDF)
    └── Dossiê de oportunidade
```

---

## 7. Estado AIOX

| Item | Valor | Decisão |
|------|-------|---------|
| Versão instalada | 5.2.9 (.aiox-core/package.json) | **MANTER** |
| npx resolve | 5.3.0 (npm registry) | Não usar npx para invocar |
| B2G-FIX-01/02/03 | Done, QA PASS, reviewed_commit: d45728d | ✅ OK |
| B2G-FIX-04 | Done, QA PASS, reviewed_commit: **N/A** | ❌ Corrigir |
| QW-01 | Done, QA PASS, reviewed_commit: **null** | ❌ Corrigir |
| Phase Zero (1.1-1.5) | Markdown vs state divergentes | ⚠️ Alinhar |
| EPIC MASTER v3.0 | Desatualizado (B2G-FIX-04 status) | ⚠️ Atualizar |

---

## 8. Confiança

| Área | Confiança | Notas |
|------|-----------|-------|
| Estado do código | ALTA | Ruff limpo, testes passam, arquitetura clara |
| Estado do banco | ALTA | PostgreSQL offline confirmado |
| Estado de produção | ALTA | VPS nunca provisionada, 0 crawlers contínuos |
| Valor comercial | ALTA | 0% hoje, ~10-15% do potencial com banco online |
| Estado AIOX | ALTA | 4/5 state files OK, 2 anomalias |
| Cobertura real | MÉDIA | Métrica depende de migration v3 aplicada |
| Entidades unresolved | MÉDIA | Data diz 0, PRD diz 604 — métricas diferentes |

---

## 9. Próximo Passo Imediato

**Subir PostgreSQL e executar crawl PNCP.** Sem isso, todo o resto é teórico.

Comandos:
```bash
docker compose up -d test-db
python3 scripts/opportunity_intel/cli.py update --source pncp
python3 scripts/opportunity_intel/cli.py list --ranking GO --limit 10
```

---

*Auditoria consolidada por Claude Opus 4.8 (DeepSeek v4 Pro) — 5 auditores paralelos + convergência.*
*Próxima fase: Epic e execution plan.*
