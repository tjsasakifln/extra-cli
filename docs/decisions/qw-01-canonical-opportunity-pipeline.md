# QW-01 — Pipeline canônico de oportunidades

## Status

Aceita para o quick win QW-01 em 2026-07-13.

## Decisão

`opportunity_intel` é a camada canônica do Radar Auditável. O endpoint oficial PNCP `GET /api/consulta/v1/contratacoes/proposta` é a única fonte operacional selecionada no quick win. As modalidades PNCP 1–19 são escopos de uma mesma fonte; `pncp_publication` não é contado como canal independente.

`pncp_raw_bids` continua sendo a zona raw consolidada e pode alimentar `opportunity_intel` por adaptador/backfill, mas presença nessa tabela não prova cobertura. `scripts/crawl/monitor.py`, `scripts/consulting_readiness.py` e o manifesto legado permanecem disponíveis e são marcados como não canônicos para o radar.

## Motivos

- `opportunity_intel` já possui identidade, proveniência, runs, checkpoints, deduplicação e campos de oportunidade.
- O endpoint de propostas abertas fornece evidência semântica melhor que inferir abertura por recência da publicação.
- Corrigir essa vertical evita alterar todos os crawlers do pipeline multi-source.
- `coverage_evidence` já é o ledger de evidência mais rico. A migration 029 o amplia com escopo, aplicabilidade, paginação, freshness e chave canônica; não é criado um quarto ledger.

## Universo

A população nasce exclusivamente da planilha seed da execução. A chave estável é o hash de `(CNPJ raiz normalizado, município normalizado, razão social normalizada)`. CNPJ raiz sozinho não é único: o root `00394494` ocorre quatro vezes na seed atual. Linhas compostas repetidas recebem um sufixo de ocorrência e permanecem no denominador como duplicidades suspeitas.

A flag `sc_public_entities.raio_200km` não participa da definição da população do radar. Ela pode ser comparada como diagnóstico, mas nunca substituir o snapshot da seed.

## Completude e `success_zero`

Uma run PNCP é completa somente quando todas as modalidades configuradas terminam por uma destas regras:

- página atual alcançou `totalPaginas` informado pela API;
- a API retornou página vazia/HTTP 204 após todas as páginas anteriores válidas;
- sem total informado, uma página válida retornou menos que `tamanhoPagina`.

HTTP 4xx/5xx, timeout, JSON inválido, `max_pages`, limite de registros ou retomada sem completar o escopo produzem `partial`, `error` ou `blocked`. `success_zero` só é projetado por ente após a completude de todas as modalidades.

## Status aberto

O radar aceita apenas:

- registro retornado pelo endpoint de propostas abertas; ou
- registro com `data_encerramento` no futuro, sem estado terminal/suspenso.

Publicação recente, isoladamente, não é evidência de abertura.

## Readiness

- `pncp_monitoring_coverage` é calculada sobre a população canônica dentro do raio, incluindo unresolved no denominador conservador.
- `data_presence` é descritiva e independente.
- Como somente PNCP é selecionado, `overall_channel_readiness` permanece `NOT_READY` neste quick win; não há alegação multicanal.
- Exit code `0` exige todos os gates definidos; `2` significa radar útil com readiness parcial; `1` significa falha técnica.

## Consequências

- O ranking legado `GO/REVIEW/NO_GO` não é usado pelo radar. O QW-01 calcula `data_confidence_score`, `client_fit_score` e `triage_recommendation` separadamente.
- Dados antigos continuam intactos.
- Uma futura vertical poderá tornar uma única fonte complementar operacional e reduzir o gap de canal, sem reabrir o núcleo do radar.
