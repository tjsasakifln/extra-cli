# Review do release candidate — 5–10 minutos

**Campanha:** CLIENT-READY-RECURRING-CONSULTING-CYCLE-01  
**PR:** https://github.com/tjsasakifln/extra-cli/pull/131  
**Terminal técnico:** BLOCKED (só falta o seu aceite)  
**run_id:** `live-pack-20260724-210500-96b1aa13`

## O que o sistema faz agora (um comando)

```bash
make client-ready-consulting-cycle
```

Gera, em PostgreSQL isolado sobre o dump autenticado (~4,44M contratos):

1. Pacote A–E (órgãos, concorrentes, vincendos, valores, editais)  
2. Linkage oportunidade → órgão → contratos → fornecedores + dossiers  
3. PDF + Excel + CSV + JSON reconciliados  
4. Relatório semanal + mensal com deltas  
5. Evidências machine-readable + isolation fail-closed  

## Ordem de leitura sugerida

| # | Arquivo | Por quê |
|---|---------|---------|
| 1 | `pack/executive-summary.md` | Visão em 1 página |
| 2 | `pack/executive-report.pdf` | PDF executivo |
| 3 | `pack/consulting-pack.xlsx` | Abas A–E para reunião |
| 4 | `pack/meeting-support.md` | Roteiro de reunião |
| 5 | `pack/deliverable_e.json` | Editais abertos GO/REVIEW/NO_GO |
| 6 | `dossiers/dossier-opp-*.json` | Investigação por oportunidade |
| 7 | `package-reconciliation.json` | PDF×Excel PASS |
| 8 | `recurrence.json` | Deltas entre ciclos |
| 9 | `non-claims.json` | O que **não** afirmamos |

## Números do RC (isolado)

| Métrica | Valor |
|---------|-------|
| Contratos no snapshot | 4.437.142 |
| População elegível SC | 1.179.237 |
| A | OK |
| B concorrentes defensáveis | 15 |
| C janela 90–180d | 14.750 hits (query completa) |
| D painéis | 6 |
| E editais | 4 |
| Linkage órgãos exact | 12/12 |
| Dossiers | 12 |
| production_touched | false |
| soak_touched | false |

## Como aceitar (somente você)

Edite `user-acceptance.json`:

```json
{
  "status": "ACCEPTED",
  "accepted_by": "Tiago Sasaki",
  "accepted_at": "2026-07-24T…Z",
  "notes": "Pack revisado: utilizável na consultoria Extra"
}
```

Ou rejeite com `"status": "REJECTED"` e notes com o motivo.

Detalhes: `HUMAN-ACCEPTANCE-INSTRUCTIONS.md`.

## O que o agente NÃO pode fazer

- Preencher ACCEPT por você  
- Declarar PASS sem aceite  
- Tocar soak / VPS / produção  

## Depois do ACCEPT

```bash
make client-ready-consulting-cycle
# terminal deve poder ir a PASS se aceite for válido
```

Depois: merge do PR #131.
