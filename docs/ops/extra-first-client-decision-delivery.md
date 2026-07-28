# Extra Construtora — Primeira Rodada de Decisão B2G

## Comando canônico

```bash
make extra-first-client-delivery \
  WEEKLY_INPUT=/caminho/do/weekly-run-real \
  DELIVERY_OUT=/caminho/externo/ao/git \
  CLIENT_READY_DSN=postgresql://test:test@127.0.0.1:5433/extra_test \
  AS_OF=2026-07-28
```

Requisitos:

- `WEEKLY_INPUT`: diretório de um `extra-weekly` real com `manifest.json` + `checksums.json` válidos
- `DELIVERY_OUT`: fora do Git (pacote cliente não é commitado)
- `CLIENT_READY_DSN`: opcional; apenas DSN isolado (nunca produção)

## Saídas

Ver `00-LEIA-ME.md` no pacote. `human-review.json` inicia `PENDING_HUMAN` — somente Tiago aceita.

## Testes

```bash
make test-extra-first-client-delivery
```

## Observações

- GO é proibido enquanto elicitation crítica do perfil estiver PENDING
- Shortlist vazia com insuficiência explícita é resultado honesto, não “zero de mercado”
- Dossiê sem documentos oficiais → `07-dossie-edital-NOT_AVAILABLE.md`
- PR #133 permanece fora de escopo
