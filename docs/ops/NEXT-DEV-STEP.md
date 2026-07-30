# Próximo passo de desenvolvimento (sem reconstruir contexto)

**Atualizado:** 2026-07-30  
**Branch de record para docs:** `main`

## CONFENGE commercial activation (pós #172/#174)

**Estado:** `BLOCKED` / `BLOCKED_PENDING_HUMAN_ACCEPTANCE` / handoff `READY_FOR_TIAGO_REVIEW`  
**Scope DOD §2.7:** `BLOCKED_SCOPE_UNDERDELIVERED` (0 accepts formais; evidência máquina pronta)  
**Capability SHA:** `7243b87f` · closeout `70d904ef` · skeptic-fix em andamento

### Ação de Tiago (único blocker comercial humano)

1. Abrir `docs/ops/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/TIAGO-REVIEW.md`
2. Revisar `artifacts/.../top20-durable.json` + `review-package/top20-dossiers/` + `top5-outreach-kits/`
3. Preencher `user-acceptance.template.json` só se aceitar a fila
4. **Não** interpretar coverage operacional 1.0 como cadastro RFB 100% (official ≈ 0.03)

### VPS live cycle completed

- Deploy `7ef1fc1d` + dual commercial cycle on VPS full history: **done** (see `vps-live/`).
- Soak NI: **PASS**. Human review still pending.

### Follow-ups técnicos (não humanos)

- Ingestão RFB bulk autenticada para levantar `official_registry_coverage`
- Deploy VPS do SHA integrado **sem** reset de soak + ciclo live (§16)
- Aceites DOD §2.7 via `dod_controller` (pacotes de evidência por item) — meta 20 / 80 pts
- Código: `official_registry_coverage` separado de fallbacks (skeptic-fix)

### Comando ciclo local

```bash
export CONFENGE_COMMERCIAL_STATE_DSN='postgresql://test:test@127.0.0.1:5433/confenge_commercial_activation'
export CONFENGE_COMMERCIAL_SNAPSHOT=artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/snapshot/snapshot-manifest.json
export CONFENGE_COMMERCIAL_OUT=artifacts/campaigns/CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01/run-post-merge
make confenge-commercial-cycle
```

---

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
