# ADR-001: PostgreSQL Direto sem API Layer

**Status:** Aceito
**Data:** 2026-07-10
**Decisor:** Tiago Sasaki
**Fonte:** `docs/architecture/architecture.md`, commit `4aa9e4f`

---

## Contexto

O sistema original (smartlic.tech) usava Supabase como backend com REST API. Na migração para standalone, havia duas opções: manter uma camada de API ou acessar o PostgreSQL diretamente.

## Decisão

**Acessar PostgreSQL diretamente via psycopg2, sem REST API intermediária.**

## Justificativa

- Sistema single-user — sem necessidade de autenticação, autorização ou multi-tenancy
- Latência zero de REST overhead
- Scripts Python + psycopg2 é mais simples que manter uma API layer
- Sem dependência de Supabase ou qualquer serviço externo para dados
- Schema e migrations gerenciados diretamente no repositório

## Consequências

- ✅ Stack simplificada: Python → psycopg2 → PostgreSQL
- ✅ Sem custo de Supabase
- ✅ Migrations versionadas no repositório
- ❌ Sem interface para acesso remoto (não necessário)
- ❌ Conexão direta ao banco requer acesso SSH ao VPS
