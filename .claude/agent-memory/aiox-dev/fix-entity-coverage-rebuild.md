---
name: fix-entity-coverage-rebuild
description: entity_coverage rebuilt from actual bid/contract JOINs — 46.6% real coverage vs inflated prior state
metadata:
  type: project
---

**entity_coverage foi reconstruido** de dados reais em 2026-07-11.

Antes: 692 covered (via matched_entity_id estatico), potencialmente inflado.
Depois: 972 covered (46.6%) — 692 via matched_entity_id + 280 via contratos.

**Why:** A tabela estava populada com dados inconsistentes — registros marcados como covered sem JOIN real contra bids que indicassem cobertura ativa. A origem exata da inflacao e desconhecida (possivelmente carga inicial nao-verificada).

**How to apply:** Qualquer operacao que leia `entity_coverage` deve confiar nos dados atuais. O rebuild usa tres estratejias em cascata: (1) `pncp_raw_bids.matched_entity_id`, (2) CNPJ-8 fallback nos bids, (3) CNPJ-8 nos contratos. Para re-rodar, DELETE e re-executa os INSERTs em `fix-entity-coverage-rebuild.md`.

**Numeros chave:**
- 2.085 entidades totais, 972 cobertas (46.6%), 1.113 descobertas
- Dentro 200km: 437/1.093 (40.0%)
- Fora 200km: 535/992 (53.9%)
- Municipios: 100% cobertos; Orgaos Executivos Municipais: 2.7% (maior gap)
- Comandos: `coverage --baseline` e `coverage --gaps` funcionando
