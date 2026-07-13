# ADR-003: Supabase Self-Hosted em Hetzner — Arquitetura de Migração

**Status:** Proposto (2026-07-12)
**Decision:** Documentar caminho de migração do PostgreSQL local para Supabase self-hosted em Hetzner, sem executar o deploy.
**Author:** Dara (Data Engineer) / Gage (DevOps) — Synkra AIOX
**PRD:** `docs/prd/PRD-consultoria-extra.md` v2.0

---

## 1. Contexto

Atualmente, o DataLake Extra Consultoria roda em PostgreSQL local:

- **Local (desenvolvimento):** PostgreSQL 17 em porta variável (5433 ou 54399), schema `pncp_datalake`
- **WSL/Windows:** Acesso via `localhost` com forwarding de porta
- **Hetzner VPS (futuro):** PostgreSQL 17 puro, sem Supabase
- **Testes:** SQLite (unitário) + PostgreSQL (integração)

O PRD prevê migração futura para Supabase self-hosted no Hetzner VPS para:

1. **Interface de consulta** via Studio (UI web opcional)
2. **Auth integrado** (single user, mas com segurança adequada)
3. **API auto-gerada** (PostgREST) para queries HTTP
4. **Realtime subscriptions** para notificações (futuro)
5. **Backup gerenciado** (pg_dump + Supabase CLI)

No entanto, o deploy em Supabase é **futuro** — esta ADR documenta o caminho, não executa.

## 2. Opções Consideradas

### Opção A: PostgreSQL Puro no Hetzner (Status Quo)

**Descrição:** Manter PostgreSQL 17 puro no Hetzner VPS, sem Supabase. Acesso via `psql` e scripts Python com `psycopg2`.

**Prós:**
- Simples, sem overhead de containers
- Menos recursos (RAM/CPU) que Supabase stack
- Já temos o schema e scripts funcionando
- Menor superfície de ataque (sem PostgREST, sem Kong, sem GoTrue)

**Contras:**
- Sem interface web para consultas rápidas
- Sem API REST auto-gerada
- Sem auth integrado (single user via pg_hba.conf)
- Backup manual via cron (pg_dump)

**Veredito:** Opção viável para curto prazo. Não atende requisitos de escalabilidade futura.

### Opção B: Supabase Managed Cloud

**Descrição:** Usar Supabase Cloud (managed) em vez de self-hosted. Plano gratuito ou Team ($25/mês).

**Prós:**
- Zero operação (managed pelo Supabase)
- Backup automático
- Studio, API, Auth prontos
- Escalabilidade horizontal

**Contras:**
- Custo adicional ($25-75/mês)
- Dados em cloud de terceiros (EUA)
- Latência maior que Hetzner (servidor fora do Brasil)
- Vendor lock-in

**Veredito:** REJEITADA. Custo excessivo para single user. Preferência por self-hosted no Hetzner (já pago).

### Opção C: Supabase Self-Hosted no Hetzner (SELECIONADA)

**Descrição:** Rodar Supabase stack completo em Docker no Hetzner VPS.

**Prós:**
- Controle total dos dados (Hetzner Alemanha/Finlândia)
- Studio UI para consultas
- API REST auto-gerada (PostgREST)
- Auth (GoTrue) para futuro multi-user
- Realtime para notificações (futuro)
- Sem custo adicional de licença
- Mesmo VPS já provisionado

**Contras:**
- Complexidade operacional: 8+ containers (PostgreSQL + PostgREST + Kong + GoTrue + Studio + Realtime + Storage + Logflare)
- Consumo de recursos: estimado 3-4 GB RAM + 2 vCPU para o stack completo
- Manutenção de versões (upgrade do Supabase CLI)
- Backup requer config extra (Wal-G ou pg_dump customizado)
- Overhead para single user (mas aceitável pelo Studio + API)

**Veredito:** SELECIONADA como arquitetura alvo.

### Opção D: SQLite -> PostgreSQL Direto (Sem Supabase)

**Descrição:** Pular Supabase completamente. SQLite para testes, PostgreSQL puro em produção.

**Prós:**
- Máxima simplicidade
- Menor consumo de recursos
- Sem dependência de Docker

**Contras:**
- Sem Studio UI
- Sem API REST
- Sem auth estruturado
- Diferenças SQLite vs PostgreSQL não resolvidas (ver B2G-5)

**Veredito:** REJEITADA para produção. Aceitável como estágio intermediário.

## 3. Decisão

**Adotar Opção C: Supabase Self-Hosted no Hetzner como arquitetura alvo, com execução posterior.**

### Stack Alvo

```
┌─────────────────────────────────────────────┐
│              Hetzner VPS (Ubuntu 24.04)       │
│                                               │
│  Docker Compose (Supabase Stack)              │
│  ├── PostgreSQL 15 (Supabase tuned)           │
│  ├── PostgREST (API REST automática)          │
│  ├── Kong (API Gateway)                       │
│  ├── GoTrue (Auth)                            │
│  ├── Studio (UI Web)                          │
│  ├── Realtime (WebSocket)                     │
│  ├── Storage (S3-compatible)                  │
│  └── Logflare (Logs)                          │
│                                               │
│  Scripts Python (fora do Docker)              │
│  ├── Crawlers (psycopg2 -> Supabase DB)       │
│  ├── CLI (local_datalake.py)                  │
│  └── Reports (panorama, etc.)                 │
│                                               │
│  systemd timers (crawl, report, backup)       │
└─────────────────────────────────────────────┘
```

### Componentes

| Componente | Versão | Função | Crítico? |
|------------|--------|--------|----------|
| PostgreSQL | 15.x (Supabase fork) | Banco de dados | SIM |
| PostgREST | 12.x | REST API automática | NÃO (scripts usam psycopg2 direto) |
| Kong | 3.x | API Gateway | NÃO (acesso direto via porta) |
| GoTrue | 2.x | Auth | NÃO (single user) |
| Studio | latest | UI Web | NÃO (CLI é primário) |
| Realtime | 2.x | WebSocket | NÃO (futuro) |
| Storage | latest | File storage | NÃO (PDFs no disco) |
| Logflare | latest | Logs | NÃO (logs no systemd) |

### Requisitos de Hardware

| Recurso | Mínimo | Recomendado |
|---------|--------|-------------|
| vCPU | 2 | 4 |
| RAM | 4 GB | 8 GB |
| SSD | 40 GB | 80 GB |
| Docker | 24+ | 24+ |

O Hetzner VPS atual (4 vCPU, 8 GB RAM, 160 GB SSD) atende aos requisitos.

### Caminho de Migração

```
Fase 1: Diagnóstico ──→ Fase 2: Docker Setup ──→ Fase 3: Export Dados ──→ Fase 4: Import Supabase ──→ Fase 5: Testes
```

#### Fase 1: Diagnóstico (1-2 dias)
- Verificar compatibilidade do schema atual com PostgreSQL 15 (Supabase fork)
- Mapear extensões usadas (PostGIS? pgvector?)
- Identificar queries que precisam de adaptação
- **Output:** `docs/schema/supabase-migration-path.md`

#### Fase 2: Docker Setup (1-2 dias)
- Instalar Docker + Docker Compose no Hetzner
- Configurar `docker-compose.yml` com Supabase stack
- Configurar volumes persistentes
- Configurar rede (portas: 5432 DB, 8000 API, 3000 Studio)
- Configurar auth (single user com email/senha)
- **Output:** `docker/docker-compose.yml`, scripts de setup

#### Fase 3: Export Dados (1 dia)
- Script `scripts/migration/export_to_supabase.py` exporta dados do PostgreSQL local
- Formato: SQL + CSV (gzip)
- Inclui: schema + dados
- **Output:** backup.sql.gz

#### Fase 4: Import Supabase (1 dia)
- Executar import no Hetzner: `psql -h localhost -U postgres -d postgres < backup.sql`
- Verificar integridade (row counts, constraints, indices)
- Atualizar DSN nos scripts Python
- **Output:** Supabase funcional com dados

#### Fase 5: Testes (1 dia)
- Rodar crawlers apontando para Supabase
- Rodar CLI (`local_datalake.py stats`)
- Rodar reports
- Verificar performance
- **Output:** Relatório de validação

## 4. Configuração Técnica

### docker-compose.yml (esboço)

```yaml
version: "3.8"
services:
  db:
    image: supabase/postgres:15.1.1.123
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-postgres}
    volumes:
      - ./volumes/db/data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped

  api:
    image: postgrest/postgrest:v12.2.0
    depends_on:
      - db
    environment:
      PGRST_DB_URI: postgres://${PGRST_DB_USER}:${PGRST_DB_PASS}@db:5432/${PGRST_DB_NAME}
      PGRST_DB_SCHEMA: ${PGRST_DB_SCHEMA:-public}
      PGRST_DB_ANON_ROLE: ${PGRST_DB_ANON_ROLE:-anon}
    ports:
      - "8000:3000"
    restart: unless-stopped

  studio:
    image: supabase/studio:latest
    depends_on:
      - db
    environment:
      STUDIO_PG_META_URL: http://meta:8080
    ports:
      - "3000:3000"
    restart: unless-stopped
```

### DSN Migration

```python
# Atual (local)
LOCAL_DATALAKE_DSN = "postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres"

# Futuro (Supabase Hetzner)
# LOCAL_DATALAKE_DSN = "postgresql://postgres:senha@hetzner-vip:5432/postgres"
```

## 5. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Incompatibilidade PostgreSQL 15 (Supabase fork) vs 17 (local) | Média | Alto | Testar em staging antes de produção. Schema é SQL padrão — risco baixo. |
| Perda de dados durante migração | Baixa | Crítico | Backup completo antes do export. Manter PostgreSQL local até validação. |
| Consumo de RAM > 8 GB com stack completo | Média | Médio | Desabilitar Logflare e Realtime se necessário. Kong pode rodar em modo slim. |
| Docker security no Hetzner | Baixa | Alto | Docker rootless, firewall UFW, apenas portas necessárias expostas. |
| Supabase CLI breaking changes | Média | Médio | Fixar versões no docker-compose.yml. Testar upgrades em staging. |
| Latência de rede entre scripts Python e Docker DB | Baixa | Baixo | Unix socket ou rede bridge compartilhada. |

## 6. Alternativas Futuras

### PostgresML
Se houver necessidade de ML direto no banco, considerar PostgresML como alternativa ao Supabase para embeddings + LLM.

### pgvector
Se houver necessidade de busca semântica (editais similares), adicionar extensão pgvector ao PostgreSQL — compatível com Supabase.

### TimescaleDB
Se houver necessidade de séries temporais (preços ao longo do tempo), considerar TimescaleDB como hypertable para tabelas de valores.

## 7. Não-Decisões (Postergado)

- **Qual versão exata do Supabase CLI?** — Decidir no momento da instalação (a mais recente estável)
- **PostgREST schema exposure?** — Publicar schema inteiro ou views específicas? Decidir quando API for necessária.
- **GoTrue config?** — Single user com email/senha ou magic link? Decidir quando auth for implementado.
- **Backup strategy?** — Wal-G vs pg_dump vs volume snapshot? Decidir na Fase 1 da migração.

## 8. Referências

- Supabase Self-Hosted: `https://supabase.com/docs/guides/self-hosting/docker`
- Story B2G-5: `docs/stories/epics/epic-master-b2g/story-B2G-5-schema-supabase-path.md`
- Schema docs: `docs/schema/final-schema.md` (a criar)
- Export script: `scripts/migration/export_to_supabase.py` (a criar)
- PRD v2.0: `docs/prd/PRD-consultoria-extra.md`
