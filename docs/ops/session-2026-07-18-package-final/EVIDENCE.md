# Evidence — ROI-cand-dyn-slice-ec525563e7db (Pacote final)

```bash
python3 -m scripts.ops.deliverable_package_final fixture --out-dir docs/ops/session-2026-07-18-package-final/pack
python3 -m scripts.ops.deliverable_package_final audit-fixture --out docs/ops/session-2026-07-18-package-final/audit-fixture.json
python3 -m pytest tests/test_deliverable_package_final.py -q --tb=short --no-cov
```

- Same run_id PDF+Excel + sidecars
- Reconcile PASS on cut/profile/filters
- Sections + sheets inventory
- Tiago accept PENDING_HUMAN (not auto)
