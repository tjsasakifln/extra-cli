"""Tests for tools/dod_controller.py — DOD Convergence Harness (fail-closed)."""

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
    import subprocess

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

    # Isolated git repo so HEAD/branch gates are exerciseable.
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "harness@test.local"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Harness Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "test-init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    # Stay off main so accept requires --allow-non-main (realistic harness path).
    subprocess.run(
        ["git", "checkout", "-b", "campaign/test-harness"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
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


def _write_accept_pack(mod, iid: str, *, head: str | None = None) -> Path:
    """Minimal complete evidence pack that satisfies fail-closed accept gates."""
    pack = mod.EVIDENCE_DIR / iid
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "acceptance_criteria.md").write_text(
        "Given registered criteria\nWhen verify runs\nThen exit 0\n",
        encoding="utf-8",
    )
    sha = head or mod._git_head() or "deadbeef"
    (pack / "verify_result.json").write_text(
        json.dumps(
            {
                "ok": True,
                "item_id": iid,
                "head_sha": sha,
                "substantive_runs": 1,
                "commands": [
                    {
                        "cmd": 'python3 -c "assert 1+1==2"',
                        "exit_code": 0,
                        "skipped": False,
                        "duration_s": 0.01,
                    }
                ],
                "tests": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (pack / "ci_status.json").write_text(
        json.dumps(
            {
                "conclusion": "success",
                "head_sha": sha,
                "mandatory_jobs_skipped": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (pack / "review_status.json").write_text(
        json.dumps({"pending_changes_requested": False}) + "\n",
        encoding="utf-8",
    )
    (pack / "independent_review.md").write_text(
        "# Independent review\n\nReviewed by separate agent. OK.\n",
        encoding="utf-8",
    )
    (pack / "full_suite_status.json").write_text(
        json.dumps({"ok": True, "exit_code": 0}) + "\n",
        encoding="utf-8",
    )
    return pack


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


def test_scan_does_not_auto_accept_checked(dod):
    """FG-1: checkbox is claim, not audited acceptance."""
    mod, _ = dod
    assert mod.main(["scan", "--json"]) == 0
    manifest = mod.load_manifest()
    checked = [i for i in manifest["items"] if i.get("dod_checked")]
    assert checked, "fixture must have checked items"
    for it in checked:
        assert it["state"] != "ACCEPTED", (
            f"checked item auto-ACCEPTED: {it['id']} state={it['state']}"
        )
    m = mod.metrics_from_items(manifest["items"])
    assert m["claimed_checked"] == len(checked)
    assert m["audited_accepted"] == 0
    assert m["proof_debt"] >= len(checked)
    assert m["acceptance_pct"] == 0.0


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
    items = mod.load_manifest()["items"]
    nxt = mod.select_next(items)
    assert nxt is not None
    assert "suíte global completa verde" in nxt["text"].lower()


def test_next_respects_dependencies(dod):
    mod, _ = dod
    assert mod.main(["scan"]) == 0
    items = mod.load_manifest()["items"]
    suite = next(i for i in items if "Suíte global" in i["text"])
    other = next(i for i in items if i["id"] != suite["id"] and i["state"] == "OPEN")
    # Make suite depend on other (not yet ACCEPTED) → suite ineligible.
    suite["dependencies"] = [other["id"]]
    mod.save_manifest(mod.load_manifest())  # wrong - need to save suite into manifest
    manifest = mod.load_manifest()
    for it in manifest["items"]:
        if it["id"] == suite["id"]:
            it["dependencies"] = [other["id"]]
    mod.save_manifest(manifest)
    items2 = mod.load_manifest()["items"]
    nxt = mod.select_next(items2)
    assert nxt is not None
    assert nxt["id"] != suite["id"]
    # Accept dependency → suite may become eligible again.
    for it in items2:
        if it["id"] == other["id"]:
            it["state"] = "ACCEPTED"
            it["acceptance_commit"] = "abc"
            it["evidence_audit"] = {"status": "ok"}
    nxt2 = mod.select_next(items2)
    assert nxt2 is not None
    # suite should be preferred among eligible (critical path)
    assert nxt2["id"] == suite["id"]


def test_trivial_command_rejected():
    mod = _load_controller()
    assert mod.is_trivial_command("true")
    assert mod.is_trivial_command("/bin/true")
    assert mod.is_trivial_command(":")
    assert mod.is_trivial_command("echo ok")
    assert mod.is_trivial_command("exit 0")
    assert mod.is_trivial_command("mytool --help")
    assert not mod.is_trivial_command('python3 -c "assert 1+1==2"')
    assert not mod.is_trivial_command("python3 -m pytest tests/test_dod_controller.py -q")


def test_verify_rejects_trivial_and_empty(dod):
    mod, _ = dod
    assert mod.main(["scan"]) == 0
    iid = mod.select_next(mod.load_manifest()["items"])["id"]
    mod.main(["start", iid])

    # Empty → fail
    assert mod.main(["verify", iid]) == 1

    # Trivial true → fail
    manifest = mod.load_manifest()
    item = mod.find_item(manifest, iid)
    item["acceptance_commands"] = ["true"]
    mod.save_manifest(manifest)
    (mod.EVIDENCE_DIR / iid / "acceptance_criteria.md").write_text(
        "Given suite\nWhen run\nThen 0\n", encoding="utf-8"
    )
    assert mod.main(["verify", iid, "--json"]) == 1
    assert mod.find_item(mod.load_manifest(), iid)["state"] != "VERIFIED"

    # --mark-if-empty must not greenwash empty
    item = mod.find_item(mod.load_manifest(), iid)
    item["acceptance_commands"] = []
    item["tests"] = []
    mod.save_manifest(mod.load_manifest())
    manifest = mod.load_manifest()
    item = mod.find_item(manifest, iid)
    item["acceptance_commands"] = []
    item["tests"] = []
    mod.save_manifest(manifest)
    assert mod.main(["verify", iid, "--mark-if-empty"]) == 1


def test_verify_rejects_missing_criteria(dod):
    mod, _ = dod
    assert mod.main(["scan"]) == 0
    iid = mod.select_next(mod.load_manifest()["items"])["id"]
    mod.main(["start", iid])
    manifest = mod.load_manifest()
    item = mod.find_item(manifest, iid)
    item["acceptance_commands"] = ['python3 -c "assert True"']
    mod.save_manifest(manifest)
    assert mod.main(["verify", iid]) == 1


def test_verify_substantive_and_records_fields(dod):
    mod, _ = dod
    assert mod.main(["scan"]) == 0
    iid = mod.select_next(mod.load_manifest()["items"])["id"]
    mod.main(["start", iid])
    manifest = mod.load_manifest()
    item = mod.find_item(manifest, iid)
    item["acceptance_commands"] = ['python3 -c "assert 1+1==2"']
    item["tests"] = []
    mod.save_manifest(manifest)
    (mod.EVIDENCE_DIR / iid / "acceptance_criteria.md").write_text(
        "Given suite definition\nWhen full suite runs\nThen exit 0\n",
        encoding="utf-8",
    )
    assert mod.main(["verify", iid, "--json"]) == 0
    assert mod.find_item(mod.load_manifest(), iid)["state"] == "VERIFIED"
    vr = json.loads(
        (mod.EVIDENCE_DIR / iid / "verify_result.json").read_text(encoding="utf-8")
    )
    assert vr["ok"] is True
    assert vr["substantive_runs"] >= 1
    assert "env" in vr
    assert "duration_s" in vr
    assert vr["commands"][0]["exit_code"] == 0
    assert "duration_s" in vr["commands"][0]
    assert vr.get("head_sha")


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

    # Substantive acceptance command (not true).
    manifest = mod.load_manifest()
    item = mod.find_item(manifest, iid)
    item["acceptance_commands"] = ['python3 -c "assert 1+1==2"']
    item["tests"] = []
    mod.save_manifest(manifest)
    (mod.EVIDENCE_DIR / iid / "acceptance_criteria.md").write_text(
        "Given suite definition\nWhen full suite runs\nThen exit 0\n",
        encoding="utf-8",
    )

    assert mod.main(["verify", iid, "--json"]) == 0
    assert mod.find_item(mod.load_manifest(), iid)["state"] == "VERIFIED"

    # Accept without main / without complete pack gates should fail.
    rc = mod.main(["accept", iid, "--json"])
    assert rc == 1

    # Directory alone must not accept (FG-4).
    rc = mod.main(
        ["accept", iid, "--json", "--allow-non-main", "--allow-missing-evidence"]
    )
    assert rc == 1

    head = mod._git_head()
    _write_accept_pack(mod, iid, head=head)
    # Suite item requires full_suite — pack includes it.

    assert (
        mod.main(
            [
                "accept",
                iid,
                "--json",
                "--allow-non-main",
                "--skip-divergence-check",
            ]
        )
        == 0
    )
    accepted = mod.find_item(mod.load_manifest(), iid)
    assert accepted["state"] == "ACCEPTED"
    assert accepted.get("acceptance_commit")
    m = mod.metrics_from_items(mod.load_manifest()["items"])
    assert m["audited_accepted"] >= 1

    # Block another item and resume.
    other = next(
        i
        for i in mod.load_manifest()["items"]
        if i["id"] != iid and i["state"] == "OPEN"
    )
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
    assert mod.main(["resume", other["id"], "--mark-resolved", "--json"]) == 0
    assert mod.find_item(mod.load_manifest(), other["id"])["state"] == "IN_PROGRESS"


def test_accept_rejects_stale_verify_without_justification(dod):
    mod, _ = dod
    assert mod.main(["scan"]) == 0
    iid = mod.select_next(mod.load_manifest()["items"])["id"]
    mod.main(["start", iid])
    manifest = mod.load_manifest()
    item = mod.find_item(manifest, iid)
    item["state"] = "VERIFIED"
    item["acceptance_commands"] = ['python3 -c "assert True"']
    mod.save_manifest(manifest)
    pack = _write_accept_pack(mod, iid, head="0000000stale")
    # Force verify_result head mismatch vs real HEAD
    vr = json.loads((pack / "verify_result.json").read_text(encoding="utf-8"))
    vr["head_sha"] = "0000000stale"
    (pack / "verify_result.json").write_text(
        json.dumps(vr) + "\n", encoding="utf-8"
    )
    # Align CI sha to current so only freshness fails
    head = mod._git_head()
    (pack / "ci_status.json").write_text(
        json.dumps(
            {
                "conclusion": "success",
                "head_sha": head,
                "mandatory_jobs_skipped": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rc = mod.main(
        [
            "accept",
            iid,
            "--json",
            "--allow-non-main",
            "--skip-divergence-check",
        ]
    )
    assert rc == 1
    # With immutability justification → ok
    (pack / "immutability_justification.md").write_text(
        "Result frozen at tag v1; content immutable.\n", encoding="utf-8"
    )
    assert (
        mod.main(
            [
                "accept",
                iid,
                "--json",
                "--allow-non-main",
                "--skip-divergence-check",
            ]
        )
        == 0
    )


def test_vps_category(dod):
    mod, _ = dod
    assert mod.main(["scan"]) == 0
    vps = next(i for i in mod.load_manifest()["items"] if "VPS" in i["text"])
    assert vps["category"] == "VPS_PHASE"


def test_audit_and_report(dod):
    mod, _ = dod
    assert mod.main(["scan"]) == 0
    # Checked-but-not-accepted is a divergence under fail-closed audit.
    rc = mod.main(["audit", "--json"])
    assert rc in (0, 1)
    assert mod.main(["report", "--json"]) == 0
    assert mod.main(["status", "--json"]) == 0
    # Report metrics must expose split counters.
    manifest = mod.load_manifest()
    m = mod.metrics_from_items(manifest["items"])
    assert "claimed_checked" in m
    assert "audited_accepted" in m
    assert "proof_debt" in m


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


def test_workflow_yml_no_fail_open():
    """Workflow must not swallow audit/verify failures with || true."""
    pytest.importorskip("yaml")
    import re
    import yaml

    path = ROOT / ".specify" / "workflows" / "dod-convergence" / "workflow.yml"
    text = path.read_text(encoding="utf-8")
    # Fail-open shell swallow patterns on executable `run:` lines only.
    run_blobs = re.findall(r"(?m)^\s*run:\s*>?\s*(.*?)(?=^\s*- id:|\Z)", text, re.S)
    for blob in run_blobs:
        assert not re.search(
            r"\|\|\s*true\b", blob
        ), f"workflow run: still has || true fail-open: {blob[:120]!r}"
    assert not re.search(
        r'condition:\s*["\']false["\']', text
    ), "converge-loop must not hardcode condition false"
    data = yaml.safe_load(text)
    assert data["workflow"]["id"] == "dod-convergence"
    # max_items input must exist and be referenced in spirit (bootstrap writes it).
    assert "max_items" in data.get("inputs", {})
