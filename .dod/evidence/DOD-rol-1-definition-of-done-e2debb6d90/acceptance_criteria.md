# DOD-rol-1-definition-of-done-e2debb6d90

**Alias:** `CMI-10.1-06`

**Text:** O sistema não trata quantidade de contratos como sinônimo de capacidade técnica.

**Weight:** 5

**Given** package on SHA `ff9b78a86268e63248694d56a99fcf1a4336a60f` with REQUIRE_REAL_DB=1
**When** `python3 -m scripts.ops.cmi_item_proofs --item CMI-10.1-06 --json`
**Then** exit 0 and item assertions pass.

**Package:** `artifacts/campaigns/CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01/final-package/`
