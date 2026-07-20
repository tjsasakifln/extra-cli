"""ARCH-RESET recovery — entrypoint classification contract (from PR #56, adapted)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_product_canonical_is_extra_weekly_only() -> None:
    data = yaml.safe_load((ROOT / "docs/canonical-entry-points.yaml").read_text(encoding="utf-8"))
    assert data["product_canonical_command"] == "extra-weekly"
    assert data["product_canonical_module"] == "scripts.ops.weekly_cycle"
    classes = data["entrypoint_classification"]
    product = classes["product_canonical"]
    assert len(product) == 1
    assert product[0]["make"] == "extra-weekly"
    for row in classes.get("legacy_composite", []) + classes.get("diagnostic", []):
        assert row.get("make") != "extra-weekly"


def test_makefile_has_verify_weekly_and_extra_weekly() -> None:
    mk = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^extra-weekly:", mk, flags=re.M)
    assert re.search(r"^verify-weekly:", mk, flags=re.M)
    assert "scripts.ops.weekly_cycle" in mk


def test_engineering_verify_not_listed_as_product() -> None:
    data = yaml.safe_load((ROOT / "docs/canonical-entry-points.yaml").read_text(encoding="utf-8"))
    eng = {r.get("make") for r in data["entrypoint_classification"]["engineering"]}
    assert "verify-weekly" in eng
    prod = {r.get("make") for r in data["entrypoint_classification"]["product_canonical"]}
    assert "verify-weekly" not in prod
    assert data["engineering_verify_command"] == "verify-weekly"
