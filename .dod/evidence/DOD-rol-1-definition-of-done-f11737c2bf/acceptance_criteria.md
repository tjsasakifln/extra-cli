# DOD-rol-1-definition-of-done-f11737c2bf

**Alias:** `CMI-10.2-08`

**Text:** Distribuição por setor ou tipo de objeto.

**Weight:** 3

**Given** the CMI operational package on SHA `b15f8f0de3cd18f8a5bb5d4ff0cf0d99702a02bf`
**When** `python3 -m scripts.ops.cmi_item_proofs --item CMI-10.2-08` with REQUIRE_REAL_DB=1
**Then** exit 0 and item-specific assertions pass.

**Package:** `artifacts/campaigns/CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01/final-package/`
