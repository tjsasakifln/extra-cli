# ADR-039 — Desacoplar a ingestão PNCP do plano comercial outbound

- **Status:** Accepted/Effective (2026-09-02)
- **Aceitação:** merge do PR #535 em `ad4d18f8d37c81a24ea9837b83c3a07fc820b2be`
  (ancestral de `origin/main`). Commit revisado pelo QA: `d99dc92c82446ec3e64fa5d30aa1eded6340f633`
  (RE-QA PASS). Story `current-pncp-outbound-decoupling-01` = Done.
- **Contexto de código na aceitação:** `main` @ `e693f2ae` (#529 + #534) como base do PR.
- **População:** **não** se adotou `COMMERCIAL_AUTHORITY/2.0`. Autoridade populacional
  vigente = projeção target-fit persistida.
- **Contrato de plano:** `docs/contracts/confenge-commercial-plane/v1/operating-authority.json`
  (não duplica `COMMERCIAL_AUTHORITY/1.0`).
- **Relacionadas:** ADR-035 (feed target-fit autoritativo), ADR-037 (papel da contratada)
- **Supersede:** cascata systemd `OnSuccess` PNCP→gate→reconcile→contact→feed;
  PR #528 como implementação vigente (SUPERSEDED / PARTIALLY_REUSED).
- **Lei superior:** `DOD.md` § P0 plano comercial / incidente #468.

## Contexto

O outbound da CONFENGE dependia da saúde **viva** do crawler PNCP em dois planos.

**Plano systemd.** A cascata era
`pncp-contracts.service → extra-confenge-source-freshness-gate.service →
extra-confenge-target-fit-reconcile.service → extra-confenge-contact-cycle.service →
extra-confenge-feed-cycle.service`, encadeada por `OnSuccess`. O gate executa
`scripts.ops.pncp_contract_freshness --live --health`, cujo `main()` retorna
`contract["health_exit"]` — **exit code diferente de zero para qualquer contrato
não-`FRESH`**. Como `OnSuccess` só dispara em sucesso, uma janela PNCP não
fechada congelava silenciosamente target-fit, contatos e publicação. Uma cadência
independente do feed (`extra-confenge-feed-cycle.timer`) existia no repositório,
mas `deploy/confenge/pin_release.py` a desabilitava explicitamente em produção.

**Plano de código.** Cinco pontos abortavam com `ValueError`/`EXIT_FAIL` quando o
contrato PNCP não era `FRESH`: `confenge_outreach_pipeline/cli.py`,
`confenge_outreach_pipeline/pipeline.py` (`run_pipeline` e
`_published_target_fit_snapshot`), `warmbly_bridge/export.py`,
`confenge_activation/publish.py` e `ops/build_controlled_email_cohort.py`.

O efeito combinado: uma fonte de **aquisição** indisponível revogava operação
comercial sobre uma população já provada e persistida no datalake.

## Decisão

Separar os dois planos.

```
PNCP live  = ingestão + telemetria assíncrona — não governa nada
Datalake   = fonte operacional do outbound     — fail-closed de verdade
```

1. `pncp-contracts.service` é ingestion-only: sem `OnSuccess`.
2. `extra-confenge-source-freshness-gate.service` é telemetria/diagnóstico: sem
   `OnSuccess`. A telemetria de rotina já é emitida por `scripts/ops/health_bundle.py`
   sob `extra-health-check.timer`, então o gate não ganha cadência própria.
3. Cada estágio a jusante passa a ter cadência independente, habilitada por
   `pin_release.py`: target-fit refresh (30 min), reconcile (diário),
   contact-cycle (diário) e feed-cycle (4x/dia, `02,08,14,20:15`).
4. `source_maintenance_health.py` inverte o contrato: em vez de exigir uma cadeia
   `OnSuccess` exata, passa a **proibir** qualquer `OnSuccess` em
   `pncp-contracts.service` e no gate (`*_ONSUCCESS_COUPLED`).
5. O status PNCP continua registrado verbatim em `source_operational_health` /
   `authoritative_source_freshness`, e **nunca é fabricado como `FRESH`**: uma
   sonda inalcançável vira `UNKNOWN` + `PNCP_TELEMETRY_UNAVAILABLE`.

### Extensão — autoridade concorrente do ciclo comercial (2026-09-05)

Os estágios mantêm cadências independentes, mas compartilham uma única
autoridade de mutação no host. Refresh, reconcile, contact e feed adquirem
atomicamente `confenge.commercial.authority.v1` antes da primeira mutação. Para
um ciclo explícito, a reserva permanece `OPEN` entre estágios e impede outra
operação; timers usam scope de estágio e continuam independentes.

O lock kernel é acompanhado por registro durável com operation ID, owner, host,
PID + process start ticks, boot ID e timestamps. Um crash libera o lock kernel,
mas deixa `ACTIVE`: nova aquisição falha até recuperação explícita comprovar que
o owner morreu e marcar a operação `ABORTED`. Não há timeout/takeover automático.
Retry de estágio concluído é recusado antes da mutação; contact `FAILED` ou de
outra operação nunca reutiliza a coorte anterior.

### O que continua fail-closed

Nada abaixo foi afrouxado; o gate de integridade do datalake foi na verdade
**generalizado**. Em `main` ele só era avaliado quando havia uma observação
`FRESH` — e, como o CLI abortava antes disso, na prática rodava sempre que havia
DSN. Agora é incondicional com DSN, independente da saúde da fonte:

- `coverage_ratio < 1.0`, `last_full_reconcile_unexplained_missing != 0`,
  paginação não exaurida, fila com itens não resolvidos;
- membership/binding, identidade do produtor e hash semântico de publicação;
- suppression/DNC e exclusão estrutural;
- envelope de source health ausente ou malformado (build inauditável);
- recência da própria publicação (`generated_at`, watermark do datalake).

O binding comercial conserva o watermark CDC e os watermarks de decisão lidos
do Data Lake. Mesmo `FRESH`, `source_observed_at` é apenas telemetria: não
substitui esses valores nem carimba um run de observação nas decisões. A
recência do full reconcile continua sendo provada pelo estado persistido.
Correção causal do incidente #468; prova e gate de retomada em
`docs/ops/handoff-2026-09-05-468-persisted-watermark-binding.md`.

## Escopo explicitamente fora

A população comercial **não muda**. `COMMERCIAL_AUTHORITY/2.0`
(`commercial_authority_v2.py`, `rebuild_commercial_qualification.py`, corpus de
qualificação) fica fora: ela redefine quem é alvo lendo `v_contracts_canonical_v2`
e carimba `target_fit_class = "TARGET_CONFIRMED"` para toda raiz qualificada, o
que é uma decisão comercial separada. A semântica de targeting vigente pós-#529
(inclusive `parafiscal_institutional_hard_out`) e a identidade oficial de
contratos de #534 são preservadas integralmente.

## Terminologia canônica

| Termo | Uso |
|-------|-----|
| PNCP ingestion run | crawler / `pncp-contracts.service` |
| commercial refresh | refresh/reconcile no Data Lake persistido |
| source health | telemetria; não governa o comercial |
| source run canônico *(sem namespace)* | **proibido** |
| PENDING_ONSUCCESS | **estado inválido** para target-fit/contact/feed |

Saúde da fonte ≠ prontidão do Data Lake. Um crawler `STALE` com Data Lake
íntegro não bloqueia o plano comercial; um crawler `FRESH` com Data Lake
inválido não o autoriza.

## Consequências

- Uma indisponibilidade do PNCP degrada observabilidade, não receita.
- Uma cascata `OnSuccess` reintroduzida por drift de host passa a ser detectada
  pelo readback (`*_ONSUCCESS_COUPLED`), não silenciosa.
- Cortar `OnSuccess` sem habilitar as cadências correspondentes órfã o estágio:
  `pin_release.py` e seus testes tratam um timer requerido não agendado como
  falha, e `CHAIN_DISABLED_TIMERS` fica vazio por contrato explícito.
- Dado envelhecido no datalake não é mais mascarado por um bloqueio de fonte;
  passa a ser responsabilidade das cadências independentes e do monitor.
