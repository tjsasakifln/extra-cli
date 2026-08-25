# Incidente #458 — PNCP partial cascade

Status: `IMPLEMENTED + LIVE_WINDOW_ACCEPTED + SOAK_ADMISSION_BLOCKED`; o soak
permanece `NOT_STARTED` até todos os gates de admissão passarem. Não é
`PROVEN`, `VPS_OPERATIONAL` nem aceite de #241/#248.

## Identidade da observação recorrente (2026-08-25)

O coletor PNCP resiliente usa uma identidade horária UTC na janela implícita
do dia corrente. Reexecuções dentro da mesma hora reutilizam checkpoints e o
watermark comprometido. Uma hora posterior recebe escopos distintos de run e
página, então um checkpoint concluído no mesmo dia não pode suprimir uma nova
observação HTTP nem fazer evidência stale parecer saudável. Replays com intervalo
de datas explícito preservam a semântica anterior de checkpoint.

## Diagnóstico e classificação

Baseline sanitizada de 2026-08-22 no `ec-prod`:

| Falha | Classe | Causa |
|---|---|---|
| `growth_above_budget: totalRegistros 46124 -> 46135` | contrato upstream, transitória | `/contratos` incluiu 22/08 ainda aberto; a população mudou durante 93 páginas |
| `totalRegistros 46124 -> 46135` | contrato upstream, transitória | segunda representação fail-closed do mesmo drift, não uma página suprimida |
| `coverage_evidence ... ck_ce_success_zero_scope` | corrupção local, permanente | `success` sem linha canônica era projetado como `success_zero`, sem prova de escopo QW-01 |
| `crawl_failure_events ... PERSIST_FAILURE` | corrupção local, permanente | classifier e CHECK SQL divergiam |
| `coverage-report` sem `psycopg2` | permanente local | `ExecStartPre` usava `/usr/bin/python3`, fora da venv |
| health sem segundo check | permanente local | override do host encadeava módulo inexistente; falha do primeiro `ExecStart` ocultava freshness |
| webhook HTTP 404 | permanente de configuração/destino | alerta completo não tinha fallback durável no caminho live |
| `raw/cas/.body` no resume resiliente | corrupção local, permanente | checkpoints pré-CAS apontavam para JSON raw legado sem `body_sha256`; o loader construía um caminho vazio e abortava em vez de reprocessar a página |

Captura reproduzível: `tests/fixtures/pncp_incident_458/errors-2.sanitized.json`.
Os payloads de contratos, DSN, headers, IP e URL de webhook não foram retidos.

Reauditoria somente-leitura de 2026-08-23T03:33Z, antes do deploy deste patch:

- `ec-prod` estava no `main` `51dc89e1` (#465, data operacional em UTC), mas
  o artifact ainda declarou `range_end=2026-08-23` e completou a janela aberta
  `20260816_20260823`: 92 páginas, 45.812 transformados, 63 inserts na primeira
  passagem e 45.812 skips na repetição. UTC correto sem limite fechado não
  resolve #458;
- `extra-crawl-pncp` continuava falho com exit 2 e `extra-health-check` falho;
  health ainda reportava `dual coverage summary missing`;
- o unit efetivo de coverage ainda usava `/usr/bin/python3` e o journal repetia
  `ModuleNotFoundError: psycopg2`;
- o health efetivo ainda tinha dois `ExecStart`; o segundo apontava para o
  módulo inexistente `scripts.ops.freshness_health` e era suprimido quando o
  primeiro falhava;
- o timer de soak executava a campanha antiga
  `EXTRA-OPERATIONAL-RELIABILITY-AND-COVERAGE-CLOSURE-01`, aceitava exit 2 como
  sucesso do unit e ainda media contratos contra 168h. Isso é observação
  incompleta, não início de #248; a autoridade da issue permanecia
  `NOT_STARTED`.

Relação com issues:

- #241 continua aberta: este incidente não prova `ZERO_CONFIRMED` por ente.
- #248 muda de `NOT_STARTED` para `SOAK_ACTIVE` somente depois dos gates abaixo;
  o critério é p95 de idade de contratos `<=24h` por sete dias UTC consecutivos.
- #458 não fecha por merge: primeiro exige a janela real pós-deploy e o soak
  permanece gate aberto até o sétimo dia.

## Correção

- incremental usa `/contratos/atualizacao` e exatamente D-7..D-1; nunca fecha D;
- retry por página limitado a 3, backoff exponencial+jitter e telemetria por tentativa;
- checkpoint JSON atômico após persistência de página; restart faz replay desde
  página 1 porque o PNCP não garante ordenação estável; upsert absorve duplicatas;
- `partial` só existe com registros transformados utilizáveis e persistência
  íntegra; continua exit não-zero e nunca vira `HEALTHY`;
- erro e `current_window_start` são limpos somente após janela completa;
- health executa infraestrutura e freshness independentemente;
- alertas live sem destino funcional persistem corpo acionável no ledger
  host-local; `OnFailure` grava antes da tentativa remota e um webhook quebrado
  não consegue derrubar nem apagar a evidência do alerta;
- coverage health exige `as_of`, denominador, numerador e zero explícitos;
- migration 100 aceita `PERSIST_FAILURE` e a projeção QW-01 grava prova de escopo.
- resume resiliente valida `body_sha256` antes de tocar o CAS; referência raw
  legada/inválida é preservada para diagnóstico, classificada como corrupção
  local e somente sua página é reprocessada, com `pages_reprocessed` e
  `local_corruption_count` explícitos;
- reconciliação live conta inserts e skips como linhas duravelmente tratadas;
  `fetched != persisted + rejected` força `PARTIAL` como corrupção local;
- o budget de convergência limita somente a passagem adicional por drift; não
  invalida uma primeira paginação longa cujo total permaneceu estável;
- o artifact publica `counts_reconciled` e não pode divergir do predicado que
  autorizou `completed`.

O freshness SLO não foi relaxado. O soak foi endurecido para p95 `<=24h`.

## Validação local pré-PR

- 244 testes focais/regressão passaram após rebase sobre #465, incluindo a
  integração PostgreSQL real, replay, interrupção/restart e health cascade;
- migration 100 foi aplicada e a segunda execução confirmou idempotência
  (`applied=0`, `skipped=102`);
- Ruff, `py_compile`, validação dos unit files, política de artifacts,
  reviewability e varredura de padrões de segredo passaram;
- a primeira suíte canônica ampla parou depois de 3.879 passes e 122 skips em
  `test_issue_246_launch_spine_is_idempotent_across_runs`; o mesmo teste passou
  isolado e o arquivo inteiro passou 4/4. Um segundo passe completo terminou
  verde: 5.741 passed, 235 skipped, 11 deselected, em 891,29 s. CI verde no HEAD
  exato continua obrigatório antes de merge;
- CodeRabbit CLI não está instalado neste ambiente, portanto esse gate deve ser
  executado pela integração do PR. Ausência da ferramenta local não é aprovação.

## Primeira janela real — recusada

O PR #467 executou 28 checks verdes no SHA `93a0e1356e0375e91c740fe44332ede79e04d4cd`.
Esse SHA foi implantado de forma controlada em `ec-prod`, com backup em
`/var/lib/extra-consultoria/backups/incident-458-20260823T041214Z` e migration
100 aplicada. A execução `73a4d87e93574f11a040f662ab66b9fe` produziu:

- run `contracts-90d-20260823T041311Z-0d90e1daec`;
- janela fechada `20260816_20260822`, `query_kind=update`;
- 118/118 páginas, 118 tentativas, zero retries, zero páginas reprocessadas e
  zero page errors;
- 58.889 transformados, 59 inserts, 58.830 skips, duração 1.437,6 s;
- total do banco 4.618.839 -> 4.618.898.

A janela foi **recusada** antes de health/soak porque o artifact publicou
`status=success` ao mesmo tempo que `population_drift` declarou `persisted=0`,
`ok=false` e `decision=retry`. Causa residual: o runner não alimentava inserts +
skips no acumulador e aplicava o limite de 90 s de uma passagem de convergência
à duração total do crawl estável. Evidência sanitizada permanece em
`/var/lib/extra-consultoria/incidents/458/20260823T041303Z`. Timers e soak não
foram promovidos com base nesse run.

## Janela real aceita e auditoria de admissão

No SHA `02b0b415bdcbdbb20ad5aa3719bae6bf3e7b7aad`, aprovado por 28/28 checks
do PR #467 e implantado exatamente no `ec-prod`, a invocation systemd
`2e11041ec0074206972cd4208098b9a2` executou o run
`contracts-90d-20260823T075501Z-89f5f4bbd8`:

- janela fechada 2026-08-16..2026-08-22 via `contratos/atualizacao`;
- 118/118 páginas, 128 tentativas, 10 retries, zero erro residual e zero página
  suprimida;
- 58.851 transformados, zero inserts e 58.851 skips idempotentes;
- duração 1.727,9 s, reconciliação de população verdadeira e max age 0,019 h.

A janela de contratos foi aceita, mas o soak não foi iniciado: o dual gate
continuou honestamente `FAIL` (0/1.093 em ambas as capabilities) e o worker
`extra-crawl-pncp` terminou com exit 2. A auditoria do worker encontrou 24
checkpoints `normalized` apontando para o layout raw legado, todos com o mesmo
payload hash mas sem envelope CAS. O erro é local/permanente e reproduzido pelo
teste `test_completed_pncp_page_with_missing_cas_body_is_reprocessed`; não é
um timeout ou contrato upstream. Depois do reparo, o primeiro ciclo deve
reportar quantos desses checkpoints foram reprocessados e só pode ficar verde
quando DB, evidence, watermark e freshness concluírem.

O primeiro ciclo pós-reparo (`resilient-local-20260823T084549Z-1c34f4d6b2`,
invocation `266dbc76f5a641e49719182ddc4c61e4`) confirmou 24/24 páginas
reprocessadas, sete janelas satisfatórias, 539 registros projetados,
`pending_checkpoints=0` e duração 527,46 s. Mesmo assim, seu `healthy` foi
**recusado** porque `pending_dlq=1`: uma falha sistêmica antiga de persistência
em 2026-08-01 não tinha checkpoint e, portanto, nunca entrava no replay. O
runner passou a incluir DLQs sistêmicas no conjunto oldest-first, reconciliar o
scope legado apenas após sucesso equivalente e degradar enquanto qualquer DLQ
do source permanecer pendente. DLQ record-level poison não vira replay amplo.

## Janela controlada pós-deploy

Pré-condições: PR/CI verdes, SHA exato aprovado e deploy concluído. Não usar
`--reset-checkpoint`; não apagar estado. Salvar a saída pesada como artifact.

```bash
ssh ec-prod 'bash -s' <<'EOF'
set -eu
cd /opt/extra-consultoria
set -a; . ./.env; set +a
.venv/bin/python -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
systemctl daemon-reload
systemctl start pncp-contracts.service
journalctl -u pncp-contracts.service --since "10 minutes ago" --no-pager
.venv/bin/python -m scripts.ops.pncp_contract_freshness \
  --live --json --health --output /var/lib/extra-consultoria/output/pncp-contract-freshness-458.json
EOF
```

Aceite da janela: `query_kind=update`, `range_end=D-1`, todas as páginas
tentadas, retries/reprocessadas enumeradas, `windows_partial=0`,
`windows_failed=0`, `page_errors=0`, inserts/skips/duração presentes e idade
máxima `<=24h`. Uma execução verde é apenas evidência before/after, não `PROVEN`.

## Início e acompanhamento do soak #248

Somente após a janela acima, health cascade, alert ledger e dual coverage
passarem com o mesmo SHA:

```bash
ssh ec-prod 'systemctl start extra-contracts-soak.service && \
  systemctl status extra-contracts-soak.service --no-pager'
```

O primeiro start cria `soak_epoch_started_at`; não há preenchimento retroativo.
Durante sete dias, o rollup precisa manter `contracts_freshness_p95_ok=true`,
`contracts_freshness_p95_hours<=24`, coverage >=95% com denominador/as_of e
zero critical units. Estado durante a janela: `IMPLEMENTED + SOAK_ACTIVE`, gate
aberto. Qualquer mudança invalidante de SHA/config/policy reinicia a época.

## Rollback

Rollback é para código/unit/migration, nunca para dados ingeridos:

1. parar `pncp-contracts`, `extra-crawl-pncp`, `coverage-report`,
   `extra-health-check`, `extra-check-alerts` e `extra-contracts-soak` antes de
   trocar o SHA;
2. retornar ao SHA anterior conhecido e reinstalar os unit files anteriores;
3. `daemon-reload`, iniciar timers e confirmar que health permanece fail-closed;
4. migration 100 pode permanecer (é compatível para trás); se reversão SQL for
   exigida, restaurar o CHECK anterior apenas depois de provar que não existem
   linhas `PERSIST_FAILURE`;
5. preservar checkpoint e artifacts; nunca truncar nem resetar para obter verde;
6. marcar o soak inválido e iniciar nova época somente depois da nova correção.

## Evidência antes/depois

Antes: fixture `errors-2`, journal e unit audit descritos acima. Depois local:
testes unitários/replay/restart/health cascade. Depois real: a janela aceita
está registrada acima. `soak_epoch_started_at` permanece
**PENDENTE/NOT_STARTED**; não preencher até worker, truth gate, backup/restore e
reboot recovery passarem no SHA/policy fixados.
