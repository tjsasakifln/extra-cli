# Permissões e Papéis — Extra Consultoria

> Re-extração Detective 2026-07-17  
> Sistema **CLI single-operator** (sem RBAC multi-tenant de aplicação).  
> 🟢 CONFIRMADO | 🟡 INFERIDO

---

## 1. Modelo real

Não há usuários/roles em banco de aplicação. Controle é:

| Camada | Mecanismo |
|--------|-----------|
| OS / SSH | acesso VPS `ec-prod`, systemd user |
| Env secrets | `.env` / secret store (DATABASE_URL, API keys) |
| GitHub | permissões de repo + CI secrets |
| Filesystem | quem pode ler `output/`, `data/`, ledgers |
| Postgres | roles de DB (app vs admin) — 🟡 depende do deploy |

---

## 2. Papéis lógicos (operacionais)

| Papel | Quem | Pode |
|-------|------|------|
| **Operador consultor** | Tiago (único) | workspace CLI, gates locais, relatórios, decisões no ledger |
| **Operador crawl/VPS** | mesmo / automação systemd | timers de crawl, backup, health |
| **CI bot** | GitHub Actions | lint, test, bandit, pip-audit — fail-closed |
| **Desenvolvedor** | devs com clone | código; **não** deve commitar raw operacional (ADR-020) |
| **Auditor/QA** | humano/agente | ler docs/ops carimbados, dual-metric, evidence |

---

## 3. Matriz de capacidade × papel

| Capacidade | Consultor | systemd | CI | Dev local |
|------------|:---------:|:-------:|:--:|:---------:|
| `workspace today/decide` | ✅ | ❌ | ❌ | ✅ |
| crawl live fontes | ✅* | ✅ | ❌ | ✅* |
| mutar Postgres produção | ✅* | ✅ | ❌ | ⚠️ |
| carimbar DoD em docs/ops | ✅ | ❌ | ❌ | ✅ |
| commitar raw JSONL | ❌ | ❌ | ❌ | ❌ |
| alterar Client Profile | ✅ | ❌ | ❌ | ✅ (PR) |
| bypass coverage gates | ❌ | ❌ | ❌ | ❌ |
| ler secrets .env | ✅ host | ✅ unit | secrets GH | local only |

\* sujeito a credenciais e rate limits das fontes.

---

## 4. Controles fail-closed (autorização de *claim*)

Mais importante que RBAC: **autorização de afirmações**:

| Claim | Autorizado somente se |
|-------|------------------------|
| “Cobertura 95%” | M2 operational ≥95% com evidência |
| “GO comercial” | score + Client Profile + sem hard exclusion; default REVIEW |
| “Fonte operacional” | `is_strict_operational` / satisfactory evidence |
| “Zero resultados OK” | `empty_confirmed` + supports_zero_proof |

---

## 5. Artefatos sensíveis

| Artefato | Restrição |
|----------|-----------|
| `config/mides-bigquery-sa.json` | secret de serviço — não expor |
| `.env` | nunca no git |
| ledgers / overrides | local; podem conter decisões comerciais |
| raw crawls | gitignored (ADR-020) |

---

## 6. Lacunas 🔴

1. Sem RBAC se no futuro houver multi-consultor/web UI.  
2. Papéis Postgres de produção não auditados nesta extração (requer VPS).  
3. Ledger de decisões sem assinatura criptográfica — confiança no filesystem + git de resumos.
