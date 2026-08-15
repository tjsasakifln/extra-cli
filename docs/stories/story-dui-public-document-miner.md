# Story: Miner de documentos públicos com provenance (DUI)

**Status:** InReview  
**Risco:** STANDARD  
**ID:** DUI-DOC-MINER-01

## Problema

#392 encontra pessoa nomeada e domínio, mas poucos e-mails nominais chegam a identidade comprovada. Documentos públicos (contratos, atas, editais, ART/RRT) ligam pessoa ↔ empresa ↔ e-mail de forma auditável e hoje o provider `official_documents` só fazia skip.

## Valor

Fonte isolada e aditiva: `empresa/CNPJ → documento público → pessoa/cargo → e-mail observado → provenance → associação candidata`. Não promove `EMAIL_VALIDATED`.

## Escopo IN

- Módulo `scripts/decision_unit_intelligence/contact_discovery/public_documents.py`
- Wiring aditivo em `OfficialDocumentsProvider` + `default_providers` + CLI `mine-docs`
- Associação só estrutural; reason codes `DOC_*`; fixtures adversariais
- Canário Track A (ou falha honesta de ambiente)

## Escopo OUT

- Crawler HTML, query planner, pattern inference, identidade de #392
- Batch #393, SearXNG #394 (apenas consumo)
- Warmbly, web-cfg, SmartLic, breach/leak, CPF/telefone pessoal

## AC

1. Given documento com assinatura nome+cargo+e-mail, when o miner roda, then `DOC_IDENTITY_ASSOCIATED` + `DOC_EMAIL_OBSERVED` e nenhum `EMAIL_VALIDATED`.
2. Given tabela ambígua / contador / documento antigo / consórcio / holding / homônimo / genérico / ilegível / empresa errada, then o reason code do fixture.
3. Given política canônica vigente, then evidência documental não vira `EMAIL_VALIDATED` sozinha (`OBSERVED_IN_PUBLIC_DOCUMENT` ≠ `CURRENT_IDENTITY_PROVEN`).

## DoD

Fonte aditiva, provenance por campo, 0 identidade inventada, stale/ambiguity explícitos, canário 30 ou ENVIRONMENT_LIMITED, delta publicado.
