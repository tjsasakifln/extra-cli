"""Emission SHA, clock-stripped content hashes, and READY xor BLOCKED.

Drives the shipped git_identity / strip_temporal_for_hash / build_rendezvous_files
entry points. Does not oracle live PNCP hashes.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

from scripts.historical_contract_authority import official_live as official_live_mod
from scripts.historical_contract_authority.freshness import (
    TEMPORAL_HASH_EXCLUSIONS,
    strip_temporal_for_hash,
)
from scripts.historical_contract_authority.official_live import (
    build_rendezvous_files,
    deepen_one_contract_detail,
    git_identity,
    verify_claim_url_hash,
    write_atomic_rendezvous,
)
from scripts.historical_contract_authority.schema import content_hash
from scripts.official_contract_semantics.identity import raw_record_hash_for
from tests.historical_contract_authority.test_aec_singularity_gate import _obs
from tests.historical_contract_authority.test_official_live_handoff import _assemble

REPO_ROOT = Path(__file__).resolve().parents[2]


def _rendezvous(*, producer_commit: str, generated_at: str) -> dict[str, str]:
    ready = _assemble(producer_commit=producer_commit)
    return build_rendezvous_files(
        [ready],
        producer={"repo": "tjsasakifln/extra-cli", "branch": "goal/x", "commit": producer_commit},
        generated_at=generated_at,
        replay_command="replay",
        query_window={"start": "2026-07-19", "end": "2026-08-18"},
        live_meta={"production_write": False, "backfill": False},
        candidate_log=[{"contract_id": "x", "disposition": "entered", "reason": "aec"}],
        tests=[],
    )


def test_git_identity_producer_commit_is_emission_head_sha() -> None:
    """producer_commit is the git SHA of the tree that ran the producer."""
    identity = git_identity(repo_root=REPO_ROOT)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    assert identity["commit"] == head
    assert len(identity["commit"]) == 40
    assert identity["commit"] != ""
    assert identity["branch"] == "goal/authority-singularity-20260818"


def test_git_identity_reads_worktree_head_file_not_later_tip(tmp_path: Path) -> None:
    """A later docs-only tip is not the emission SHA unless that SHA is in HEAD at run time."""
    emission = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    later_tip = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/goal/x\n", encoding="utf-8")
    refs = git_dir / "refs" / "heads" / "goal"
    refs.mkdir(parents=True)
    (refs / "x").write_text(emission + "\n", encoding="utf-8")
    identity = git_identity(repo_root=tmp_path)
    assert identity["commit"] == emission
    assert identity["commit"] != later_tip
    assert identity["branch"] == "goal/x"


def test_generated_at_clock_is_excluded_from_root_and_content_hash() -> None:
    assert "generated_at" in TEMPORAL_HASH_EXCLUSIONS
    first = _rendezvous(producer_commit="abc123", generated_at="2026-08-18T03:00:00Z")
    second = _rendezvous(producer_commit="abc123", generated_at="2026-08-18T04:00:00Z")
    ready_a = json.loads(first["READY.json"])
    ready_b = json.loads(second["READY.json"])
    assert ready_a["generated_at"] != ready_b["generated_at"]
    assert ready_a["root_content_hash"] == ready_b["root_content_hash"]
    manifest_a = json.loads(first["manifest.json"])
    manifest_b = json.loads(second["manifest.json"])
    assert manifest_a["generated_at"] != manifest_b["generated_at"]
    assert manifest_a["content_hash"] == manifest_b["content_hash"]
    dossier_a = json.loads(next(value for key, value in first.items() if key.startswith("dossiers/")))
    stripped = strip_temporal_for_hash({k: v for k, v in dossier_a.items() if k != "content_hash"})
    assert "generated_at" not in stripped
    assert dossier_a["content_hash"] == content_hash(stripped)


def test_producer_commit_is_emission_sha_inside_hashed_provenance() -> None:
    emission = "cccccccccccccccccccccccccccccccccccccccc"
    files = _rendezvous(producer_commit=emission, generated_at="2026-08-18T12:00:00Z")
    ready = json.loads(files["READY.json"])
    manifest = json.loads(files["manifest.json"])
    dossier = json.loads(next(value for key, value in files.items() if key.startswith("dossiers/")))
    assert ready["producer_commit"] == emission
    assert manifest["producer_commit"] == emission
    assert dossier["provenance"]["producer_commit"] == emission
    other = _rendezvous(producer_commit="d" * 40, generated_at="2026-08-18T12:00:00Z")
    other_ready = json.loads(other["READY.json"])
    other_dossier = json.loads(next(value for key, value in other.items() if key.startswith("dossiers/")))
    assert other_dossier["content_hash"] != dossier["content_hash"]
    assert other_ready["root_content_hash"] != ready["root_content_hash"]


def test_ready_xor_blocked_cannot_both_exist(tmp_path: Path) -> None:
    ready_files = _rendezvous(producer_commit="abc123", generated_at="2026-08-18T12:00:00Z")
    assert "READY.json" in ready_files
    assert "BLOCKED.json" not in ready_files
    dest = tmp_path / "ready"
    write_atomic_rendezvous(dest, ready_files)
    assert (dest / "READY.json").is_file()
    assert not (dest / "BLOCKED.json").exists()
    hold = _assemble(insight="", bytes_obtained=False, retrieved_at=None, verified_at=None)
    blocked_files = build_rendezvous_files(
        [hold],
        producer={"repo": "tjsasakifln/extra-cli", "branch": "goal/x", "commit": "abc123"},
        generated_at="2026-08-18T12:00:00Z",
        replay_command="replay",
        query_window={"start": "2026-07-19", "end": "2026-08-18"},
        live_meta={"production_write": False, "backfill": False, "reason_codes": ["no_handoff_ready_dossier"]},
        candidate_log=[],
        tests=[],
    )
    assert "BLOCKED.json" in blocked_files
    assert "READY.json" not in blocked_files
    blocked_dest = tmp_path / "blocked"
    write_atomic_rendezvous(blocked_dest, blocked_files)
    assert (blocked_dest / "BLOCKED.json").is_file()
    assert not (blocked_dest / "READY.json").exists()
    assert not ((dest / "READY.json").exists() and (dest / "BLOCKED.json").exists())
    assert not ((blocked_dest / "READY.json").exists() and (blocked_dest / "BLOCKED.json").exists())


def test_listing_facts_rebind_to_contract_detail_bytes(monkeypatch) -> None:
    """Listing FACTs must hash the contract-specific official record, not a shared page."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    contract_id = "14862788000150-2-000069/2026"
    detail = {
        "numeroControlePNCP": contract_id,
        "objetoContrato": "Pavimentação em Paralelepípedo de 4.710,00 m²",
        "valorGlobal": 719177.48,
        "dataVigenciaInicio": "2026-07-08",
        "dataVigenciaFim": "2027-07-08",
    }
    listing_page = {"data": [detail], "totalRegistros": 175203}
    listing_shifted = {"data": [detail], "totalRegistros": 175204}
    listing_bytes = json.dumps(listing_page, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    shifted_bytes = json.dumps(listing_shifted, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    detail_bytes = json.dumps(detail, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    listing_sha = raw_record_hash_for(listing_bytes)
    detail_sha = official_live_mod.canonical_json_sha256(detail_bytes)
    assert detail_sha is not None
    assert listing_sha != raw_record_hash_for(shifted_bytes)
    assert listing_sha != detail_sha

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            payload = detail_bytes if self.path.startswith("/detail") else listing_bytes
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host = f"http://127.0.0.1:{server.server_address[1]}"
        detail_url = f"{host}/detail/{contract_id}"
        listing_url = f"{host}/consulta?pagina=2"
        monkeypatch.setattr(
            official_live_mod,
            "pncp_contract_urls",
            lambda _cid: {"detail": detail_url, "termos": f"{detail_url}/termos", "arquivos": f"{detail_url}/arquivos"},
        )
        listing = replace(
            _obs(
                contract_id=contract_id,
                objeto=detail["objetoContrato"],
                official_url=listing_url,
                sha256=listing_sha,
                value_amount="719177.48",
            ),
            extra={"listing_index": 31, "uf": "PI"},
        )
        grouped = {contract_id: [listing]}
        result = deepen_one_contract_detail(
            grouped,
            contract_id,
            cache_dir=None,
            retrieved_at="2026-08-18T12:00:00Z",
            artifact_budget={"used": 0, "max": 40},
        )
        assert result["error_kind"] is None
        rebound = grouped[contract_id][0]
        assert rebound.official_url == detail_url
        assert rebound.source_document_sha256 == detail_sha
        assert rebound.source_document_sha256 != listing_sha
        assert rebound.extra.get("listing_index") is None
        dossier = official_live_mod.dossier_from_group(
            contract_id,
            grouped[contract_id],
            retrieved_at="2026-08-18T12:00:00Z",
            verified_at="2026-08-18T12:00:00Z",
            source_as_of=None,
            as_of="2026-08-18T12:00:00Z",
            producer={"repo": "tjsasakifln/extra-cli", "branch": "goal/x", "commit": "abc"},
            replay_command="replay",
            query_window={"start": "2026-07-19", "end": "2026-08-18", "uf": "BR"},
            bytes_obtained=True,
            disposition="entered",
            disposition_reason="aec_engineering_or_construction",
        )
        facts = [item for item in dossier["factual_matrix"]["claims"] if item.get("class") == "FACT"]
        listing_facts = [item for item in facts if item.get("url") == detail_url]
        assert listing_facts
        for claim in listing_facts:
            assert claim["sha256"] == detail_sha
            assert "consulta" not in str(claim["url"])
            assert verify_claim_url_hash(claim=claim) is True
    finally:
        server.shutdown()
        server.server_close()


def test_pdf_raw_sha_still_verifies_without_utf8_roundtrip() -> None:
    raw = b"%PDF-1.4 binary \xff\xfe not utf8"
    digest = raw_record_hash_for(raw)
    claim = {"url": "https://example.invalid/file.pdf", "sha256": digest}
    assert official_live_mod.claim_bound_to_retrieved_bytes(claim, raw) is True
    corrupted = raw.decode("utf-8", errors="replace").encode("utf-8")
    assert corrupted != raw
    assert official_live_mod.claim_bound_to_retrieved_bytes(claim, corrupted) is False


def test_json_key_order_does_not_change_listing_fact_hash() -> None:
    from scripts.historical_contract_authority.official_live import canonical_json_sha256

    left = '{"valorGlobal":719177.48,"objetoContrato":"pavimentacao"}'
    right = '{"objetoContrato":"pavimentacao","valorGlobal":719177.48}'
    assert left != right
    assert canonical_json_sha256(left) == canonical_json_sha256(right)
    claim = {"url": "https://example.invalid", "sha256": canonical_json_sha256(left)}
    assert official_live_mod.claim_bound_to_retrieved_bytes(claim, right.encode("utf-8")) is True
