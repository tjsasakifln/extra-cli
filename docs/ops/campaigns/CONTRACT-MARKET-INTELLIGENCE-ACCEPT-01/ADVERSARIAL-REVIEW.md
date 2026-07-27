# Revisão adversarial — CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01

Somente leitura sobre o pacote funcional e artefatos de execução.

| attack_id | target | method | result | severity | blocking |
|-----------|--------|--------|--------|----------|----------|
| A01 | orgão disfarçado | scan suppliers-ranking + report_concorrentes provenance | PASS — só winner_identified / from_pncp_supplier_contracts | high | no |
| A02 | ranking = alias contratos | diff colunas competitor-review vs contratos | PASS — roles, win_rate, capacity, limitations distintas | medium | no |
| A03 | linhas vazias | CSV row count / Excel sheets | PASS — material | high | no |
| A04 | market share denom parcial | proof market_share status + population_definition | PASS — complete_population_aggregated | high | no |
| A05 | HHI universo diferente | same conc object | PASS | high | no |
| A06 | estimado como contratado | value_type fields | PASS — valor_contratado only for totals | high | no |
| A07 | ausente→zero | typed_values status MISSING | PASS | high | no |
| A08 | outlier oculto | panels outliers_flagged | PASS | medium | no |
| A09 | heterogêneos agregados | comparability group dims | PASS | medium | no |
| A10 | afirma todos concorrentes | limitations + participant_identified=false | PASS | high | no |
| A11 | win rate sem propostas | reliability win_rate NOT_COMPUTABLE | PASS | high | no |
| A12 | capacidade inferida | capacity_claim HYPOTHESIS | PASS | high | no |
| A13 | deságio inválido | desagio NOT_COMPUTABLE sem par | PASS | high | no |
| A14 | Excel≠JSON | same run_id/code_sha | PASS | medium | no |
| A15 | fonte/data ausente | metadata as_of/source | PASS | high | no |
| A16 | query não-PG | REQUIRE_REAL_DB + RealDict schema | PASS | high | no |
| A17 | tabela fictícia | information_schema pncp_supplier_contracts | PASS | high | no |
| A18 | fixture como mercado live | limitations seed_applied labeled | PASS (honest) | medium | no |
| A19 | claim 95%/LOCAL_READY | claims_scan | PASS | high | no |
| A20 | evidência sem SHA | proof.code_sha | PASS at package time | high | no |

**Veredito:** PASS_FOR_MERGE — nenhum achado alto/crítico explorável remanescente no contrato do pacote.


## Remediation re-check (2026-07-27T23:07:36Z)

- Per-item proofs: 47/47 PASS
- Package code_sha field / executed_sha: `b15f8f0de3cd18f8a5bb5d4ff0cf0d99702a02bf`
- Dishonest `or True` tests removed
- Matrix CLOSED with real evidence paths
