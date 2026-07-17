# Requirements — Coverage (atualizado 2026-07-17)

## Propósito
Contrato multi-métrica de cobertura (ADR-018) + states + multi-source + commercial status.

## RFs principais
- RF-COV-01 Emitir M1–M5 com denominador fixo 1093 🟢
- RF-COV-02 Dual-headline M1 comercial × M2 operacional 🟢
- RF-COV-03 List identity covered/uncovered 🟢
- RF-COV-04 Métrica sem evidência → not_ready/0 🟢
- RF-COV-05 satisfactory só com predicados mig 054 🟢
- RF-COV-06 commercial_status classificar sem overclaim 🟢
- RF-COV-07 multi_source_coverage a partir de artefatos de sessão 🟢

## NFRs
- Fail-closed, as_of + git_sha em JSON de métrica, testes adversariais obrigatórios

## Baseline carimbada
- M1 116/1093 · M2 strict 0/1093 (2026-07-17)
