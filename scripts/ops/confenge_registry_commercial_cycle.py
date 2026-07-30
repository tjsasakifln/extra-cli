#!/usr/bin/env python3
"""CONFENGE commercial cycle wrapper with official local registry gates.

Not part of CONFENGE-COMMERCIAL-READY freeze seed surface. Use:

  python -m scripts.ops.confenge_registry_commercial_cycle
  make confenge-commercial-cycle-official

Delegates ranking/export to scripts.ops.confenge_commercial_cycle after:
- fail-closed ACTIVE official registry checks
- optional publish of interest CNPJs into supplier_registry
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main(argv: list[str] | None = None) -> int:
    require_official = os.environ.get("CONFENGE_REQUIRE_OFFICIAL_REGISTRY", "1") not in {
        "0",
        "false",
        "False",
        "no",
    }
    interest_cnpjs: list[str] | None = None
    interest_file = os.environ.get("CONFENGE_OFFICIAL_INTEREST_CNPJ_FILE")
    if interest_file and Path(interest_file).is_file():
        interest_cnpjs = [
            ln.strip()
            for ln in Path(interest_file).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]

    official_precheck: dict = {"ok": False, "reason": "not_evaluated"}
    if require_official:
        from scripts.company_registry.commercial_bridge import (
            fail_closed_commercial_precheck,
            publish_matches_to_supplier_registry,
        )
        from scripts.company_registry.lookup import read_active_pointer

        official_precheck = fail_closed_commercial_precheck(
            candidates=interest_cnpjs,
            top20=None,
            require_top20_full=False,
        )
        if not official_precheck.get("ok"):
            reason = str(
                official_precheck.get("reason") or "BLOCKED_OFFICIAL_REGISTRY_NOT_AVAILABLE"
            )
            print(f"[registry-cycle] BLOCKED reason={reason}", file=sys.stderr)
            out = os.environ.get("CONFENGE_COMMERCIAL_OUT")
            if out:
                Path(out).mkdir(parents=True, exist_ok=True)
                payload = {
                    "status": "BLOCKED",
                    "reason": reason,
                    "official_registry_precheck": official_precheck,
                }
                (Path(out) / "cycle-manifest.json").write_text(
                    json.dumps(payload, indent=2) + "\n", encoding="utf-8"
                )
            return 2

        dsn = os.environ.get("CONFENGE_COMMERCIAL_STATE_DSN") or os.environ.get(
            "LOCAL_DATALAKE_DSN"
        )
        if (
            interest_cnpjs
            and dsn
            and os.environ.get("CONFENGE_PUBLISH_OFFICIAL_REGISTRY", "1")
            not in {"0", "false", "False"}
        ):
            from scripts.commercial_leads.dbutil import connect

            conn = connect(dsn)
            try:
                pub = publish_matches_to_supplier_registry(
                    conn,
                    interest_cnpjs,
                    source="rfb_public_cadastral_via_opencnpj",
                )
            finally:
                conn.close()
            official_precheck["publish"] = {
                "upserted": pub.get("upserted"),
                "stats": pub.get("stats"),
            }
        official_precheck["active_pointer"] = read_active_pointer()
        print(
            "[registry-cycle] official precheck PASS "
            f"release={official_precheck.get('active_official_registry_release')}"
        )

    # Delegate to frozen commercial cycle entry (protected surface untouched)
    from scripts.ops.confenge_commercial_cycle import main as commercial_main

    code = commercial_main(argv)

    # Optional post Top20 gate when interest/top20 available from run-result
    out = os.environ.get("CONFENGE_COMMERCIAL_OUT")
    if require_official and out:
        run_path = Path(out) / "run-result.json"
        if run_path.is_file():
            try:
                from scripts.company_registry.commercial_bridge import (
                    fail_closed_commercial_precheck as post_gate,
                )
                from scripts.company_registry.coverage import compute_coverage

                result = json.loads(run_path.read_text(encoding="utf-8"))
                leads = list(result.get("leads") or [])
                top20 = [
                    str(x.get("cnpj14") or x.get("cnpj") or "")
                    for x in leads[:20]
                    if x.get("cnpj14") or x.get("cnpj")
                ]
                post = post_gate(
                    candidates=interest_cnpjs,
                    top20=top20 or None,
                    require_top20_full=bool(top20),
                )
                cov = compute_coverage(
                    interest_cnpjs or top20,
                    ranking_eligible=interest_cnpjs or top20,
                    top20=top20,
                )
                result["official_registry_precheck"] = official_precheck
                result["official_registry_postcheck"] = post
                result["official_registry_coverage_post"] = cov
                result["active_official_registry_release"] = official_precheck.get(
                    "active_official_registry_release"
                )
                if not post.get("ok"):
                    result["status"] = "BLOCKED"
                    result["reason"] = str(
                        post.get("reason") or "BLOCKED_OFFICIAL_REGISTRY_POST_GATE"
                    )
                    code = 2
                run_path.write_text(
                    json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
                    encoding="utf-8",
                )
                manifest_path = Path(out) / "cycle-manifest.json"
                if manifest_path.is_file():
                    man = json.loads(manifest_path.read_text(encoding="utf-8"))
                else:
                    man = {}
                man.update(
                    {
                        "official_registry_precheck": official_precheck,
                        "official_registry_postcheck": post,
                        "official_registry_coverage_post": cov,
                        "active_official_registry_release": official_precheck.get(
                            "active_official_registry_release"
                        ),
                        "status": result.get("status", man.get("status")),
                        "reason": result.get("reason", man.get("reason")),
                    }
                )
                manifest_path.write_text(
                    json.dumps(man, indent=2, ensure_ascii=False, default=str) + "\n",
                    encoding="utf-8",
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[registry-cycle] postcheck error: {exc}", file=sys.stderr)
                return 2
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
