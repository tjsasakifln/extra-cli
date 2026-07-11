# Permissões e Papéis — Extra Consultoria

> Gerado pelo Detective em 2026-07-11T14:00:00Z
> doc_level: completo

---

## Modelo de Acesso

🟢 **CONFIRMADO** — PRD, `config/settings.py`, `docs/architecture/architecture.md`

**Single-user system.** Não há RBAC, ACL, autenticação ou autorização.

---

## Arquitetura de Acesso

```
Tiago Sasaki (Consultor)
  │
  ├── SSH → Hetzner VPS (Ubuntu 24.04)
  │     ├── Acesso shell total
  │     ├── python scripts/crawl/monitor.py ...
  │     ├── python scripts/intel_pipeline.py ...
  │     └── python scripts/local_datalake.py ...
  │
  ├── psql → PostgreSQL 17 (porta 5432)
  │     └── Acesso direto (sem RLS, sem middle-tier)
  │
  └── WSL → Scripts locais (desenvolvimento)
        └── Mesmo acesso, ambiente local
```

---

## Decisão Explícita de Arquitetura

> **ADR-003 (implícito):** PostgreSQL raw (psycopg2) sem REST overhead.
> **Justificativa:** Single user. Sem necessidade de API layer, autenticação ou autorização.
> **Fonte:** `docs/architecture/architecture.md` (Decisões de Arquitetura), PRD (W5: Won't Have — Auth/RLS)

---

## Matriz de Acesso

| Recurso | Tiago (SSH) | Outros | Notas |
|---------|-------------|--------|-------|
| PostgreSQL (leitura) | ✅ Total | ❌ | Acesso direto via psql/psycopg2 |
| PostgreSQL (escrita) | ✅ Total | ❌ | Migrations, seed, upserts |
| Scripts Python | ✅ Total | ❌ | Execução via CLI |
| Systemd timers | ✅ (root) | ❌ | Gerenciamento de serviços |
| OpenAI API | ✅ (API key) | ❌ | `.env` com OPENAI_API_KEY |
| PNCP API | ✅ (pública) | — | Sem autenticação |
| DOM-SC API | ✅ (API key) | ❌ | `.env` com DOM_SC_API_KEY |
| Hetzner VPS | ✅ (SSH key) | ❌ | Acesso root |
| PDF/Excel output | ✅ | ❌ | Arquivos locais no VPS |

---

## Ambiente

| Variável | Produção (Hetzner) | Desenvolvimento (WSL) |
|----------|---------------------|----------------------|
| `LOCAL_DATALAKE_DSN` | `postgresql://postgres:***@hetzner:5432/pncp_datalake` | `postgresql://postgres:***@127.0.0.1:5433/pncp_datalake` |
| `OPENAI_API_KEY` | Configurado | Configurado |
| `PNCP_BASE` | `https://pncp.gov.br/api/consulta/v1` | mesma |
| `DATALAKE_BACKEND` | `local` | `local` |

---

## Conclusão

🟢 Este sistema **não possui RBAC**. A matriz de permissões é binária: Tiago tem acesso total, qualquer outro ator não tem acesso algum. Esta é uma decisão arquitetural consciente, documentada no PRD como "W5 — Won't Have: Auth/RLS". O projeto é explicitamente single-user, single-client.
