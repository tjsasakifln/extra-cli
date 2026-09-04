# Matriz de autoridade — plano comercial CONFENGE

**Status:** CURRENT (2026-09-04)
**Campanha:** `CONFENGE_COMMERCIAL_PLANE_AUTHORITY_RECTIFICATION_01`
**Não é uma segunda especificação.** A lei superior está em `DOD.md`,
ADR-039 Accepted/Effective e
`docs/contracts/confenge-commercial-plane/v1/operating-authority.json`.

Hierarquia:

```
DOD.md
→ ADR aceita e vigente
→ contrato machine-readable
→ código testado
→ evidência reproduzível
→ runbook/handoff
→ comentários históricos
```

| Fonte | Afirmação | Status | Autoridade | Ação | Evidência |
|-------|-----------|--------|------------|------|-----------|
| `DOD.md` § P0 plano comercial / #468 | PNCP live não é autoridade comercial; commercial refresh = Data Lake; PENDING_ONSUCCESS inválido | CURRENT (esta campanha) | Superior | Manter; regressão bloqueia merge | Texto P0 + preflight |
| ADR-039 | PNCP live = ingestão+telemetria; datalake = fonte operacional; OnSuccess proibido | CURRENT — Accepted/Effective | ADR vigente | Manter alinhada ao DOD | PR #535 merge `ad4d18f8`; QA `d99dc92c`; story Done / QA PASS |
| `docs/architecture/adr/INDEX.md` ADR-039 | Accepted/Effective | CURRENT | Índice | Coerente com o arquivo da ADR | INDEX |
| `docs/contracts/confenge-commercial-plane/v1/operating-authority.json` | Qual plano governa | CURRENT / ACTIVE | Contrato machine-readable | Não duplicar 1.0; não adotar 2.0 | contract_id + testes |
| `docs/ops/confenge-commercial-plane-authority.md` | Runbook operacional único dos dois planos | CURRENT | Runbook | Único runbook ativo desta regra | docs/INDEX.md, AGENTS.md |
| `docs/contracts/confenge-commercial-authority/v1/` | Last-good aging / admission vs transport (`COMMERCIAL_AUTHORITY/1.0`) | CURRENT para aging; a linha “live PNCP não-FRESH recusa fatos novos” é SUPERSEDED | Contrato 1.0 ≠ operating-authority | Não reescrever o contrato; a linha de recusa live foi marcada SUPERSEDED | Nota no markdown 1.0 |
| `scripts/confenge_activation/commercial_authority.py` | Envelope de source health obrigatório; FRESH não é veredito comercial | CURRENT (comportamento #535) | Código testado | Docstring não pode restaurar FRESH como gate de fatos novos | `source_health_attestation_present` |
| `deploy/confenge/pin_release.py` `CHAIN_TIMERS` | Cada estágio comercial tem timer independente; `CHAIN_DISABLED_TIMERS=()` | CURRENT | Código testado | Reintroduzir cascata/órfão falha o pin/preflight | `tests/test_confenge_release_pin.py` |
| `deploy/systemd/pncp-contracts.service` | Ingestion-only, sem OnSuccess | CURRENT | Código testado | Host live deve coincidir; backups `.pre-*` são HISTORICAL | unit + host readback 2026-09-04 |
| Units target-fit / contact / feed | Sem OnSuccess; timers próprios | CURRENT (versionado) | Código testado | Timers desabilitados no host pelo freeze #468 são pausa operacional, não órfão arquitetural | `systemctl show -p OnSuccess` vazio; timers `disabled` sob freeze |
| `scripts/ops/source_maintenance_health.py` | Saúde da fonte / liveness de manutenção; `DECOUPLED_ON_SUCCESS` | CURRENT — telemetria, não autoridade comercial | Código testado | Não promover FRESH a PASS comercial | contrato `SOURCE_MAINTENANCE_HEALTH/1.0` |
| Story `current-pncp-outbound-decoupling-01` | Desacoplamento Done / QA PASS | CURRENT (histórico de entrega) | Story | Não reabrir o desacoplamento | story file |
| PR #535 | Integra o desacoplamento sem adotar população 2.0 | CURRENT (implementação vigente) | Evidência | Não reverter | merge `ad4d18f8` ancestral de `origin/main` `04683dc8` |
| PR #528 | População `COMMERCIAL_AUTHORITY/2.0` + desacoplamento misturados | SUPERSEDED / PARTIALLY_REUSED | Comentário histórico < DOD | Fechar; não mergear; não reusar a branch | comentário `5512109904`; dirty vs main |
| ADR-038 em #528 (`docs/architecture/adr/ADR-038-confenge-durable-commercial-authority.md`) | Redefine população a partir de `v_contracts_canonical_v2` | SUPERSEDED nesta árvore (não merged); exige decisão humana separada | Não vigente em main | Issue própria, sem implementação | #528 files; main ADR-038 continua being national census |
| Issue #468 corpo pré-retificação | “source run” / “refresh canônico” sem namespace; dois ciclos | CONTRADICTORY até retificação do corpo vivo | Issue < DOD | Corpo vigente recebe INTERPRETAÇÃO CANÔNICA; comentários históricos intactos | corpo + comentários 2026-09-04 |
| Comentário #468 `5545203044` | Libera “source run canônico contemporâneo” | HISTORICAL (checkpoint humano); interpretação corrigida em `5545805218` e abortada | Comentário < DOD | Não retomar; novo /goal | founder abort |
| Comentário #468 `5545805218` | Refresh = Data Lake; PNCP assíncrono | CURRENT como correção, mas a execução comercial que seguiu foi abortada | Comentário | Não reutilizar refresh/reconcile parciais | `refresh-20260904T200041Z-ea2063`, `reconcile-20260904T201037Z-f0fb75` NOT_REUSABLE |
| Issue #469 corpo | Yield no TARGET_CONFIRMED pós-#468; não cria transporte | CURRENT com bloqueio de incidente | Issue | Não instruir espera PNCP live | corpo |
| Comentário #469 `5449927755` | “Contact discovery OnSuccess chain is the live path” | HISTORICAL / SUPERSEDED | Comentário | Não usar como instrução vigente | ADR-039 |
| Issue #530 | Envelope Live Intelligence oficial; canário Warmbly ≠ evento oficial | CURRENT | Issue | Canário não satisfaz evento oficial | corpo + comentários ACK |
| Handoff 2026-08-25 em #468 | 7/7 janelas PNCP então reconcile/feed | HISTORICAL (arquitetura OnSuccess) | Comentário | Rotular; não reescrever | comentário `5411464544` |
| `pncp-contracts.service.pre-d0c706c5-20260831` no host | `OnSuccess=extra-confenge-source-freshness-gate.service` | HISTORICAL (backup, não unit live) | Artefato de host | Não tratar como vigente | grep host 2026-09-04 |

## Terminologia canônica

| Termo | Significa | Não significa |
|-------|-----------|---------------|
| PNCP ingestion run | oneshot `pncp-contracts.service` / crawler | gate de contact/feed |
| commercial refresh | target-fit refresh + reconcile sobre Data Lake persistido | consulta live ao PNCP |
| source health | telemetria FRESH\|DEGRADED\|STALE\|UNKNOWN | autorização comercial |
| source run canônico *(sem namespace)* | **terminologia proibida** | — |
| PENDING_ONSUCCESS | **estado inválido** para target-fit/contact/feed | espera legítima |

## Host vs versionado (2026-09-04)

- Units live: `OnSuccess=''` em PNCP, gate, refresh, reconcile, contact, feed. `HOST_ONSUCCESS_COUPLING=ZERO`.
- Pin: `6b0bcc03081277040fcb304ca5c8090963d70e46` (#541).
- Timers comerciais `disabled` no host = freeze do incidente #468, não `CHAIN_DISABLED_TIMERS` versionado.
- `pncp-contracts.timer` permanece enabled (ingestão independente). **Não matar** o crawler por abort de campanha comercial.
