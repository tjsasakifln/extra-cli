# DOD-PROPOSED-CHANGES — CONFENGE-OFFICIAL-REGISTRY-TO-REVENUE-01

**Não aplicar diretamente em `DOD.md` nesta branch paralela.**  
Promover após integração com campanhas paralelas (documentos processuais, soak, etc.).

## Itens propostos

### 1. Official company registry mirror (novo capability)

- [ ] Existe módulo canônico `scripts/company_registry` com discover/download/load/activate/lookup/coverage/health.
- [ ] Release ACTIVE somente após integrity + validate-load + smoke.
- [ ] Rollback de release anterior provado.
- [ ] `official_registry_coverage` permanece o conceito único (supplier_registry); fallbacks não inflacionam.

**Evidência candidata:** `docs/ops/campaigns/CONFENGE-OFFICIAL-REGISTRY-TO-REVENUE-01/`, `tests/company_registry/`, CLI health/lookup.

### 2. Gates comerciais cadastrais

- [ ] `make confenge-commercial-cycle` fail-closed sem release ACTIVE.
- [ ] Top20 final exige MATCHED + situação + CNAE + release (gate existente `top10_gate` + coverage top20 100%).
- [ ] Metas: official_match_coverage ≥99.5% (população válida), usable ≥98%, top20 100% — **após bulk ou selective full population**.

**Nota:** Nesta entrega, metas atingidas no **universo seletivo de 211**; promover checkbox full-population só com evidência bulk/selective-22k.

### 3. Fila humana + outcome ledger

- [ ] Kits Top5 sem auto-send.
- [ ] Ledger com proibição de auto-atribuir APPROVED_FOR_CONTACT / CONTACTED / REPLIED / MEETING_SCHEDULED / WON.
- [ ] Feedback metrics determinísticas (sem claim de precisão sem volume).

### 4. Operação

- [ ] Raw/staging/active separados; dados grandes fora do Git.
- [ ] Documentado rebuild a partir da fonte pública vs backup de metadados/manifests.
- [ ] Não interferência com soak/crawlers (isolamento de paths).

## Itens explicitamente NÃO propostos como PASS

- `PROJECT_DONE`
- `VPS_OPERATIONAL`
- Aceites DOD §2.7 em massa
- Receita / conversão comercial sem eventos humanos reais
