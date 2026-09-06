# Runbook — autoridade do plano comercial CONFENGE

**Status:** CURRENT
**Lei superior:** `DOD.md` (P0 plano comercial / #468) → ADR-039 Accepted/Effective →
`docs/contracts/confenge-commercial-plane/v1/operating-authority.json`
**Preflight:** `python3 -m scripts.ops.check_confenge_commercial_plane`
**Linter de plano:** `python3 -m scripts.ops.check_confenge_campaign_plan --file <arquivo>`

Este é o único runbook operacional ativo desta regra. Handoffs e comentários
que descrevem a cascata PNCP→feed são HISTORICAL / SUPERSEDED.

## Dois planos

```
PNCP LIVE                          DATA LAKE / PLANO COMERCIAL
─────────────────────────────      ──────────────────────────────────────────
pncp-contracts.timer               extra-confenge-target-fit-refresh.timer
  → pncp-contracts.service         extra-confenge-target-fit-reconcile.timer
    (ingest + persist)             extra-confenge-contact-cycle.timer
                                   extra-confenge-feed-cycle.timer
source health envelope             read persisted projection
FRESH|DEGRADED|STALE|UNKNOWN         → refresh → reconcile
(telemetry only)                     → contact discovery → feed
```

Não existe `OnSuccess` entre os planos. `PENDING_ONSUCCESS` é estado inválido.

## Diagnóstico read-only

```bash
python3 -m scripts.ops.check_confenge_commercial_plane
python3 -m scripts.ops.check_confenge_commercial_plane --host-readback
ssh ec-prod "systemctl show pncp-contracts.service extra-confenge-source-freshness-gate.service extra-confenge-target-fit-refresh.service extra-confenge-target-fit-reconcile.service extra-confenge-contact-cycle.service extra-confenge-feed-cycle.service -p Id -p ActiveState -p OnSuccess --no-page"
ssh ec-prod "systemctl list-timers 'extra-confenge-*' 'pncp-contracts.timer' --all --no-pager"
```

Não iniciar jobs comerciais a partir deste runbook.

## Mutex canônico e identidade de operação

Estado e lock duráveis:
`/var/lib/extra-consultoria/commercial-cycle-authority/authority.{json,lock}`.
Diagnóstico não mutante:

```bash
python3 -m scripts.ops.confenge_commercial_mutex status
```

Os units/timers de refresh, reconcile, contact e feed recebem um
`INVOCATION_ID` do systemd e usam scope `stage`. Uma execução explícita de ciclo
deve fornecer o mesmo ID e owner nos quatro comandos:

```bash
export CONFENGE_COMMERCIAL_OPERATION_ID='<checkpoint>:cycle-1'
export CONFENGE_COMMERCIAL_OPERATION_SCOPE=cycle
export CONFENGE_COMMERCIAL_OWNER_ID='<session-owner>'
```

O primeiro estágio reserva a operação; a ordem aceita é exatamente refresh →
reconcile → contact → feed. Replay de estágio completo e operação concorrente
saem 75 antes da mutação. Nunca editar o JSON nem apagar o lock.

Após crash `ACTIVE`, primeiro inspecionar e então recuperar somente o operation
ID observado:

```bash
python3 -m scripts.ops.confenge_commercial_mutex recover-stale \
  --expected-operation-id '<id>' --recovered-by '<operator>'
```

Se uma operação estiver `OPEN` entre estágios e for formalmente abandonada, usar
`abort-open` com ID, ator e motivo. `recover-stale` nunca toma lock vivo e
`abort-open` nunca aceita `ACTIVE`.

### Cobertura de entrypoints

| Entrada | Boundary canônico |
|---|---|
| `systemctl start|restart` e timers dos quatro stages | CLI pinado → mutex único |
| `systemd-run`/shell/agent chamando os mesmos módulos | operation ID obrigatório → mutex único |
| `scripts.confenge_target_fit refresh|reconcile` | `acquire_stage_from_env` |
| hook `notify_datalake_committed` | refresh stage-scope; soft-fail se sem autoridade |
| `scripts.ops.confenge_contact_cycle` | contact; state arbitrário não contorna o mutex |
| DUI `batch enqueue|retry|resume|publish|export-contacts` | exige processo descendente do owner contact ativo; não depende do nome da coorte |
| `scripts.ops.confenge_feed_cycle` e `scripts.confenge_activation publish` | feed antes de build/promote |
| target-fit/contact workers | subordinados: processam filas; não iniciam/reiniciam nem promovem ciclo |
| feed monitor/status/progress/inspect | somente leitura; não adquire autoridade |

## Sequência correta de um ciclo comercial

1. Confirmar Data Lake disponível e projeção target-fit persistida.
2. `target-fit refresh` (CDC) sobre o persistido.
3. `target-fit reconcile` nacional; exigir coverage/membership fechados.
4. Contact discovery sobre o `TARGET_CONFIRMED` **desse** reconcile.
5. Publicar feed somente com membership/hash/as_of reconciliados e envelope de
   source health **registrado verbatim**.
6. SMTP, despausa, kill switch, mailbox, cap, rate, janela e follow-up
   permanecem fora deste ciclo.

Ingestão PNCP pode estar `activating`, `failed`, `STALE` ou `UNKNOWN` **em
paralelo**. Não se espera o crawler.

## Ingestão vs refresh comercial vs publicação

| Operação | Unit / comando | Pode publicar? |
|----------|----------------|----------------|
| PNCP ingestion run | `pncp-contracts.service` | Não |
| Commercial refresh | refresh + reconcile | Não (ainda) |
| Contact discovery | `extra-confenge-contact-cycle.service` | Não |
| Feed publication | `extra-confenge-feed-cycle.service` | Sim, se os gates do Data Lake passarem |
| Source health probe | `pncp_contract_freshness --health` | Nunca |

## Pode bloquear / não pode bloquear

| Sinal | Pode bloquear o ciclo comercial? |
|-------|----------------------------------|
| Data Lake indisponível | Sim |
| `coverage_ratio` < 1.0 | Sim |
| `unexplained_missing` ≠ 0 | Sim |
| paginação não exaurida | Sim |
| fila não terminal | Sim |
| membership/binding divergente | Sim |
| identidade oficial inválida | Sim |
| `parafiscal_institutional_hard_out` | Sim |
| suppression / DNC / revogação | Sim |
| contato inválido | Sim |
| envelope de source health ausente | Sim (inauditável) |
| PNCP `FRESH` | Não |
| PNCP `STALE` / `DEGRADED` / `UNKNOWN` / 503 | Não |
| crawler `activating` / `failed` | Não |
| sete janelas PNCP abertas | Não |
| `OnSuccess` pendente | Inválido — não esperar |

## Resposta operacional quando PNCP está activating / STALE / PARTIAL / UNKNOWN

1. Registrar o envelope verbatim (`status`, `reason_codes`, `run_id` se houver).
2. Não fabricar `FRESH`.
3. Seguir os gates do Data Lake.
4. Se o Data Lake for íntegro, o ciclo comercial **pode** correr.
5. Se o Data Lake for inválido, o ciclo **falha fechado** mesmo com PNCP `FRESH`.
6. Não matar `pncp-contracts.service` para “destravar” o comercial.

## Não reutilizar resultado parcial

Refresh/reconcile/contact/feed de uma campanha abortada **não** autorizam a
próxima. Membership divergente invalida snapshot e contact projection.
Campanha futura exige novo `/goal` e novo preflight.

## Exemplos

Correto:

- PNCP `STALE` + Data Lake íntegro → ciclo comercial permitido.
- PNCP `FRESH` + Data Lake inválido → ciclo comercial bloqueado.
- PNCP `UNKNOWN` + last-good válido → decisão pela autoridade comercial vigente
  (`COMMERCIAL_AUTHORITY/1.0` aging), não pelo crawler.
- Novo membership → contact discovery reconciliado **antes** da publicação.
- Ingestão PNCP ativa em paralelo, não aguardada.
- Source health registrado verbatim, sem promover `FRESH`.

Incorreto (PROIBIDO — o linter rejeita em planos CURRENT que instruam isto):

- PROIBIDO aguardar `pncp-contracts` ficar `FRESH` e então rodar feed.
- PROIBIDO `CONTACT_DISCOVERY=PENDING_ONSUCCESS`.
- PROIBIDO após fechar sete janelas PNCP, publicar contatos.
- PROIBIDO “source run canônico” sem dizer ingestão PNCP ou ciclo comercial no Data Lake.
- PROIBIDO `PNCP_LIVE_REQUIRED_FOR_FEED=YES`.
- PROIBIDO retomar a branch do PR #528.
- PROIBIDO canário Warmbly satisfaz evento oficial.
- PROIBIDO `QUEUED` como SMTP enviado.

## Links

- `DOD.md` — regra superior
- `docs/architecture/adr/ADR-039-confenge-pncp-outbound-decoupling.md`
- `docs/architecture/confenge-commercial-plane-authority-matrix.md`
- `docs/contracts/confenge-commercial-plane/v1/operating-authority.json`
- `docs/contracts/confenge-commercial-authority/v1/` — aging last-good (não é este contrato)
- Testes: `tests/test_confenge_commercial_plane.py`,
  `tests/test_confenge_campaign_plan.py`,
  `tests/confenge_target_fit/test_commercial_plane_source_separation.py`,
  `tests/test_pncp_outbound_decoupling.py`,
  `tests/test_confenge_outreach_refresh_cascade.py`
