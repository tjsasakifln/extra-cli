# Próximo passo de desenvolvimento (sem reconstruir contexto)

**Atualizado:** 2026-07-25  
**Branch de record para docs:** `main`

## Comando único (priorização DOD / ROI)

```bash
python3 squads/extra-dod-roi/scripts/cli.py force-next
```

Convergência DOD:

```bash
python3 tools/dod_controller.py status
python3 tools/dod_controller.py next
```

## Estado honesto (campanhas em `main`)

| Campanha | Resultado | Bloqueio |
|----------|-----------|----------|
| `HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01` | **BLOCKED** | soak 7d (calendário) |
| `OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01` | **BLOCKED** | soak 7d + recall full strata residual |
| `STRATIFIED-RECALL-SOURCE-RESILIENCE-01` | ver `artifacts/.../result.json` | amostra/strata — não inventar recall 95% |

### Já provado (não re-provar do zero)

- Dual `historical_contracts` **100%** (1093/1093)
- Dual `open_tenders` **100%** (1093/1093) — candidato na campanha OT
- Backfill contratos ≥3y na VPS (~4,4M), cutover, off-site NFS, incremental `pncp-contracts`
- Timer `extra-weekly` com 1º fire de sucesso (OT)
- **Non-claims:** `LOCAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE` até soak + accepts

## O que a próxima sessão deve fazer

1. **Calendário / soak (não fabricar dias):**
   ```bash
   # Contratos
   ssh ec-prod 'cd /opt/extra-consultoria && python3 -m scripts.ops.campaign_soak_tracker --campaign HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01'
   # Open tenders
   make open-tenders-soak
   make verify-open-tenders-production
   ```
2. Após ≥7 dias com fires OK: fechar `result.json=PASS` onde gates internos bastarem; accepts DOD **um a um**.
3. **Recall estratificado:** completar strata / amostra-ouro (`STRATIFIED-RECALL-SOURCE-RESILIENCE-01`) sem claim 95% prematuro.
4. Em paralelo: `force-next` se houver item DOD desbloqueado sem depender de calendário.

## Artefatos

- HC: `artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/`
- OT: `artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/`
- Recall: `artifacts/campaigns/STRATIFIED-RECALL-SOURCE-RESILIENCE-01/`
- Specs: `specs/002-*`, `specs/003-*`, `specs/005-*`
- README / DEVELOPMENT / INDEX

## Non-claims

Não declarar: `LOCAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE`, campaign **PASS** com soak incompleto, recall ≥95% sem strata completas.
