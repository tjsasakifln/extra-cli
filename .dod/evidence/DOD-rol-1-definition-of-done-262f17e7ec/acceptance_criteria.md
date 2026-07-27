# DOD-rol-1-definition-of-done-262f17e7ec

**Alias:** `CMI-11.1-08`

**Text:** O relatório exibe a data de referência.

**Weight:** 3

**Given** package on SHA `ff9b78a86268e63248694d56a99fcf1a4336a60f` with REQUIRE_REAL_DB=1
**When** `python3 -m scripts.ops.cmi_item_proofs --item CMI-11.1-08 --json`
**Then** exit 0 and item assertions pass.

**Package:** `artifacts/campaigns/CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01/final-package/`
