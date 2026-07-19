# FINAL-REPORT — EXTRA-DECISION-LOOP-01

## O que passou a ser possível

1. Resolver o perfil Extra com hash estável, estados SET/PENDING/NOT_APPLICABLE/REDACTED e `profile_status`.
2. Gerar snapshot de open/upcoming no universo Extra, reconfirmar alvos (acionáveis + top-N), e calcular delta vs snapshot anterior.
3. Decidir por oportunidade com dimensões (`data_confidence`, `client_fit`, `technical_fit`, `commercial_fit`, `operational_fit`, `temporal_fit`), hard blockers e mapeamento PARTICIPAR/REVIEW/NÃO_PARTICIPAR.
4. Exportar/importar labels humanos e calibrar só com amostra suficiente (`PENDING_HUMAN` caso contrário).
5. Rodar `make extra-decision-pack` e obter brief MD+PDF, Excel, CSVs, manifest, checksums reconciliados.

## O que foi comprovado (live)

| Item | Evidência |
|------|-----------|
| Pack E2E em dados reais | `evidence/live-pack/decision_manifest.json` status OK |
| 200 decisões | REVIEW=200, PARTICIPAR=0 (legítimo; sem reconfirm HTTP ok no modo offline + perfil pendente) |
| PDF + Excel mesmo run | `reconcile.json` PASS |
| Profile hash nos artefatos | `profile_status.json` + manifest |
| Fila humana | `human_review_queue.csv` (labels vazios) |
| Testes obrigatórios | 27 passed em `tests/test_decision_loop_v2.py` |

## DOD

Itens candidamente avançáveis como **PARTIAL** com execução real do decision pack (não 95%, não LOCAL_READY). Aceite §15 permanece humano.

## Blockers restantes

- 11 campos críticos do perfil PENDING (elicitation com Tiago/Extra).
- Reconfirmação live HTTP em massa ainda opt-in (modo offline default no evidence pack para não martelar PNCP).
- GO/PARTICIPAR zero até perfil + reconfirm ok — **esperado**, não fabricado.
- Full suite legada fora do escopo.

## Única próxima decisão humana

Revisar o pacote live e registrar em `human-acceptance.md`:

`ACCEPTED` | `ACCEPTED_WITH_LIMITATIONS` | `REJECTED`
