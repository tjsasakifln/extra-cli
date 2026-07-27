# DOD-rol-1-definition-of-done-a9b1b6e0c3

**Alias:** `CMI-11.1-14`

**Text:** Valores de objetos heterogêneos não são agregados sem classificação adequada.

**Weight:** 5

**Given** package on SHA `ff9b78a86268e63248694d56a99fcf1a4336a60f` with REQUIRE_REAL_DB=1
**When** `python3 -m scripts.ops.cmi_item_proofs --item CMI-11.1-14 --json`
**Then** exit 0 and item assertions pass.

**Package:** `artifacts/campaigns/CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01/final-package/`
