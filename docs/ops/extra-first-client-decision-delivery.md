# Extra Construtora — Primeira Rodada de Decisão B2G

## Comando canônico

```bash
make extra-first-client-delivery \
  WEEKLY_INPUT=/caminho/do/weekly-run-real \
  DELIVERY_OUT=/caminho/externo/ao/git \
  AS_OF=2026-07-29
```

Requisitos:

- `WEEKLY_INPUT`: diretório de um `extra-weekly` real com `manifest.json` + `checksums.json` válidos e **exit_code=0** para entrega consultiva final
- `DELIVERY_OUT`: fora do Git (pacote cliente não é commitado)
- `CLIENT_READY_DSN`: opcional; apenas DSN isolado (nunca produção)
- Weekly canônico: `make extra-weekly` (ou `python -m scripts.ops.weekly_cycle --strict`)

## Saídas (pacote externo)

| Artefato | Função |
|----------|--------|
| `00-LEIA-ME.md` | Índice e regras de uso |
| `01-resumo-executivo.pdf` / `.md` | Visão para Leonardo + **DECISÕES SOLICITADAS À EXTRA** |
| `02-oportunidades-priorizadas.xlsx` | Shortlist, evidências, intake, baseline sheets |
| `03-decision-ledger.csv` / `.json` | Ledger de GO/REVIEW/NO_GO humano |
| `04-intake-operacional-extra.md` / `.json` | Até 10 perguntas; respostas em branco |
| `05-limitacoes-e-confiabilidade.md` | Freshness, exit code, claims proibidas |
| `06-baseline-mercado-extra.md` / `.json` | Referências históricas (≠ oportunidades atuais) |
| `07-plano-30-dias.md` | Cadência e decisões dos próximos 30 dias |
| `08-roteiro-reuniao.md` | Roteiro kickoff Tiago ↔ Leonardo |
| `09-dossie-edital-*.md` | Deep dive ou `NOT_AVAILABLE` |
| `diagnostico-weekly-source.json` / `.md` | Causa dos bloqueios / funil auditável |
| `shortlist.json` | Shortlist machine-readable |
| `profile-patch-candidate.yaml` | Patch PENDING (não aplicar sem validação) |
| `human-review.json` | Inicia `PENDING_HUMAN` — só Tiago aceita |
| `manifest.json` / `checksums.json` | Integridade |

## Testes

```bash
make test-extra-first-client-delivery
# ou
python3 -m pytest tests/test_extra_first_client_delivery.py -q --tb=line --no-cov
```

## Observações

- GO é proibido enquanto elicitation crítica do perfil estiver PENDING
- Shortlist vazia com insuficiência explícita é resultado honesto, não “zero de mercado”
- Weekly com exit_code 2/3 **não** sustenta declaração de mercado zerado
- PNCP `/contratacoes/proposta`: `dataFinal` é limite superior de encerramento (horizonte default 30 dias)
- Dossiê sem documentos oficiais → `09-dossie-edital-NOT_AVAILABLE.md`
- PR #133 permanece fora de escopo
- Pacote final de referência (2026-07-29): `~/extra-deliveries/EXTRA-FIRST-CLIENT-DECISION-B2G-20260729/`
