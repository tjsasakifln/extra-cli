from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.public_exports.market_radar import (
    POINTER_SCHEMA,
    REQUIRED_COLUMN_TYPES,
    SNAPSHOT_SCHEMA,
    ExportError,
    _calendar_window_start,
    _require_schema,
    build_snapshot,
    normalize_contract,
    sanitize_text,
)

TODAY = dt.date(2026, 11, 9)
NOW = dt.datetime(2026, 11, 9, 15, 0, tzinfo=dt.UTC)


def test_postgres_interval_window_is_a_date_even_if_driver_returns_midnight_timestamp():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (dt.datetime(2024, 11, 9, 0, 0),)
    start = _calendar_window_start(connection, today=TODAY, months=24)
    assert type(start) is dt.date
    assert start.isoformat() == "2024-11-09"


def test_schema_preflight_accepts_cursor_pairs_and_refuses_missing_or_changed_type():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    columns = {name: sorted(types)[0] for name, types in REQUIRED_COLUMN_TYPES.items()}
    cursor.fetchall.return_value = list(columns.items())
    assert len(_require_schema(connection)) == 64
    cursor.fetchall.return_value = [(name, kind) for name, kind in columns.items() if name != "valor_total"]
    with pytest.raises(ExportError, match="missing required columns: valor_total"):
        _require_schema(connection)
    cursor.fetchall.return_value = list({**columns, "valor_total": "text"}.items())
    with pytest.raises(ExportError, match="incompatible required types: valor_total=text"):
        _require_schema(connection)


def row(**changes):
    value = {
        "contrato_id": "12345678000190-2-000123/2026",
        "orgao_cnpj": "12345678000190",
        "orgao_nome": "Secretaria de Infraestrutura",
        "fornecedor_cnpj": "98765432000110",
        "fornecedor_nome": "Construtora Exemplo Ltda",
        "objeto_contrato": "Manutenção preventiva de edifício público",
        "valor_total": Decimal("120000.15"),
        "data_inicio": dt.date(2026, 1, 1),
        "data_fim": dt.date(2027, 1, 1),
        "data_publicacao_fonte": dt.date(2026, 2, 1),
        "uf": "SC",
        "municipio": "Florianópolis",
        "source_updated_at": dt.datetime(2026, 11, 8, 12, 0, tzinfo=dt.UTC),
        "supplier_id_type": "CNPJ",
        "status_normalized": "ACTIVE_PROVEN",
        "quality_state": "VALID",
    }
    value.update(changes)
    return value


def source_meta(**changes):
    value = {
        "source_as_of": NOW,
        "ingestion_latest_at": NOW - dt.timedelta(hours=2),
        "window_start": dt.date(2024, 11, 9),
        "window_end": TODAY,
        "candidate_rows": 3,
        "qualified_rows": 3,
    }
    value.update(changes)
    return value


def read_snapshot(output: Path):
    pointer = json.loads((output / "current.json").read_text(encoding="utf-8"))
    path = output / pointer["file"]
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    return pointer, path, connection


def test_normalize_uses_opaque_ids_and_canonical_pncp_link():
    normalized = normalize_contract(row(), today=TODAY)
    assert normalized is not None
    contract_id, _, buyer_id, _, _, _, supplier_id, _, cents, *_ = normalized
    assert len(contract_id) == len(buyer_id) == len(supplier_id) == 24
    assert all(ch in "0123456789abcdef" for ch in contract_id + buyer_id + supplier_id)
    assert "12345678000190" not in {contract_id, buyer_id, supplier_id}
    assert cents == 12_000_015
    assert normalized[-2] == "https://pncp.gov.br/app/contratos/12345678000190/2026/123"
    assert normalized[-1] == 1


def test_expiry_signal_requires_both_valid_dates():
    normalized = normalize_contract(row(data_inicio=None), today=TODAY)
    assert normalized is not None
    assert normalized[-1] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"supplier_id_type": "CPF", "fornecedor_cnpj": "12345678901"},
        {"quality_state": "REVIEW"},
        {"data_publicacao_fonte": None},
        {"contrato_id": "not-an-official-id"},
        {"orgao_cnpj": "00000000000000"},
    ],
)
def test_normalize_fails_closed_for_ineligible_rows(changes):
    assert normalize_contract(row(**changes), today=TODAY) is None


def test_sanitizer_removes_contact_and_document_identifiers():
    text = sanitize_text(
        "Contato pessoa@exemplo.com, CPF 123.456.789-00, CNPJ 12.345.678/0001-90, "
        "WhatsApp (48) 99999-0000",
        limit=500,
    )
    assert "@" not in text
    assert "123.456" not in text
    assert "12.345" not in text
    assert "99999" not in text
    assert "removido" in text


def test_sanitizer_removes_unlabelled_formatted_phone_and_uf_fails_closed():
    text = sanitize_text("Plantão (48) 99999-0000 para emergências", limit=500)
    assert "99999" not in text
    normalized = normalize_contract(row(uf="XX"), today=TODAY)
    assert normalized is not None
    assert normalized[4] is None


def test_snapshot_is_immutable_hashed_deduplicated_and_fts_searchable(tmp_path):
    older = row(
        objeto_contrato="Versão antiga",
        source_updated_at=dt.datetime(2026, 10, 1, tzinfo=dt.UTC),
    )
    newer = row(objeto_contrato="Manutenção atualizada de escola")
    second = row(
        contrato_id="12345678000190-2-000124/2026",
        objeto_contrato="Limpeza hospitalar",
        fornecedor_cnpj="11111111000191",
        fornecedor_nome="Limpeza Exemplo S.A.",
        valor_total=Decimal("0"),
        status_normalized="COMPLETED",
        data_fim=dt.date(2026, 10, 1),
    )
    pointer = build_snapshot(
        [older, newer, second],
        output_dir=tmp_path,
        source_meta=source_meta(),
        today=TODAY,
        generated_at=NOW,
    )
    assert pointer["schema"] == POINTER_SCHEMA
    assert pointer["meta"]["schema"] == SNAPSHOT_SCHEMA
    assert pointer["meta"]["record_count"] == 2
    assert pointer["meta"]["deduplicated_count"] == 1
    assert pointer["meta"]["excluded_count"] == 1
    assert pointer["meta"]["value_aggregation"] is False
    assert pointer["file"] == f"snapshot-{pointer['sha256']}.sqlite"

    loaded, path, connection = read_snapshot(tmp_path)
    try:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == loaded["sha256"]
        assert path.stat().st_size == loaded["bytes"]
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        embedded_meta = json.loads(
            connection.execute("SELECT value FROM metadata WHERE key='meta'").fetchone()[0]
        )
        assert embedded_meta == loaded["meta"]
        assert connection.execute("SELECT count(*) FROM metadata").fetchone() == (1,)
        objects = [r[0] for r in connection.execute("SELECT object FROM contracts ORDER BY object")]
        assert objects == ["Limpeza hospitalar", "Manutenção atualizada de escola"]
        assert connection.execute(
            "SELECT count(*) FROM contract_search WHERE contract_search MATCH ?", ("manutencao",)
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT expiry_eligible FROM contracts WHERE object='Limpeza hospitalar'"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT value_cents FROM contracts WHERE object='Limpeza hospitalar'"
        ).fetchone() == (0,)
        serialized = "\n".join(str(v) for row_ in connection.execute("SELECT * FROM contracts") for v in row_)
        assert "98765432000110" not in serialized
        assert "12345678000190" in serialized  # canonical official source URL only
    finally:
        connection.close()
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o440
        assert (tmp_path / "current.json").stat().st_mode & 0o777 == 0o440


def test_invalid_value_becomes_null_and_is_counted(tmp_path):
    pointer = build_snapshot(
        [row(valor_total=Decimal("-1"))],
        output_dir=tmp_path,
        source_meta=source_meta(candidate_rows=1, qualified_rows=1),
        today=TODAY,
        generated_at=NOW,
    )
    assert pointer["meta"]["invalid_value_count"] == 1
    _, _, connection = read_snapshot(tmp_path)
    try:
        assert connection.execute("SELECT value_cents FROM contracts").fetchone() == (None,)
    finally:
        connection.close()


def test_failed_build_preserves_previous_pointer(tmp_path):
    first = build_snapshot(
        [row()],
        output_dir=tmp_path,
        source_meta=source_meta(candidate_rows=1, qualified_rows=1),
        today=TODAY,
        generated_at=NOW,
    )
    pointer_before = (tmp_path / "current.json").read_bytes()

    def broken_rows():
        yield row(contrato_id="12345678000190-2-000125/2026")
        raise RuntimeError("synthetic interrupted source")

    with pytest.raises(RuntimeError, match="interrupted"):
        build_snapshot(
            broken_rows(),
            output_dir=tmp_path,
            source_meta=source_meta(candidate_rows=2, qualified_rows=2),
            today=TODAY,
            generated_at=NOW + dt.timedelta(hours=1),
        )
    assert (tmp_path / "current.json").read_bytes() == pointer_before
    assert json.loads(pointer_before)["sha256"] == first["sha256"]
    assert not list(tmp_path.glob(".building-*.sqlite"))


def test_empty_projection_is_refused_without_pointer(tmp_path):
    with pytest.raises(ExportError, match="no eligible contracts"):
        build_snapshot(
            [row(supplier_id_type="CPF")],
            output_dir=tmp_path,
            source_meta=source_meta(candidate_rows=1, qualified_rows=0),
            today=TODAY,
            generated_at=NOW,
        )
    assert not (tmp_path / "current.json").exists()


def test_stale_source_is_refused_without_pointer(tmp_path):
    with pytest.raises(ExportError, match="source_stale"):
        build_snapshot(
            [row()],
            output_dir=tmp_path,
            source_meta=source_meta(
                candidate_rows=1,
                qualified_rows=1,
                ingestion_latest_at=NOW - dt.timedelta(hours=49),
            ),
            today=TODAY,
            generated_at=NOW,
        )
    assert not (tmp_path / "current.json").exists()


def test_low_space_preserves_current_pointer(tmp_path, monkeypatch):
    build_snapshot(
        [row()],
        output_dir=tmp_path,
        source_meta=source_meta(candidate_rows=1, qualified_rows=1),
        today=TODAY,
        generated_at=NOW,
    )
    pointer_before = (tmp_path / "current.json").read_bytes()
    monkeypatch.setattr(
        "scripts.public_exports.market_radar.shutil.disk_usage",
        lambda _path: type("Usage", (), {"free": 1, "total": 2, "used": 1})(),
    )
    with pytest.raises(ExportError, match="insufficient_disk_space"):
        build_snapshot(
            [row(objeto_contrato="nova versão")],
            output_dir=tmp_path,
            source_meta=source_meta(candidate_rows=1, qualified_rows=1),
            today=TODAY,
            generated_at=NOW + dt.timedelta(hours=1),
        )
    assert (tmp_path / "current.json").read_bytes() == pointer_before


def test_retention_keeps_current_and_two_predecessors(tmp_path):
    for sequence in range(4):
        pointer = build_snapshot(
            [row(objeto_contrato=f"versão {sequence}")],
            output_dir=tmp_path,
            source_meta=source_meta(candidate_rows=1, qualified_rows=1),
            today=TODAY,
            generated_at=NOW + dt.timedelta(minutes=sequence),
        )
    snapshots = list(tmp_path.glob("snapshot-*.sqlite"))
    assert len(snapshots) == 3
    assert (tmp_path / pointer["file"]).is_file()


def test_source_count_mismatch_is_refused(tmp_path):
    with pytest.raises(ExportError, match="source count mismatch"):
        build_snapshot(
            [row()],
            output_dir=tmp_path,
            source_meta=source_meta(candidate_rows=2, qualified_rows=2),
            today=TODAY,
            generated_at=NOW,
        )
    assert not (tmp_path / "current.json").exists()
