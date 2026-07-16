# L1.6 — Resume / DLQ / watermark (re-prova)

**Data:** 2026-07-16

## Testes

```bash
pytest tests/test_dlq_sync.py tests/test_watermark_sync.py tests/test_freshness.py tests/test_golden_path_ledger.py -q
```

| Suite | Resultado |
|-------|-----------|
| DLQ/watermark/freshness | 8 passed |
| golden_path ledger | 5 passed |

Capture: `mission-unit.log` / `mission-unit-ledger.log`.
