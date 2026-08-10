# GO / NO-GO

**Terminal:** `EXTERNAL_BLOCKER_REQUIRES_TIAGO`

**FULLY_RECONCILED:** true (513650/513650, ratio=1.0)

**NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY:** false

## Yield proof (process harvest in progress, no Top-N)

| Metric | Value |
|--------|------:|
| CONFIRMED | 8382 |
| Process harvest done | 1102 (13.15%) |
| Process ESR proxy | 24 |
| Yield ESR/attempted | 0.0218 |
| Projected ESR full CONFIRMED | ~182.5 |
| MIN_OPERATIONAL_RESERVE | 900 |
| Projected gap | ~717.5 |

## One action for Tiago

Autorizar fontes públicas adicionais de maior yield (SEI com sessão humana por órgão, portais estaduais/municipais prioritários) e/ou aceitar MIN_OPERATIONAL_RESERVE menor por decisão comercial — projeção de yield processo ~2.2% ⇒ ~183 ESR sobre 8382 CONFIRMED, abaixo de 900.

## Human review (when healthy)

```bash
python -m scripts.confenge.human_review --sample artifacts/confenge/national-commercial-ready/HUMAN-REVIEW-SAMPLE.json --reviewer tiago
```
