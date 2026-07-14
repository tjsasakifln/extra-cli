# ADR-006: B2G-FIX-04 Migration Fixes — Fresh Install Scope

**Status:** ACCEPTED
**Date:** 2026-07-14
**Decision by:** @architect (Aria) + @data-engineer (Dara)
**Story:** B2G-FIX-04

---

## Contexto

A auditoria de 46 migrations (`docs/audits/migration-forensics-2026-07-14.md`) identificou 7 problemas que impedem fresh install determinístico. As migrations 013, 025a e 026 contêm referências a colunas que nunca foram criadas pelo próprio sistema de migrations — foram adicionadas via DDL manual em ambientes de desenvolvimento.

## Decisão

As correções de migrations históricas (013, 025a, 026) e a renomeação de arquivos (021* → 021a-d) são **exclusivamente para fresh install**.

**NÃO** se aplicam automaticamente a databases existentes com dados.

## Justificativa

1. Databases existentes já aplicaram essas migrations com os schemas incorretos
2. Editar o arquivo `.sql` não retroage sobre tabelas/views já criadas
3. Reaplicar uma migration editada num banco existente pode falhar (objeto já existe) ou ser NO-OP (IF NOT EXISTS)
4. Para bancos existentes, migrations corretivas separadas (042+) são necessárias

## Consequências

- `db/setup_db.sh` é o runner canônico para fresh install
- `scripts/apply-migrations.sh` é deprecated (ver ADR-007)
- `supabase/migrations/` é legado arquivado
- Migrations corretivas para bancos existentes devem ser numeradas 042+
- Checksums no `_migrations` ledger detectam divergências entre fresh install e upgrade

## Alternativas rejeitadas

1. **Criar migrations corretivas 042+ para todos os problemas** — adicionaria complexidade desnecessária para fresh install, onde não há dados a preservar
2. **Rewrite completo do baseline (B2G-DB-01)** — escopo maior, bloqueia Fase 0; adiado para após fresh install funcional
3. **Manter migrations históricas quebradas** — perpetua impossibilidade de disaster recovery

## Referências

- `docs/audits/migration-forensics-2026-07-14.md`
- `docs/stories/epics/epic-master-b2g/story-B2G-FIX-04-schema-alignment.md`
- `db/setup_db.sh`
