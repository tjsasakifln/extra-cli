# Story — Desacoplar PNCP (ingestão) do plano comercial outbound

- **ID:** `current-pncp-outbound-decoupling-01`
- **Risco:** HIGH-RISK (systemd, deploy, gates de publicação)
- **Base:** `main` @ `e693f2ae` (#529 + #534)
- **Origem parcial:** PR #528 — tratado como `SUPERSEDED/PARTIALLY_REUSED`

## Problema

O plano comercial (qualificação, publicação, exportação, coorte, transporte) está
acoplado à saúde viva do PNCP por dois caminhos:

1. **systemd:** `pncp-contracts.service` → `OnSuccess=extra-confenge-source-freshness-gate.service`.
   O gate executa `pncp_contract_freshness --live --health`, que **retorna
   `health_exit != 0` quando o contrato não é `FRESH`**. Um `OnSuccess` só dispara
   em sucesso, portanto PNCP não-FRESH congela toda a cascata
   `gate → target-fit-reconcile → contact-cycle → feed-cycle`.
2. **código:** cinco pontos abortam com `ValueError`/`EXIT_FAIL` quando o contrato
   PNCP não é `FRESH`, mesmo havendo dado persistido válido no datalake.

Consequência: indisponibilidade/STALE/UNKNOWN de uma fonte de **aquisição** bloqueia
operação comercial sobre população já provada e persistida.

## Arquitetura desejada

```
PNCP live      = ingestão + telemetria assíncrona (não governa nada)
Datalake       = fonte operacional do outbound (fail-closed de verdade)
```

## Escopo IN

1. `pncp-contracts.service` vira ingestion-only (sem `OnSuccess`).
2. `extra-confenge-feed-cycle.timer` com cadência independente 4x/dia.
3. Remoção do bloqueio de freshness PNCP em:
   `confenge_outreach_pipeline/cli.py`, `confenge_activation/publish.py`,
   `warmbly_bridge/export.py`, `ops/build_controlled_email_cohort.py`,
   `confenge_outreach_pipeline/pipeline.py`.
4. Freshness PNCP permanece visível como telemetry/source health, sem fabricar `FRESH`.
5. Datalake indisponível, membership inválido, suppression/DNC, identidade ou binding
   inválidos continuam fail-closed.

## Escopo OUT (invariantes absolutos)

- **NÃO** adotar a população `COMMERCIAL_AUTHORITY/2.0` do #528
  (`commercial_authority_v2.py`, `rebuild_commercial_qualification.py`,
  `commercial_qualification_corpus`). A mudança de população comercial exige
  decisão separada.
- **NÃO** escrever `TARGET_CONFIRMED` como carimbo fabricado.
- Preservar a semântica de targeting vigente em `main` pós-#529, inclusive
  `parafiscal_institutional_hard_out`.
- Preservar a identidade oficial de contratos corrigida por #534.
- **NÃO** usar DNC/env pause como substituto de exclusão estrutural.
- **NÃO** mexer em SMTP/GO/kill switch.
- **NÃO** re-freezar artefatos nesta PR.

## Correção obrigatória sobre o #528

O #528 remove `OnSuccess` do PNCP mas mantém
`extra-confenge-target-fit-refresh.timer`, `...-reconcile.timer` e
`extra-confenge-contact-cycle.timer` em `CHAIN_DISABLED_TIMERS`. Sem o `OnSuccess`
e sem timer, **nada mais dispara target-fit e contatos** — a loja `published`
de target-fit congela. No #528 isso é irrelevante (a população passa a vir direto
da view V2); aqui seria fatal, porque a população continua sendo a loja target-fit.

Portanto esta PR também **habilita as cadências independentes** de refresh,
reconcile e contact-cycle, e quebra o `OnSuccess` gate→reconcile e
contact-cycle→feed-cycle.

## Critérios de aceite

- **AC1** — `Given` contrato PNCP `STALE`/`503` `And` datalake válido
  `When` o pipeline comercial roda `Then` qualificação, publicação, exportação e
  construção de coorte concluem, com `source_operational_health` registrado.
- **AC2** — `Given` contrato PNCP `FRESH` `When` o pipeline roda `Then` o
  comportamento (observação, watermark, `target_fit_observation_run_id`) permanece
  compatível com `main`.
- **AC3** — `Given` datalake indisponível/inválido (coverage < 1.0, missing
  inexplicado, paginação incompleta, fila não resolvida) `When` o pipeline roda
  `Then` falha fechada, independentemente da saúde do PNCP.
- **AC4** — regressão #529: as 9 raízes contidas e os hard-outs permanecem fora.
- **AC5** — regressão #534: `numeroControlePNCP`/`contrato_id` oficial sobrevive no feed.
- **AC6** — cohort builder aceita autoridade comercial válida com source health
  `STALE`/`UNKNOWN`.
- **AC7** — `pncp-contracts.service` e `extra-confenge-source-freshness-gate.service`
  não possuem nenhum `OnSuccess`; `extra-confenge-feed-cycle.timer` roda 4x/dia
  com `Persistent=true`.
- **AC8** — CI completo verde.

## Rollback

`git revert` do merge; restaurar `OnSuccess=extra-confenge-source-freshness-gate.service`
em `pncp-contracts.service` e `OnCalendar=*-*-* 01,13:20:00` no timer do feed;
`python3 deploy/confenge/pin_release.py apply --sha <sha anterior>`.

---

## QA Results

**Gate:** CONCERNS
**Revisor:** Quinn (@qa)
**Data:** 2026-09-02
**Commit revisado:** `fdeedfbd` (base `origin/main` @ `e693f2ae`)
**Nível:** HIGH-RISK

### Invariantes absolutos (Escopo OUT) — todos preservados

| Invariante | Evidência |
|---|---|
| População `COMMERCIAL_AUTHORITY/2.0` não adotada | `git diff --stat e693f2ae..fdeedfbd -- scripts/confenge_activation/commercial_authority_v2.py scripts/confenge_activation/rebuild_commercial_qualification.py scripts/confenge_target_fit/ scripts/confenge_universe/` → vazio. Ambos os módulos já existiam em `e693f2ae` (`git cat-file -e` OK); nenhum novo import ou call-site. `commercial_qualification_corpus` não aparece em nenhum arquivo. |
| Nenhum `TARGET_CONFIRMED` fabricado | Único write literal em `scripts/ops/confenge_scale_rehearsal.py:261` (pré-existente, fora do diff). No diff, `TARGET_CONFIRMED` só aparece como dado de fixture em `tests/test_pncp_outbound_decoupling.py:47`. |
| Semântica #529 (`parafiscal_institutional_hard_out`) | `scripts/confenge_universe/parafiscal.py:32` intacto; `scripts/confenge_universe/` fora do diff. `tests/confenge_universe/` 124 passed. |
| Identidade oficial de contratos #534 | `tests/test_contract_supplier_identity.py`, `tests/test_national_contract_truth.py`, `tests/contract_comparables/test_official_canary.py` verdes. |

### Fail-closed (AC3) — não afrouxado; estritamente ≥ `main`

`scripts/confenge_outreach_pipeline/pipeline.py:508-528` — os gates de datalake (`coverage_ratio < 1.0`, `last_full_reconcile_unexplained_missing != 0`, `pagination_exhausted_normally`, fila `pending/processing/retry/dead`) passaram a rodar **incondicionalmente dentro do bloco com DSN**, fora do antigo `if source_observed_at:`.

Prova de que isso é ≥ `main`: em `main`, `run_pipeline` abortava em `pipeline.py:484` (`authoritative PNCP freshness must be FRESH for a live feed`) sempre que havia DSN e status != FRESH; e `_published_target_fit_snapshot` exigia `source_observed_at` não-vazio para um contrato FRESH. Logo, com DSN, `source_observed_at` era sempre não-vazio em `main` e os gates sempre rodavam. Fora isso, o novo código **acrescenta** `last_full_dt.tzinfo is None → raise` (`pipeline.py:502`), antes tratado junto do comparador de ordenação.

Apenas a ordenação `last_full_dt >= observed_dt` e o re-carimbo do watermark continuam acoplados ao PNCP, e só no caminho FRESH (`pipeline.py:524-531`). Nenhum caminho fail-open encontrado. Suppression/DNC, membership, binding e identidade permanecem fora do diff; `source_health_attestation_present` (`commercial_authority.py:407-419`) mantém a exigência de envelope bem-formado, e `_validate_authoritative_manifest` continua exigindo `contract_version` (`publish.py:487`).

### Nenhum FRESH fabricado (AC1/AC4-telemetria)

- Sonda indisponível → `UNKNOWN` + `PNCP_TELEMETRY_UNAVAILABLE` (`cli.py:330-337`), comprovado por `tests/test_pncp_outbound_decoupling.py::test_the_cli_reports_an_unreachable_probe_as_unknown_and_keeps_going`.
- `expires_at` só é calculado no ramo FRESH (`cli.py:324-329`).
- Status reportado verbatim: `pipeline.py:675` (`source_operational_health` no meta do run), `export.py:1448` e `export.py:1604` (manifesto e source_feed). Coberto por `test_export_proceeds_while_the_live_source_is_degraded` (assert status == status, sem upgrade).

### systemd (AC7)

- `pncp-contracts.service` e `extra-confenge-source-freshness-gate.service` sem `OnSuccess` (verificado nos arquivos e por `tests/test_source_maintenance_health.py::test_ingestion_and_source_health_carry_no_on_success_and_locks_are_verbose`).
- `extra-confenge-feed-cycle.timer`: `OnCalendar=*-*-* 02,08,14,20:15:00`, `Persistent=true`, `RandomizedDelaySec=10m`.
- `CHAIN_TIMERS` agora inclui refresh, reconcile, contact-cycle e feed-cycle; `CHAIN_DISABLED_TIMERS = ()` com guarda contra `systemctl disable` sem argumento (`pin_release.py:317-320`).
- `source_maintenance_health.py:497-512` inverte a asserção corretamente: passa a **reprovar** qualquer `OnSuccess` em ingestão/gate.

### Testes executados

```
ruff check scripts/ deploy/ tests/                       -> All checks passed
pytest (alvos do diff, 8 suítes)                         -> 293 passed
pytest tests/ (sem integrity_gates e coverage_live_proof) -> 6219 passed, 298 skipped, 1 failed
  falha única: test_golden_path_coverage::test_dual_coverage_only_exits_nonzero_when_gates_fail
  (pré-existente, exige Postgres local — declarada fora de escopo)
pytest -k "parafiscal_gate|membership_drop|supplier_identity|national_contract_truth" -> 61 passed, 1 skipped
```

Revisão de asserções invertidas: nenhuma máscara de regressão. As trocas em `tests/confenge_outreach_pipeline/test_pipeline.py:566-593` apenas refletem a nova ordem dos gates (fila antes da ordenação) e **ambos** os caminhos continuam provados. As trocas de `status: STALE` por `contract_version: BOGUS/9` em `tests/test_confenge_feed_publication.py` preservam os cenários de "refresh falho não revive autoridade" via outro gatilho de falha ainda vigente.

### Escopo

Sem SMTP/GO/kill switch (as 3 ocorrências de "kill switch" são comentários explicativos). Sem re-freeze: nenhum arquivo em `artifacts/` no diff. Nenhum arquivo de protocolo AIOX (`.claude/`, `.aiox-core/`, `CLAUDE.md`) modificado.

### Issues

| ID | Sev | Descrição |
|---|---|---|
| ARCH-001 | MEDIUM | **Gatilho duplo introduzido em contact-cycle.** `extra-confenge-target-fit-reconcile.service:8` mantém `OnSuccess=extra-confenge-contact-cycle.service` **e** esta PR habilita `extra-confenge-contact-cycle.timer` (01:10). Em `e693f2ae` o timer estava em `CHAIN_DISABLED_TIMERS`, logo havia exatamente um gatilho. Como contact-cycle roda sob `flock --nonblock` com `TimeoutStartSec=20h` / `CONFENGE_CONTACT_TIMEOUT_HOURS=18`, o disparo do reconcile (~05:15) tende a encontrar o lock preso, sair != 0 e acionar `OnFailure=extra-onfailure@%n.service` — alerta espúrio recorrente. Contradiz o docstring do próprio `pin_release.py` e o ADR-039 ("every downstream stage owns an independent timer"). **Correção sugerida:** remover o `OnSuccess` residual do reconcile (plano 100% timer-driven), ou tornar contenção de lock um exit-code de sucesso. |
| OPS-001 | LOW | Feed-cycle 4x/dia sobre projeção de contatos diária (01:10, até 18h de duração) pode encontrar `coverage_complete`/`terminal_equation` incompletos e falhar fechado várias vezes ao dia — comportamento correto, mas gerador de ruído em `extra-onfailure`. Monitorar após deploy. |
| MNT-001 | LOW | `scripts/confenge_activation/commercial_authority.py:426` `historical_source_was_proven_fresh` perdeu seu único caller de produção (`build_controlled_email_cohort.py`); resta apenas `tests/test_commercial_authority.py`. Código morto de produção — remover ou documentar a retenção intencional. |
| MNT-002 | LOW | `scripts/ops/source_maintenance_health.py` deixou de verificar que `extra-confenge-target-fit-reconcile.service` tem exatamente `OnSuccess=...contact-cycle.service` (o antigo `EXPECTED_ON_SUCCESS` foi removido por inteiro). Se ARCH-001 for resolvido removendo o `OnSuccess`, essa perda deixa de importar; caso contrário, é cobertura de drift perdida. |
| MNT-003 | LOW | `pipeline.py:1152` passa `require_authoritative_source_freshness=False` ao exportador. Sem impacto em produção — `confenge_feed_cycle.py:43,143` invoca o entrypoint da CLI por subprocesso, e `cli.py:270-337` sempre produz um envelope (UNKNOWN em exceção). É apenas defense-in-depth perdida para chamadas programáticas diretas de `run_pipeline`. |
| TST-001 | LOW | O ramo `last_full_dt.tzinfo is None → raise` (`pipeline.py:502`), novo nesta PR, não tem teste dedicado. |

### Riscos residuais

- ARCH-001 só se manifesta no host (systemd real); a suíte de testes não pode observá-lo. Validar em `ssh ec-prod "systemctl list-timers 'extra-*'"` após o deploy.
- Nenhum teste exercita o pipeline comercial end-to-end contra Postgres real com fonte STALE; a prova de AC1 é por unidade com `_published_target_fit_snapshot` mockado.

### Veredito

**CONCERNS** — nenhum invariante violado, nenhum caminho fail-open, nenhuma requalificação de raiz contida ou hard-out, suíte verde exceto falhas pré-existentes declaradas. O gatilho duplo introduzido (ARCH-001) é uma regressão operacional real em um deploy HIGH-RISK e deve ser resolvido antes ou logo após a publicação, com validação no host.
