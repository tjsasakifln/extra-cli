# Ledger de suppressions Ruff — #327

Todas as suppressions introduzidas pela campanha são locais, têm justificativa na linha e não
alteram a configuração global do Ruff.

| Regra | Local | Justificativa |
|---|---|---|
| S310 | `.aiox-core/monitor/hooks/lib/send_event.py` (2) | A URL é validada como HTTP(S), com hostname, antes de construir e abrir a request. |
| S602 | `tools/dod_controller.py` | Executor intencional de comandos de aceitação versionados, cujo contrato permite pipes e sintaxe shell. |
| S602 | `squads/extra-dod-roi/scripts/remediate_skeptic_findings.py` | Reexecução intencional dos mesmos comandos de evidência versionados. |
| S603 | `tools/dod_controller.py` (3) | `sys.executable`/git resolvido e argv sem shell. |
| S603 | `squads/extra-dod-roi/scripts/{campaign,canonical_count,cli,enforce_aiox_path,force_next,rebuild_campaign_final,remediate_skeptic_findings,snapshot_state,stale_detect}.py` | Executáveis resolvidos ou `sys.executable`, argv controlado e `shell=False`. |
| S603 | `squads/extra-dod-roi/tests/{test_main_direct,test_squad_smoke}.py` | Testes invocam somente o interpretador corrente e scripts versionados do repositório. |
| S603 | `docs/ops/campaigns/DUAL-CAPABILITY-COVERAGE-TRUTH-01/scripts/check_campaign_stamp_consistency.py` (2) | Git resolvido, argv em lista e sem shell. |

Não foram adicionados ignores globais, exclusões de diretório ou suppressions de arquivo inteiro.
