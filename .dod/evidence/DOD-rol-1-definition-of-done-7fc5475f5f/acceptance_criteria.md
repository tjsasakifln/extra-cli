# DOD-rol-1-definition-of-done-7fc5475f5f

**Alias:** `CMI-10.1-02`

**Text:** O sistema não afirma conhecer todos os concorrentes quando a fonte não expõe participantes.

**Weight:** 5

**Given** package on SHA `ff9b78a86268e63248694d56a99fcf1a4336a60f` with REQUIRE_REAL_DB=1
**When** `python3 -m scripts.ops.cmi_item_proofs --item CMI-10.1-02 --json`
**Then** exit 0 and item assertions pass.

**Package:** `artifacts/campaigns/CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01/final-package/`
