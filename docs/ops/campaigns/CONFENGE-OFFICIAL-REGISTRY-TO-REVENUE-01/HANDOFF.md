# HANDOFF — CONFENGE-OFFICIAL-REGISTRY-TO-REVENUE-01

## O que está pronto

1. Módulo `scripts/company_registry` (lifecycle completo + CLI).
2. Fail-closed no `confenge_commercial_cycle` sem release ACTIVE.
3. Release seletiva ACTIVE com 211 CNPJs oficiais (shortlist comercial).
4. Top20 oficial 100% + Top5 kits manuais.
5. Outcome ledger com estados human-only protegidos.
6. Testes `tests/company_registry/` (15 passed).
7. Make targets `company-registry-*`.

## O que a próxima sessão deve fazer

1. **Bulk RFB** (quando rede/VPS permitir): staged ZIPs em `data/company_registry/raw/<YYYY-MM>/` → `refresh --raw-dir`.
2. **Selective full candidates**: exportar os ~22.882 CNPJs do run comercial full → `selective-fetch` → `refresh` → medir `official_match_coverage` na população real.
3. **Publish + cycle**: `publish-supplier-registry` + `make confenge-commercial-cycle` com snapshot autenticado.
4. **Tiago review**: preencher aceite humano; **nunca** auto `APPROVED_FOR_CONTACT`.
5. Integrar `DOD-PROPOSED-CHANGES.md` após merge das campanhas paralelas (não editar `DOD.md` nesta branch se ainda paralela).

## Comandos úteis

```bash
export COMPANY_REGISTRY_ROOT=$PWD/data/company_registry
python3 -m scripts.company_registry health
python3 -m scripts.company_registry lookup --cnpj <CNPJ>
python3 -m scripts.company_registry commercial-precheck
python3 -m pytest tests/company_registry/ -q
```

## Bloqueios residuais

| Bloqueio | Tipo |
|----------|------|
| RFB bulk listing 404/timeout | Ambiente de rede |
| População full 22.8k não medida | Volume / tempo |
| Human outreach | Humano (Tiago) |
| VPS proof SSH | Não executado nesta sessão |
