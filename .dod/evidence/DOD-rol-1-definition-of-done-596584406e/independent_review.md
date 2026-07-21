# Independent adversarial review — O golden path pode ser executado em ambiente limpo.

| Field | Value |
|-------|-------|
| **Item** | `DOD-rol-1-definition-of-done-596584406e` |
| **Requirement (DOD.md L918)** | O golden path pode ser executado em ambiente limpo. |
| **Reviewer** | adversarial-qa-continue-03 |
| **Reviewed at (UTC)** | 2026-07-21T23:55:00Z |
| **main_sha (spawn)** | `a1bf947ddcfa011dc072f16afb0cfd736c7a823c` (or current HEAD) |
| **Impl** | PR #96 (merged) · `scripts/ops/golden_clean_env.py` · `tests/test_golden_clean_env.py` |
| **Verdict** | **PASS_FOR_ACCEPT** |

## Scope honesty (critical)

This item is **foundation clean-env for golden path**: empty disposable PostgreSQL → DROP/CREATE → migrations → seeds → `scripts.golden_path` bootstrap path with documented skips for live crawl/freshness.

**MUST NOT** be used to accept:

| Claim / DOD item | Why out of scope |
|------------------|------------------|
| `LOCAL_READY` (§35.1) | Explicitly forbidden in report `claims.forbidden` |
| 95% coverage / recall | Coverage on proof run is `num=0 pct=0.0` |
| Full live crawl on clean DB | Foundation uses `--skip-sources` / `--skip-freshness` / `--allow-zero` |
| Install-wide clean env (`2b84ce6e0c` L535) | Separate §5.1 item (deps + project install) |
| Domain reports (editais/contratos/concorrentes/valores) | Generic panorama Excel/PDF only; domain items remain OPEN |
| Snapshot integrity 100% | Snapshot step **fails** on empty `pncp_raw_bids` (expected without sources) |

Campaign AC (`docs/ops/campaigns/.../critical-path.md` AC-1..AC-5) authorizes crawl/freshness skip **only** for documented foundation bootstrap.

## Falsification attempts

| # | Attack | Result |
|---|--------|--------|
| F1 | **`--skip-sources` means this is not “golden path”** | **Does not falsify.** Flag help: “clean-env foundation / offline proof only”. `classify_status(..., skip_sources=True)` returns `success/0` by design. AC-2 explicitly allows documented foundation skips. Live fontes/persist/freshness are **separate** §12.1 items already ACCEPTED. Residual: not a full online GP on empty DB — honesty gap only if someone claims full crawl. |
| F2 | **Proof reuses prior DB volume / host theater** | **Falsified.** `recreate_db`: `term_exit=0`, `drop_exit=0`, `create_exit=0`, DSN `…/extra_clean_c03`. Migrations `applied=61 skipped=0` (fresh schema, not re-run-only). Seeds insert 2085 entities. Post-GP coverage `numerator=0` and snapshot `current_count=0` consistent with empty bid state. Guard: without `--confirm-drop` exit `3` (test + code). |
| F3 | **Exit 0 without migrations + seeds + GP** | **Falsified.** Report `ok=true` requires `recreate_db.ok ∧ migrations.ok ∧ seeds.ok ∧ public_tables≥5 ∧ golden_path.ok`. Evidence: migrations exit 0, seeds entities/aliases exit 0, `public_tables=76`, `golden_path.exit=0`, Status SUCCESS run `gp-20260721-200931`. |
| F4 | **Hidden LOCAL_READY / 95% claim** | **Falsified.** `claims.forbidden = ["LOCAL_READY", "95% coverage from clean env alone"]`. Limitations list documents empty-source foundation. Coverage in proof run is 0%, not 95%. |
| F5 | **Dry-run alone sold as accept** | **Not sold.** Pack has live `clean-env-report.json` with `dry_run=false` and real DROP/CREATE + GP. Dry-run is unit-tested separately; AC-4 forbids dry-run-only accept. |
| F6 | **Snapshot FAIL proves GP broken on clean env** | **Does not falsify this item.** Empty `pncp_raw_bids` cannot reconcile; step status `fail` but overall exit remains 0 under foundation flags. Snapshot reconciliation is a **different** ACCEPTED item (`c73b1150d6`) requiring data. Not a threshold weaken for *this* literal. |

## Evidence accepted

| Artifact | What it shows |
|----------|----------------|
| `clean-env-report.json` | `ok=true`, recreate/migrations/seeds, `public_tables=76`, GP exit 0, forbidden claims |
| `proof.json` | Tool + limitations (sources skipped offline; no LOCAL_READY/95%) |
| `acceptance_criteria.md` | G/W/T aligned with campaign AC-1..AC-5 |
| `pytest.txt` | 8 passed (suite includes clean-env help/dry-run/refuse + real_db path when available) |
| `tests/test_golden_clean_env.py` | Refuse without confirm; dry-run; confirm-drop asserts recreate/migrations/tables/ok |
| `scripts/ops/golden_clean_env.py` | Controlled DROP/CREATE, migrations, seeds, GP with documented flags |
| Ledger run `gp-20260721-200931` | skip-sources/freshness; spreadsheet pass (1093); coverage 0; snapshot fail empty; Excel/PDF generated; status success |

## Residuals (non-blocking)

1. **Not full live crawl on clean DB** — intentional foundation; re-run with sources is operator follow-up, not this DOD checkbox.
2. **`snapshot_reconciliation` fails under empty sources** — expected; does not fail foundation exit code.
3. **Ledger file is multi-run append** — earlier entries in `ledger-clean-extra_clean_c03.json` may predate the successful recreate; authoritative proof run is `gp-20260721-200931` + report.
4. **`pytest.txt` lacks nodeids** — weak packaging; tests file still readable and scoped.
5. **Install-wide ambient limpo** remains OPEN (`2b84ce6e0c`).

## Decision

**PASS_FOR_ACCEPT** — The DOD literal is satisfied as **reproducible golden-path foundation on a freshly created empty database** (migrations + seeds + GP exit 0, destructive guard, no LOCAL_READY/95% claim). Live crawl completeness and project-wide install are explicitly out of scope.
