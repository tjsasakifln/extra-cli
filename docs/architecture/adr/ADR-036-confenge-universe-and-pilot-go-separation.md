# ADR-036 — Universo integral e GO do piloto CONFENGE

**Status:** Proposed
**Date:** 2026-08-10
**Capability:** CONFENGE commercial activation

## Context

Os pacotes de fechamento misturavam três populações distintas: todos os fornecedores presentes no histórico contratual, as empresas pertencentes ao setor de construção e o estado comercial mutável de target-fit. A reserva de contatos `EMAIL_SEND_READY` é uma quarta métrica operacional. Contagens de snapshots históricos chegaram a coincidir ou divergir sem provar relação entre os conjuntos; nenhuma delas é constante. A publicação de evidência também alterava o HEAD e provocava PRs sucessivos de SHA rebind.

## Decision

1. `confenge.universe_manifest.v3` é o contrato canônico. Na mesma visão PostgreSQL `REPEATABLE READ`, fecha `SUPPLIER_UNIVERSE`, a dimensão setorial, a população de target-fit e suas materializações. Registra snapshot, timestamp transacional, watermark CDC, queries e hashes integrais dos classificadores.
2. `CONSTRUCTION_UNIVERSE` é derivado exclusivamente de `CONSTRUCTION_CONFIRMED + CONSTRUCTION_PROBABLE`. `NON_CONSTRUCTION` e `SECTOR_INSUFFICIENT_EVIDENCE` fecham a partição setorial. Nenhuma classe `TARGET_*` define pertencimento setorial.
3. `TARGET_CONFIRMED`, `TARGET_PROBABLE_RESEARCH`, `TARGET_INSUFFICIENT_EVIDENCE` e `TARGET_OUT_OF_SCOPE` fecham separadamente `target_fit_population`. `TARGET_INSUFFICIENT_EVIDENCE` é estado reconsiderável, não exclusão. `REFRESH_FAILED` e `RECOMPUTE_REQUIRED` são estados operacionais fora da partição; o manifesto os contabiliza em `target_operational_states`, exige ambos em zero e mantém essas linhas no total materializado para que a soma de classes também denuncie a lacuna.
4. A dimensão setorial e target-fit compartilham CDC/dirty queue, mas possuem materializações e históricos independentes. Enriquecimento contínuo enumera todo `CONSTRUCTION_UNIVERSE`; target-fit, contato, DNC e provenance controlam somente prioridade e envio.
5. Top-N, auditorias, hot sets, Top-20, ESR e a reserva 900 são subsets/métricas de validação ou operação. Não podem limitar scan, classificação, materialização, enriquecimento contínuo ou reconsideração.
6. `confenge.go_no_go.v2` separa `UNIVERSE_HEALTH`, `PILOT_QUALITY`, `HUMAN_ACCEPTANCE`, `PILOT_GO` e `NATIONAL_RESERVOIR_HEALTH`.
7. O piloto pode receber GO abaixo de 900 quando o universo está reconciliado, os gates técnicos passam, o Top-20 foi revisado e ao menos 10 leads foram aprovados por humano atribuível.
8. Mesmo após GO, Warmbly permanece `PAUSED_MANUAL_START`, e-mail apenas, WhatsApp desligado e 10 envios/h até comando explícito de Tiago.
9. `evaluated_code_sha` identifica o código provado; `evidence_publication_sha` identifica somente a publicação de ponteiros. A segunda identidade não invalida a primeira.
10. `scripts.confenge_activation.pilot_go_policy.evaluate_pilot_go` é a única autoridade de decisão terminal; o emissor de pacote apenas coleta gates e delega à política. Emissores anteriores são `SUPERSEDED_NON_TERMINAL`.
11. O rebuild setorial integral lê contratos ordenados por CNPJ-raiz no snapshot, fecha cada raiz uma única vez e publica por staging bounded. `row_batch_size` e `root_batch_size` são controles de I/O/memória, nunca limites de população; checkpoints registram linhas e raízes processadas antes da troca atômica da materialização corrente.
12. Reutilizar `evaluated_code_sha` anterior exige provar que ele é ancestral do tip publicado e que nenhum input protegido mudou no intervalo. Igualdade entre deploy e runtime, isoladamente, não autoriza `sha_bound`.
13. O feed autoritativo para Warmbly transporta `construction_universe_member` explicitamente. Campo ausente ou falso bloqueia envio; target-fit não é proxy para pertencimento setorial.
14. Enriquecimento process-first usa somente CNPJ de estabelecimento observado no datalake. CNPJ montado a partir da raiz não é identidade operacional e permanece pendente até existir representante válido.

## Consequences

- Ausência ou inconsistência do manifesto bloqueia o GO; baixa reserva não.
- Decisões humanas são append-only e sobrevivem à regeneração do pacote.
- Dumps e linhas completas permanecem fora do Git conforme ADR-020; o PR carrega somente código, testes e documentação leve.
- Contagens históricas são exemplos auditáveis, nunca fallbacks operacionais. `MIN_OPERATIONAL_RESERVE=900` permanece meta configurada de escala nacional, não denominador nem gate do piloto controlado.
- A memória residente do rebuild não cresce linearmente com centenas de milhares de raízes; cresce com o lote operacional configurado e com o histórico da raiz corrente.
- Contagens negativas ou não inteiras são diagnóstico inválido; não são normalizadas para zero para produzir reconciliação aparente.

## Acceptance

- Igualdade de conjuntos/contagens e ausência de truncamento testadas.
- Caso ESR `<900`, Top-20 revisado e 10 aprovados produz GO com dispatch pausado.
- Subsets não alteram nenhum denominador do manifesto.
- Uma empresa `CONSTRUCTION_CONFIRMED + TARGET_INSUFFICIENT_EVIDENCE` permanece materializada, enriquecível e reconsiderável.
- Linhagem de versão/hash divergente bloqueia o fechamento mesmo quando as contagens coincidem.
- Ausência de pertencimento setorial explícito, quebra de linhagem do SHA avaliado ou falta de CNPJ observado bloqueiam seus respectivos caminhos operacionais.
