# DOD-rol-1-definition-of-done-f2cc2a2ae5

**Alias:** `CMI-10.2-20`

**Text:** O relatório distingue métricas prontas, parciais e indisponíveis.

**Weight:** 5

**Given** the CMI operational package on SHA `b15f8f0de3cd18f8a5bb5d4ff0cf0d99702a02bf`
**When** `python3 -m scripts.ops.cmi_item_proofs --item CMI-10.2-20` with REQUIRE_REAL_DB=1
**Then** exit 0 and item-specific assertions pass.

**Package:** `artifacts/campaigns/CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01/final-package/`
