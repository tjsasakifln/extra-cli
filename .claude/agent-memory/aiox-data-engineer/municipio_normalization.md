---
name: municipio-normalization
description: IBGE code resolution requires Unicode NFKD normalization for Portuguese accented municipality names matching between spreadsheet and BrasilAPI
metadata:
  type: reference
---

When matching municipality names between a spreadsheet (openpyxl) and BrasilAPI responses, Python's `re.sub(r"[^a-z0-9\s]", "", name)` strips accented chars entirely (e.g., "Agrolândia" -> "agrolndia"), causing mismatch with spreadsheet data that has ASCII transliterations ("Agrolandia").

**Fix:** Use `unicodedata.normalize("NFKD", name)` to decompose accented chars, then strip combining diacritical marks (category "Mn") before the regex pass. This produces consistent ASCII keys for matching.

**Matching strategy used (in priority order):**
1. Exact normalized name match
2. Remove connecting words (de, da, do, das, dos) and retry (handles "Balneário de Piçarras" vs "Balneário Piçarras")
3. Remove all spaces and retry (handles "Grão Pará" vs "Graopará")
4. Prefix match on first word as last resort
