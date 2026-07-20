# Spike OCDS — Decision

| Field | Value |
|-------|--------|
| Spike | PR D `spike/ocds-semantic-mapping` |
| Result | **`ADOPT_AS_REFERENCE`** (export layer optional) |
| Reject | Physical OCDS model · Kingfisher as core ingestion |
| License | OCDS open standard; no new production dependency required |
| DOD impact | Documentation / interoperability; no coverage % claim |

## Benchmark

| Check | Result |
|-------|--------|
| Field matrix ≥30 concepts | Yes (36 rows; 28 mapped, rest gap) |
| Sample package export | Yes |
| Structural validation | Pass |
| Strict release-schema (1.1.5) | Expected fail with `extra:*` / local status — documented |
| Round-trip essential bid fields | Pass (existing tests) |

## Commands

```bash
python3 -m scripts.ocds_bridge.export_sample \
  --out docs/ops/campaigns/ARCH-RESET-2026-07-20/spikes/OCDS/sample-release-package.json \
  --schema /path/to/release-schema.json   # optional

python3 -m pytest tests/test_ocds_bridge_mapping.py tests/test_ocds_spike_validate.py -q --tb=short --no-cov
```
