"""Public campaign manifesto for CONFENGE-EXTRA-FRESH-COHORT-PRODUCTION-HANDOFF-01 stays redacted.

Drives the real campaign artifact plus the shipped outreach schema constant.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.warmbly_bridge import SCHEMA_OUTREACH

CAMPAIGN = Path("docs/ops/campaigns/CONFENGE-EXTRA-FRESH-COHORT-PRODUCTION-HANDOFF-01")

_FORMATTED_CNPJ = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
_BARE_CNPJ = re.compile(r"(?<![0-9A-Fa-f])\d{14}(?![0-9A-Fa-f])")
_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PHONE = re.compile(r"\(?\d{2}\)?\s*\d{4,5}[-\s]?\d{4}")


def _campaign_text() -> str:
    parts: list[str] = []
    for path in sorted(CAMPAIGN.glob("*")):
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_fresh_cohort_manifest_redacted_and_complete() -> None:
    assert CAMPAIGN.is_dir()
    manifest_path = CAMPAIGN / "manifest.json"
    handoff_path = CAMPAIGN / "HANDOFF.md"
    assert manifest_path.is_file()
    assert handoff_path.is_file()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["campaign_id"] == "CONFENGE-EXTRA-FRESH-COHORT-PRODUCTION-HANDOFF-01"
    assert manifest["status"] == "DONE"
    assert manifest["result"] == "EXTRA_FRESH_COHORT_PRODUCED_AND_HANDED_OFF"
    assert "READY_FOR" not in str(manifest["result"])
    assert manifest["auto_send"] is False
    assert manifest["REAL_EMAIL_SENT"] is False
    assert manifest["smtp"] == "none"
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["feed_sha256"])
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["code_sha"])
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["executed_sha"])
    assert manifest["schema_versions"]["outreach_schema"] == SCHEMA_OUTREACH

    # The cohort is bounded and never padded: N is whatever the real run yielded.
    members = manifest["member_count"]
    assert isinstance(members, int)
    assert 0 < members <= 50
    dist = manifest["route_class_distribution"]
    assert dist["PROBABILISTIC_OR_RISKY"] == 0
    assert sum(dist.values()) == members
    assert manifest["warmbly_import"]["leads_processed"] == members
    assert manifest["warmbly_import"]["errors"] == 0
    assert manifest["warmbly_import"]["auto_send_enabled"] is False
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["warmbly_cohort"]["cohort_hash"])
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["warmbly_cohort"]["recipient_set_hash"])
    funnel = manifest["funnel"]
    assert funnel["double_preferred"] == 0
    assert funnel["preferred_initial"] >= members
    for key in (
        "accounts_considered",
        "official_domain",
        "any_public_email",
        "DIRECT_PERSON",
        "ROLE_OR_DEPARTMENT",
        "GENERIC_COMPANY",
        "PUBLIC_COMPANY_FREEMAIL",
        "RISKY",
        "controlled_eligible",
        "preferred_initial",
        "no_email",
        "no_domain",
        "blocked",
        "suppressed",
        "double_preferred",
        "yield",
        "as_of",
    ):
        assert key in funnel, key

    text = _campaign_text()
    assert _FORMATTED_CNPJ.search(text) is None
    assert _BARE_CNPJ.search(text) is None
    assert _EMAIL.search(text) is None
    for line in text.splitlines():
        stripped = line.strip().strip("`|,")
        if re.search(r"[0-9a-f]{40}", stripped, re.I):
            continue
        assert _PHONE.search(line) is None, line
    assert "READY_FOR_COHORT_INPUT" not in text
    assert "READY_FOR_CONTROLLED_EMAIL_COHORT_INPUT" not in text
