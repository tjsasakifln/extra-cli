# Evidence — remove empty DoD orphan + skip in ranking

**Story:** ROI-cand-dyn-slice-ac8b6e76a7b2
**Cycle:** cyc-2026-07-18T131002Z

## Action
- Removed empty `- [ ]` line at former DOD.md:1401 (no requirement text)
- `generate_dynamic_candidates` skips blank item text so empty markup cannot become ranking[0]

## Explicit
- Not a fake DoD [x] flip — invalid empty checkbox deleted
- Not claiming LOCAL_READY / coverage
