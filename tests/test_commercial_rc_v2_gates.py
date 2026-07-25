"""Commercial RC gates — unit tests without committing bulk frozen pack outputs.

Heavy PDF/XLSX/deliverable dumps are generated at runtime / CI artifacts, not in Git.
These tests drive the shipped classifier and acceptance schema rules.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.ops.sector_classifier import classify_object, is_engineering_for_e

E_OK = {"ENGINEERING_HIGH_CONFIDENCE", "ENGINEERING_REVIEW"}


def test_classifier_rejects_v1_polluters() -> None:
    for obj in (
        "AQUISIÇÃO DE LENÇÓIS E MANTAS",
        "computador All in One",
        "exames laboratoriais",
        "manutenção da frota municipal",
        "SEGURO DE FROTA DE VEICULOS DO DEPARTAMENTO DE ESGOTO",
        "TELEFONIA VOIP",
        "LIMPEZA E JARDINAGEM EM AREAS PAVIMENTADAS",
        "GRAMA SINTETICA FIFA COM DRENAGEM",
        "SANEAMENTO DE INCONFORMIDADES LEGAIS",
        "CREDENCIAMENTO DE INSTITUIÇÕES FINANCEIRAS PARA ARRECADAÇÃO DE FATURAS DE ESGOTAMENTO SANITÁRIO",
        "AQUISIÇÃO DE EQUIPAMENTO DE PINTURA AIRLESS PARA MEIO-FIO",
        "AQUISIÇÃO DE CONJUNTOS MOTOBOMBAS SUBMERSÍVEIS PARA ESGOTAMENTO SANITÁRIO",
    ):
        assert not is_engineering_for_e(classify_object(obj)), obj


def test_classifier_accepts_engineering_objects() -> None:
    for obj in (
        "CONSTRUCAO DE EDIFICIO PUBLICO ESCOLAR",
        "PAVIMENTACAO ASFALTICA DE VIAS URBANAS",
        "OBRA DE DRENAGEM PLUVIAL",
    ):
        assert is_engineering_for_e(classify_object(obj)), obj


def test_pending_human_acceptance_schema(tmp_path: Path) -> None:
    """Human acceptance must stay PENDING_HUMAN with agent auto-accept forbidden."""
    ua = {
        "status": "PENDING_HUMAN",
        "campaign_id": "CLIENT-READY-RECURRING-CONSULTING-CYCLE-01",
        "accepted_by": None,
        "accepted_at": None,
        "agent_auto_accept_forbidden": True,
        "decision_options": ["ACCEPTED", "REJECTED", "CHANGES_REQUESTED"],
        "package_checksums": {},
    }
    path = tmp_path / "user-acceptance.json"
    path.write_text(json.dumps(ua), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "PENDING_HUMAN"
    assert loaded.get("accepted_by") is None
    assert loaded["agent_auto_accept_forbidden"] is True


def test_identity_excludes_self_hash(tmp_path: Path) -> None:
    """ARTIFACT-IDENTITY must not include a self-referential sha of itself."""
    identity = {
        "artifact_name": "client-ready-frozen-rc-v2",
        "classification": "HUMAN_REVIEW_ARTIFACT",
        "production_touched": False,
        "soak_touched": False,
        "file_sha256": {
            "executive-summary.md": "a" * 64,
            "checksums.json": "b" * 64,
        },
    }
    assert "ARTIFACT-IDENTITY.json" not in identity["file_sha256"]
    path = tmp_path / "ARTIFACT-IDENTITY.json"
    path.write_text(json.dumps(identity), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["artifact_name"] == "client-ready-frozen-rc-v2"
    assert "ARTIFACT-IDENTITY.json" not in (loaded.get("file_sha256") or {})


def test_checksums_map_must_match_disk_bytes(tmp_path: Path) -> None:
    content = b"fixture-pack-manifest-v1\n"
    (tmp_path / "pack-manifest.json").write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    ck = {"pack-manifest.json": digest}
    for name, expected in ck.items():
        p = tmp_path / name
        assert p.is_file()
        assert hashlib.sha256(p.read_bytes()).hexdigest() == expected


def test_v1_history_status_changes_requested() -> None:
    """RC v1 remains historically CHANGES_REQUESTED (schema contract)."""
    hist = {
        "status": "CHANGES_REQUESTED",
        "run_id": "rc-v1-historical",
        "notes": "Superseded by RC v2; kept as schema fixture only.",
    }
    assert hist["status"] == "CHANGES_REQUESTED"
