# ADR-035 — Universo integral e GO do piloto CONFENGE

**Status:** Proposed
**Date:** 2026-08-10
**Capability:** CONFENGE commercial activation

## Context

Os pacotes de fechamento misturavam três denominadores distintos: todos os fornecedores presentes no histórico contratual, as empresas classificadas para o ICP de construção e a reserva de contatos `EMAIL_SEND_READY`. Snapshots do mesmo dia registraram 48.748 construction-eligible e 8.348/8.382 `TARGET_CONFIRMED`, enquanto o emissor reutilizava constantes e tratava a reserva de 900 como bloqueio do piloto. A publicação de evidência também alterava o HEAD e provocava PRs sucessivos de SHA rebind.

## Decision

1. `confenge.universe_manifest.v2` é o contrato canônico do universo e fecha contratos lidos, roots observados, roots materializados e todas as classes de target-fit na mesma transação PostgreSQL `REPEATABLE READ`. O manifesto registra o snapshot transacional, o watermark CDC e a derivação explícita do universo comercial de construção.
2. `CONFIRMED`, `PROBABLE`, `INSUFFICIENT` e `OUT_OF_SCOPE` permanecem no ledger. Estado de contato ou DNC altera elegibilidade de envio, nunca o histórico nem o denominador observado.
3. Top-N, auditorias e hot sets são subsets de validação/operação. Não podem limitar scan, classificação, materialização ou reconsideração.
4. `confenge.go_no_go.v2` separa `UNIVERSE_HEALTH`, `PILOT_QUALITY`, `PILOT_GO` e `NATIONAL_RESERVOIR_HEALTH`.
5. O piloto pode receber GO abaixo de 900 quando o universo está reconciliado, os gates técnicos passam, o Top-20 foi revisado e ao menos 10 leads foram aprovados por humano atribuível.
6. Mesmo após GO, Warmbly permanece `PAUSED_MANUAL_START`, e-mail apenas, WhatsApp desligado e 10 envios/h até comando explícito de Tiago.
7. `evaluated_code_sha` identifica o código provado; `evidence_publication_sha` identifica somente a publicação de ponteiros. A segunda identidade não invalida a primeira.

## Consequences

- Ausência ou inconsistência do manifesto bloqueia o GO; baixa reserva não.
- Decisões humanas são append-only e sobrevivem à regeneração do pacote.
- Dumps e linhas completas permanecem fora do Git conforme ADR-020; o PR carrega somente código, testes e documentação leve.
- Os números 48.748, 8 mil e 900 são evidências/targets com semânticas próprias, nunca constantes de universo.

## Acceptance

- Igualdade de conjuntos/contagens e ausência de truncamento testadas.
- Caso ESR `<900`, Top-20 revisado e 10 aprovados produz GO com dispatch pausado.
- Subsets não alteram nenhum denominador do manifesto.
