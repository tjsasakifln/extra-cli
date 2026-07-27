# DOD-rol-1-definition-of-done-8aae30ee2e

**Alias:** `CMI-11.1-17`

**Text:** Percentis só são calculados sobre amostra comparável.

**Weight:** 5

**Given** package on SHA `ff9b78a86268e63248694d56a99fcf1a4336a60f` with REQUIRE_REAL_DB=1
**When** `python3 -m scripts.ops.cmi_item_proofs --item CMI-11.1-17 --json`
**Then** exit 0 and item assertions pass.

**Package:** `artifacts/campaigns/CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01/final-package/`
