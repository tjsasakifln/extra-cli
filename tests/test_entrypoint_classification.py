"""ARCH-RESET PR C — entrypoint classification contract."""
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
    # competing surfaces must not be product_canonical
    for row in classes.get("legacy_composite", []) + classes.get("diagnostic", []):
        assert row.get("make") != "extra-weekly"


def test_makefile_has_verify_and_extra_weekly() -> None:
    mk = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^extra-weekly:", mk, flags=re.M)
    assert re.search(r"^verify:", mk, flags=re.M)
    assert "scripts.ops.weekly_cycle" in mk
    assert "PRODUCT CANONICAL" in mk or "product_canonical" in mk
    assert "LEGACY composite" in mk or "legacy_composite" in mk


def test_engineering_verify_not_listed_as_product() -> None:
    data = yaml.safe_load((ROOT / "docs/canonical-entry-points.yaml").read_text(encoding="utf-8"))
    eng = {r.get("make") for r in data["entrypoint_classification"]["engineering"]}
    assert "verify" in eng
    prod = {r.get("make") for r in data["entrypoint_classification"]["product_canonical"]}
    assert "verify" not in prod
