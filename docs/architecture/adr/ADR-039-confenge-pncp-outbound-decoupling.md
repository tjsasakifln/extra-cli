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

Apenas três comportamentos permanecem acoplados ao PNCP, e só quando o contrato
é `FRESH`: a ordenação `last_full_reconcile >= source_observed_at`, a reescrita
de `source_watermark` e o carimbo `target_fit_observation_run_id`.

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

## Extensão — fronteira de aquisição assíncrona (global, 2026-09-05)

*Origem: EXTRA-HOMOLOGATION-LIVE-EVIDENCE-DISCOVERY-01 (#545/#554/#568).
Generaliza a Decisão acima — não a substitui, não cria autoridade concorrente.*

A Decisão original tratou o plano **comercial** (systemd cascade, target-fit,
contact-cycle, feed-cycle). O mesmo princípio é, por construção, uma
invariante de arquitetura do extra-cli inteiro, não uma regra local do
outbound comercial:

1. **A VPS/Data Lake é a fronteira de aquisição da CONFENGE.** Proibido
   qualquer consumidor — campanhas comerciais, relatórios, views, Warmbly,
   web-cfg, meetcfg, ou sessões de coding agents — depender da
   disponibilidade síncrona do PNCP.
2. **PNCP live é upstream assíncrono do Data Lake.** Sua indisponibilidade
   pode atrasar a atualização de uma família de dados, mas não pode
   transformar uma sessão CLI nem um consumidor downstream em cliente direto
   obrigatório do PNCP.
3. **Toda nova família de dados segue o mesmo fluxo:**
   `PNCP/fonte oficial → coletor resiliente executado na VPS → raw/CAS quando
   aplicável → persistência canônica no Data Lake → consumidores`. O
   consumidor lê **apenas** o estado persistido.
4. **Chamadas PNCP live feitas por coding agents são permitidas SOMENTE
   para:** discovery técnico; captura do primeiro payload real; teste/canário
   de uma nova integração; diagnóstico excepcional. Elas **não** constituem
   arquitetura operacional, freshness comercial, requisito recorrente de
   sessão, nem fonte normal de um consumidor.
5. **Após um novo coletor ser validado contra pelo menos um payload oficial
   real, a próxima etapa obrigatória é operacionalizá-lo na VPS** com:
   timer/job próprio e resiliente; retry/backoff; checkpoint/resume; raw
   archive/CAS quando cabível; observabilidade/freshness próprios;
   idempotência; persistência no Data Lake. Proibido manter um caminho
   manual de captura (ex.: `--from-pncp` opt-in por linha de comando) como
   caminho operacional permanente — ele é apenas o canário que prova o
   parser antes do job.
6. **Se o PNCP estiver indisponível:** consumidores continuam usando o
   último estado persistido, com recência/freshness declaradas; ausência de
   dado novo permanece `UNKNOWN`/`STALE` conforme o contrato da família;
   nenhuma informação é inventada; a indisponibilidade upstream não bloqueia
   trabalho downstream que possa legitimamente usar dados já persistidos.
7. **Exceção explícita (gate de aceitação, não dependência arquitetural):**
   para uma família nova que nunca foi coletada (caso #545), é legítimo dizer
   que `LIVE_PARSER_PROVEN` ainda falta até existir um payload oficial real.
   Isso é um gate de **aceitação do coletor**, não uma dependência
   arquitetural do produto. Depois de provado uma vez, a coleta migra para a
   VPS e deixa de depender de sessões CLI.

**Terminologia adicional (soma à tabela acima, não a substitui):**

| Termo | Uso |
|-------|-----|
| Segundo caminho de aquisição | **proibido** — toda coleta PNCP passa pelo coletor resiliente na VPS |
| Canário de payload | prova o parser uma vez; **não** é operação permanente |
| Polling PNCP por sessão | **proibido** como operação normal de qualquer consumidor |

**Preflight:** `python3 -m scripts.ops.check_confenge_campaign_plan --file <arquivo>`
passa a rejeitar (regras `consumer_depends_on_pncp_live`,
`session_pncp_polling_as_normal_operation`,
`second_acquisition_path_outside_lake`,
`canary_payload_as_permanent_operation`) qualquer plano que reintroduza estas
quatro violações, para qualquer consumidor — não só o outbound comercial.

**Para #568 especificamente:** o polling CLI usado para validar o candidato
isolado de #545 foi apenas canário de validação (ponto 4 acima). Não deve
continuar como polling indefinido por sessão. Após o primeiro payload real e
o parser provado, a próxima ação é projetar o job VPS que coleta resultados
periodicamente para `pncp_procurement_results`. Consumidores futuros de
homologação devem ler essa tabela — nunca chamar o PNCP diretamente.

## Consequências

- Uma indisponibilidade do PNCP degrada observabilidade, não receita.
- Uma cascata `OnSuccess` reintroduzida por drift de host passa a ser detectada
  pelo readback (`*_ONSUCCESS_COUPLED`), não silenciosa.
- Cortar `OnSuccess` sem habilitar as cadências correspondentes órfã o estágio:
  `pin_release.py` e seus testes tratam um timer requerido não agendado como
  falha, e `CHAIN_DISABLED_TIMERS` fica vazio por contrato explícito.
- Dado envelhecido no datalake não é mais mascarado por um bloqueio de fonte;
  passa a ser responsabilidade das cadências independentes e do monitor.
