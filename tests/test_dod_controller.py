"""Tests for tools/dod_controller.py — DOD Convergence Harness."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "tools" / "dod_controller.py"


def _load_controller():
    spec = importlib.util.spec_from_file_location("dod_controller", CONTROLLER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dod_controller"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def dod(tmp_path, monkeypatch):
    pytest.importorskip("yaml")
    mod = _load_controller()
    dod_md = tmp_path / "DOD.md"
    dod_md.write_text(
        """# Definition of Done

## 1. Como usar

- [x] Este arquivo está versionado na raiz.
- [ ] Cada item só é marcado como concluído quando existir evidência verificável.

## Atualização comprovada

- [ ] Suíte global completa verde. O workflow marcou skipped.
- [ ] Recall independente e estratificado ≥95%.
- [x] Freshness coverage mensurável. Evidência: `docs/ops/campaigns/ENTITY-FRESHNESS-01/evidence/` · ADR-028.

## 40. VPS

- [ ] Operação contínua em VPS no estágio posterior.
""",
        encoding="utf-8",
    )
    dod_dir = tmp_path / ".dod"
    dod_dir.mkdir()
    (dod_dir / "blockers").mkdir()
    (dod_dir / "evidence").mkdir()
    (dod_dir / "state.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "campaign_id": "TEST",
                "updated_at": "1970-01-01T00:00:00Z",
                "phase": "harness",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "DOD_PATH", dod_md)
    monkeypatch.setattr(mod, "DOD_DIR", dod_dir)
    monkeypatch.setattr(mod, "MANIFEST_PATH", dod_dir / "manifest.yaml")
    monkeypatch.setattr(mod, "STATE_PATH", dod_dir / "state.json")
    monkeypatch.setattr(mod, "LOG_PATH", dod_dir / "log.jsonl")
    monkeypatch.setattr(mod, "BLOCKERS_DIR", dod_dir / "blockers")
    monkeypatch.setattr(mod, "EVIDENCE_DIR", dod_dir / "evidence")
    return mod, tmp_path


def test_stable_ids_independent_of_line(dod):
    mod, tmp_path = dod
    items1 = mod.parse_dod(mod.DOD_PATH)
    # Insert blank lines at top — shift line numbers.
    text = mod.DOD_PATH.read_text(encoding="utf-8")
    mod.DOD_PATH.write_text("\n\n\n" + text, encoding="utf-8")
    items2 = mod.parse_dod(mod.DOD_PATH)
    ids1 = {mod.make_item_id(i.section, i.text) for i in items1}
    ids2 = {mod.make_item_id(i.section, i.text) for i in items2}
    assert ids1 == ids2
    assert all(i.startswith("DOD-") for i in ids1)


def test_scan_preserves_history_and_state(dod):
    mod, _ = dod
    assert mod.main(["scan", "--json"]) == 0
    manifest = mod.load_manifest()
    assert len(manifest["items"]) >= 5
    target = next(i for i in manifest["items"] if "Suíte global" in i["text"])
    target["state"] = "IN_PROGRESS"
    target["history"].append({"at": "t", "event": "manual", "detail": "keep"})
    mod.save_manifest(manifest)

    assert mod.main(["scan", "--json"]) == 0
    m2 = mod.load_manifest()
    t2 = next(i for i in m2["items"] if i["id"] == target["id"])
    assert t2["state"] == "IN_PROGRESS"
    assert any(h.get("event") == "manual" for h in t2["history"])


def test_next_prefers_full_suite(dod):
    mod, _ = dod
    assert mod.main(["scan"]) == 0
    assert mod.main(["next", "--json"]) == 0
    # capture via select_next
    items = mod.load_manifest()["items"]
    nxt = mod.select_next(items)
    assert nxt is not None
    assert "suíte global completa verde" in nxt["text"].lower()


def test_start_verify_accept_block_resume_flow(dod):
    mod, tmp_path = dod
    assert mod.main(["scan"]) == 0
    items = mod.load_manifest()["items"]
    nxt = mod.select_next(items)
    assert nxt
    iid = nxt["id"]

    assert mod.main(["start", iid, "--json"]) == 0
    item = mod.find_item(mod.load_manifest(), iid)
    assert item["state"] == "IN_PROGRESS"
    assert (mod.EVIDENCE_DIR / iid / "README.md").exists()

    # Register a trivial acceptance command for verify.
    manifest = mod.load_manifest()
    item = mod.find_item(manifest, iid)
    item["acceptance_commands"] = ["true"]
    item["tests"] = []
    mod.save_manifest(manifest)
    (mod.EVIDENCE_DIR / iid / "acceptance_criteria.md").write_text(
        "Given suite definition\nWhen full suite runs\nThen exit 0\n",
        encoding="utf-8",
    )

    assert mod.main(["verify", iid, "--json"]) == 0
    assert mod.find_item(mod.load_manifest(), iid)["state"] == "VERIFIED"

    # Accept without main should fail.
    rc = mod.main(["accept", iid, "--json"])
    assert rc == 1

    # Accept with harness bypasses for unit test of gates path.
    assert (
        mod.main(
            [
                "accept",
                iid,
                "--json",
                "--allow-non-main",
                "--allow-missing-evidence",
            ]
        )
        == 0
    )
    assert mod.find_item(mod.load_manifest(), iid)["state"] == "ACCEPTED"

    # Block another item and resume.
    other = next(i for i in mod.load_manifest()["items"] if i["id"] != iid and i["state"] == "OPEN")
    assert (
        mod.main(
            [
                "block",
                other["id"],
                "--kind",
                "HUMAN",
                "--reason",
                "needs Tiago",
                "--json",
            ]
        )
        == 0
    )
    assert mod.find_item(mod.load_manifest(), other["id"])["state"] == "BLOCKED_HUMAN"
    assert (mod.BLOCKERS_DIR / f"{other['id']}.json").exists()

    rc = mod.main(["resume", other["id"], "--json"])
    assert rc == 1  # still blocked
    assert (
        mod.main(["resume", other["id"], "--mark-resolved", "--json"]) == 0
    )
    assert mod.find_item(mod.load_manifest(), other["id"])["state"] == "IN_PROGRESS"


def test_vps_category(dod):
    mod, _ = dod
    assert mod.main(["scan"]) == 0
    vps = next(i for i in mod.load_manifest()["items"] if "VPS" in i["text"])
    assert vps["category"] == "VPS_PHASE"


def test_audit_and_report(dod):
    mod, _ = dod
    assert mod.main(["scan"]) == 0
    # audit may return 1 on weak evidence; harness still exercises path
    rc = mod.main(["audit", "--json"])
    assert rc in (0, 1)
    assert mod.main(["report", "--json"]) == 0
    assert mod.main(["status", "--json"]) == 0


def test_verify_fails_without_criteria(dod):
    mod, _ = dod
    assert mod.main(["scan"]) == 0
    iid = mod.select_next(mod.load_manifest()["items"])["id"]
    mod.main(["start", iid])
    assert mod.main(["verify", iid]) == 1


def test_unknown_item_exit_2(dod):
    mod, _ = dod
    assert mod.main(["scan"]) == 0
    assert mod.main(["start", "DOD-nope-0000000000"]) == 2
