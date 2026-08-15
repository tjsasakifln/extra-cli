# `public_read_v1` margin-defense facts contract

Version: `v1.0.0`
Schema: `public-read-margin-defense/1.0`
Machine-readable twin: [`public-read-margin-defense-v1.json`](public-read-margin-defense-v1.json)

Consumer: `web-cfg / Diagnóstico de Defesa de Margem` (`tjsasakifln/web-cfg#65`)
Wedge: official public-contract facts. No legal conclusion.

## Boundary

SELECT-only / file export of official facts. Not a generic API, not a second
DataLake, not a brand surface. The shipped consumer path is:

```bash
python3 -m scripts.public_read export-margin --payload PATH --out DIR
```

## Honesty

- UNKNOWN stays UNKNOWN. Absence of evidence is never zero.
- Adjustment anniversary / index is KNOWN only from an explicit rule or document.
- Evidence without identity is refused.
- The export never emits right-to-adjust, imbalance, loss, or "should adjust".
