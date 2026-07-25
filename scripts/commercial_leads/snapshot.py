"""Validate authenticated read-only contract snapshot manifests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any  # noqa: I001 — used by bind_snapshot_to_database


@dataclass
class SnapshotValidation:
    ok: bool
    status: str
    manifest_path: str | None
    snapshot_hash: str | None
    expected_hash: str | None
    dump_path: str | None
    contracts_count_declared: int | None = None
    source: str | None = None
    reasons: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "manifest_path": self.manifest_path,
            "snapshot_hash": self.snapshot_hash,
            "expected_hash": self.expected_hash,
            "dump_path": self.dump_path,
            "contracts_count_declared": self.contracts_count_declared,
            "source": self.source,
            "reasons": self.reasons,
            "details": self.details,
        }


def sha256_file(path: Path, *, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("snapshot manifest must be a JSON object")
    return data


def validate_snapshot_manifest(
    manifest_path: str | Path,
    *,
    verify_file_hash: bool = True,
    allow_missing_dump: bool = False,
) -> SnapshotValidation:
    mp = Path(manifest_path).resolve()
    if not mp.is_file():
        return SnapshotValidation(
            ok=False,
            status="BLOCKED_MISSING_AUTHENTICATED_REAL_SNAPSHOT",
            manifest_path=str(mp),
            snapshot_hash=None,
            expected_hash=None,
            dump_path=None,
            reasons=["manifest_not_found"],
        )

    try:
        man = load_manifest(mp)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return SnapshotValidation(
            ok=False,
            status="FAIL",
            manifest_path=str(mp),
            snapshot_hash=None,
            expected_hash=None,
            dump_path=None,
            reasons=[f"manifest_invalid:{exc}"],
        )

    expected = man.get("sha256") or man.get("dump_sha256") or man.get("snapshot_hash")
    dump = man.get("dump_path") or man.get("path") or man.get("snapshot_path")
    count = man.get("contracts_count") or man.get("row_count")
    source = man.get("source") or man.get("package") or man.get("origin")

    if not expected:
        return SnapshotValidation(
            ok=False,
            status="BLOCKED_MISSING_AUTHENTICATED_REAL_SNAPSHOT",
            manifest_path=str(mp),
            snapshot_hash=None,
            expected_hash=None,
            dump_path=str(dump) if dump else None,
            contracts_count_declared=int(count) if count is not None else None,
            source=str(source) if source else None,
            reasons=["missing_sha256_in_manifest"],
            details=man,
        )

    if man.get("fixture") is True or man.get("synthetic") is True:
        return SnapshotValidation(
            ok=False,
            status="BLOCKED_MISSING_AUTHENTICATED_REAL_SNAPSHOT",
            manifest_path=str(mp),
            snapshot_hash=None,
            expected_hash=str(expected),
            dump_path=str(dump) if dump else None,
            reasons=["fixture_or_synthetic_not_allowed_for_real_gate"],
            details=man,
        )

    dump_path = Path(str(dump)).expanduser() if dump else None
    if dump_path is not None and not dump_path.is_absolute():
        dump_path = (mp.parent / dump_path).resolve()

    if dump_path is None or not dump_path.is_file():
        if allow_missing_dump:
            return SnapshotValidation(
                ok=True,
                status="HASH_DECLARED_DUMP_ABSENT",
                manifest_path=str(mp),
                snapshot_hash=str(expected),
                expected_hash=str(expected),
                dump_path=str(dump_path) if dump_path else None,
                contracts_count_declared=int(count) if count is not None else None,
                source=str(source) if source else None,
                reasons=["dump_file_absent_but_hash_declared"],
                details=man,
            )
        return SnapshotValidation(
            ok=False,
            status="BLOCKED_MISSING_AUTHENTICATED_REAL_SNAPSHOT",
            manifest_path=str(mp),
            snapshot_hash=None,
            expected_hash=str(expected),
            dump_path=str(dump_path) if dump_path else None,
            contracts_count_declared=int(count) if count is not None else None,
            source=str(source) if source else None,
            reasons=["dump_file_missing"],
            details=man,
        )

    actual = None
    if verify_file_hash:
        actual = sha256_file(dump_path)
        if actual != str(expected).lower() and actual != str(expected):
            # compare case-insensitive hex
            if actual.lower() != str(expected).lower():
                return SnapshotValidation(
                    ok=False,
                    status="FAIL",
                    manifest_path=str(mp),
                    snapshot_hash=actual,
                    expected_hash=str(expected),
                    dump_path=str(dump_path),
                    contracts_count_declared=int(count) if count is not None else None,
                    source=str(source) if source else None,
                    reasons=["snapshot_hash_mismatch"],
                    details=man,
                )

    return SnapshotValidation(
        ok=True,
        status="AUTHENTICATED_REAL_SNAPSHOT",
        manifest_path=str(mp),
        snapshot_hash=actual or str(expected),
        expected_hash=str(expected),
        dump_path=str(dump_path),
        contracts_count_declared=int(count) if count is not None else None,
        source=str(source) if source else None,
        details={
            "package": man.get("package"),
            "exported_at_utc": man.get("exported_at_utc"),
            "read_only": man.get("read_only", True),
            "sha256sums_file": man.get("sha256sums_file"),
        },
    )


def bind_snapshot_to_database(
    conn: Any,
    manifest: SnapshotValidation | dict[str, Any],
    *,
    table: str = "pncp_supplier_contracts",
    sample_limit: int = 5,
) -> dict[str, Any]:
    """Bind manifest declarations to live database content.

    Fails closed when declared_row_count != database_row_count unless
    an explicit justified filter is recorded on the manifest.
    """
    from scripts.commercial_leads.dbutil import fetch_all

    allowed = {"pncp_supplier_contracts"}
    if table not in allowed:
        raise ValueError(f"table not allowed for snapshot bind: {table}")

    man = manifest.as_dict() if hasattr(manifest, "as_dict") else dict(manifest)
    details = man.get("details") or {}
    declared = man.get("contracts_count_declared")
    if declared is None:
        declared = details.get("contracts_count") or details.get("row_count")

    # table is allowlisted above (not user SQL)
    count_sql = "SELECT COUNT(*)::bigint AS n FROM public.pncp_supplier_contracts"
    count_rows = fetch_all(conn, count_sql)
    db_count = int(count_rows[0]["n"]) if count_rows else 0

    date_rows = fetch_all(
        conn,
        "SELECT MIN(data_publicacao)::text AS min_d, MAX(data_publicacao)::text AS max_d "
        "FROM public.pncp_supplier_contracts",
    )
    min_date = date_rows[0]["min_d"] if date_rows else None
    max_date = date_rows[0]["max_d"] if date_rows else None

    sample_rows = fetch_all(
        conn,
        "SELECT contrato_id, fornecedor_cnpj, md5(coalesce(objeto_contrato,'')) AS obj_md5 "
        "FROM public.pncp_supplier_contracts ORDER BY contrato_id NULLS LAST LIMIT %s",
        (sample_limit,),
    )
    sample_hashes = [
        f"{r.get('contrato_id')}:{r.get('fornecedor_cnpj')}:{r.get('obj_md5')}" for r in sample_rows
    ]

    justified = bool(details.get("row_count_filter_justified") or man.get("row_count_filter_justified"))
    filter_note = details.get("canonical_filter_note") or man.get("canonical_filter_note")

    ok = True
    reasons: list[str] = []
    if declared is not None and int(declared) != db_count:
        if justified and filter_note:
            reasons.append("row_count_diff_justified")
        else:
            ok = False
            reasons.append("manifest_row_count_ne_database_row_count")

    # table snapshot fingerprint
    import hashlib

    fp = hashlib.sha256(
        f"{db_count}|{min_date}|{max_date}|{'|'.join(sample_hashes)}".encode()
    ).hexdigest()

    return {
        "ok": ok,
        "status": "BOUND" if ok else "FAIL_SNAPSHOT_DB_MISMATCH",
        "declared_row_count": int(declared) if declared is not None else None,
        "database_row_count": db_count,
        "min_date": min_date,
        "max_date": max_date,
        "sample_hashes": sample_hashes,
        "table_snapshot_hash": fp,
        "schema_version": details.get("schema_version") or man.get("schema_version"),
        "reasons": reasons,
        "justified_filter": justified,
        "filter_note": filter_note,
        "table": table,
    }


def write_default_manifest(
    out_path: Path,
    *,
    dump_path: Path,
    sha256: str,
    contracts_count: int,
    package: str,
    exported_at_utc: str,
    sha256sums_file: str | None = None,
) -> Path:
    payload = {
        "kind": "authenticated_contract_snapshot",
        "read_only": True,
        "fixture": False,
        "synthetic": False,
        "dump_path": str(dump_path),
        "sha256": sha256,
        "contracts_count": contracts_count,
        "package": package,
        "exported_at_utc": exported_at_utc,
        "source": "local_backfill_export_pkg",
        "sha256sums_file": sha256sums_file,
        "notes": (
            "Local authenticated dump of pncp_supplier_contracts. "
            "Not obtained via production SSH during this campaign."
        ),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path
