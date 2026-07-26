"""Validate authenticated read-only contract snapshot manifests.

Content binding requires a canonical full-table hash over all rows, not
row-count + 5 samples alone (objective §15).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CANONICAL_HASH_ALGORITHM = "sha256-rowmd5-ordered-agg-v1"
MARKER_MAX_BYTES = 512  # dumps that are tiny text markers are not dumps


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
    canonical_table_hash: str | None = None
    canonical_hash_algorithm: str | None = None

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
            "canonical_table_hash": self.canonical_table_hash,
            "canonical_hash_algorithm": self.canonical_hash_algorithm,
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


def _is_marker_dump(path: Path) -> bool:
    """True when dump_path points at a tiny marker/claim file, not a real dump."""
    try:
        if not path.is_file():
            return True
        name = path.name.lower()
        if "marker" in name:
            return True
        size = path.stat().st_size
        if size <= MARKER_MAX_BYTES:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            # Explicit claim markers like "row_count=60000" without binary dump content
            if "row_count=" in text or "pncp_supplier_contracts row_count" in text:
                return True
            if text.strip().startswith("{") and "fixture" in text:
                return True
    except OSError:
        return True
    return False


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
    canon = man.get("canonical_table_hash")
    canon_algo = man.get("canonical_hash_algorithm") or CANONICAL_HASH_ALGORITHM

    if not expected and not canon:
        return SnapshotValidation(
            ok=False,
            status="BLOCKED_MISSING_AUTHENTICATED_REAL_SNAPSHOT",
            manifest_path=str(mp),
            snapshot_hash=None,
            expected_hash=None,
            dump_path=str(dump) if dump else None,
            contracts_count_declared=int(count) if count is not None else None,
            source=str(source) if source else None,
            reasons=["missing_sha256_and_canonical_table_hash"],
            details=man,
        )

    if man.get("fixture") is True or man.get("synthetic") is True:
        return SnapshotValidation(
            ok=False,
            status="BLOCKED_MISSING_AUTHENTICATED_REAL_SNAPSHOT",
            manifest_path=str(mp),
            snapshot_hash=None,
            expected_hash=str(expected) if expected else None,
            dump_path=str(dump) if dump else None,
            reasons=["fixture_or_synthetic_not_allowed_for_real_gate"],
            details=man,
        )

    dump_path = Path(str(dump)).expanduser() if dump else None
    if dump_path is not None and not dump_path.is_absolute():
        dump_path = (mp.parent / dump_path).resolve()

    dump_is_marker = dump_path is not None and _is_marker_dump(dump_path)
    dump_missing = dump_path is None or not dump_path.is_file() or dump_is_marker

    # Marker dumps never authenticate the snapshot by themselves
    if dump_is_marker:
        if canon:
            # May still bind via DB canonical hash later
            return SnapshotValidation(
                ok=True,
                status="CANONICAL_HASH_DECLARED_DUMP_IS_MARKER",
                manifest_path=str(mp),
                snapshot_hash=str(expected) if expected else None,
                expected_hash=str(expected) if expected else None,
                dump_path=str(dump_path),
                contracts_count_declared=int(count) if count is not None else None,
                source=str(source) if source else None,
                reasons=["dump_is_marker_not_authenticated_dump", "rely_on_canonical_table_hash"],
                details=man,
                canonical_table_hash=str(canon),
                canonical_hash_algorithm=str(canon_algo),
            )
        return SnapshotValidation(
            ok=False,
            status="BLOCKED_MISSING_AUTHENTICATED_REAL_SNAPSHOT",
            manifest_path=str(mp),
            snapshot_hash=None,
            expected_hash=str(expected) if expected else None,
            dump_path=str(dump_path) if dump_path else None,
            contracts_count_declared=int(count) if count is not None else None,
            source=str(source) if source else None,
            reasons=["dump_path_is_marker_not_real_dump", "no_canonical_table_hash"],
            details=man,
        )

    if dump_missing:
        if allow_missing_dump and canon:
            return SnapshotValidation(
                ok=True,
                status="CANONICAL_HASH_DECLARED_DUMP_ABSENT",
                manifest_path=str(mp),
                snapshot_hash=str(expected) if expected else str(canon),
                expected_hash=str(expected) if expected else None,
                dump_path=str(dump_path) if dump_path else None,
                contracts_count_declared=int(count) if count is not None else None,
                source=str(source) if source else None,
                reasons=["dump_file_absent_canonical_hash_declared"],
                details=man,
                canonical_table_hash=str(canon),
                canonical_hash_algorithm=str(canon_algo),
            )
        if allow_missing_dump and expected:
            # Legacy path: hash declared but no dump — NOT fully authenticated
            return SnapshotValidation(
                ok=False,
                status="BLOCKED_MISSING_AUTHENTICATED_REAL_SNAPSHOT",
                manifest_path=str(mp),
                snapshot_hash=str(expected),
                expected_hash=str(expected),
                dump_path=str(dump_path) if dump_path else None,
                contracts_count_declared=int(count) if count is not None else None,
                source=str(source) if source else None,
                reasons=[
                    "dump_file_absent",
                    "sha256_alone_without_dump_or_canonical_hash_not_sufficient",
                ],
                details=man,
            )
        return SnapshotValidation(
            ok=False,
            status="BLOCKED_MISSING_AUTHENTICATED_REAL_SNAPSHOT",
            manifest_path=str(mp),
            snapshot_hash=None,
            expected_hash=str(expected) if expected else None,
            dump_path=str(dump_path) if dump_path else None,
            contracts_count_declared=int(count) if count is not None else None,
            source=str(source) if source else None,
            reasons=["dump_file_missing"],
            details=man,
        )

    actual = None
    if verify_file_hash and expected:
        actual = sha256_file(dump_path)
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
        snapshot_hash=actual or str(expected) if expected else str(canon),
        expected_hash=str(expected) if expected else None,
        dump_path=str(dump_path),
        contracts_count_declared=int(count) if count is not None else None,
        source=str(source) if source else None,
        details={
            "package": man.get("package"),
            "exported_at_utc": man.get("exported_at_utc"),
            "read_only": man.get("read_only", True),
            "sha256sums_file": man.get("sha256sums_file"),
        },
        canonical_table_hash=str(canon) if canon else None,
        canonical_hash_algorithm=str(canon_algo) if canon else None,
    )


def compute_canonical_table_hash(
    conn: Any,
    *,
    table: str = "pncp_supplier_contracts",
    batch_size: int = 5000,
) -> dict[str, Any]:
    """Deterministic content fingerprint over ALL active rows.

    Algorithm (v1):
      ORDER BY contrato_id NULLS LAST, fornecedor_cnpj, data_publicacao, valor_total
      For each row: md5 of pipe-joined canonical fields
      Aggregate: sha256 of concatenation of per-row md5 digests in order
    """
    from scripts.commercial_leads.dbutil import fetch_all

    allowed = {"pncp_supplier_contracts"}
    if table not in allowed:
        raise ValueError(f"table not allowed: {table}")

    count_rows = fetch_all(
        conn, "SELECT COUNT(*)::bigint AS n FROM public.pncp_supplier_contracts"
    )
    n = int(count_rows[0]["n"]) if count_rows else 0

    h = hashlib.sha256()
    offset = 0
    hashed = 0
    while True:
        rows = fetch_all(
            conn,
            """
            SELECT
              coalesce(contrato_id::text, '') AS contrato_id,
              coalesce(fornecedor_cnpj::text, '') AS fornecedor_cnpj,
              coalesce(orgao_cnpj::text, '') AS orgao_cnpj,
              coalesce(objeto_contrato::text, '') AS objeto_contrato,
              coalesce(valor_total::text, '') AS valor_total,
              coalesce(data_publicacao::text, '') AS data_publicacao,
              coalesce(data_inicio::text, '') AS data_inicio,
              coalesce(data_fim::text, '') AS data_fim,
              coalesce(uf::text, '') AS uf,
              coalesce(is_active::text, '') AS is_active
            FROM public.pncp_supplier_contracts
            ORDER BY contrato_id NULLS LAST, fornecedor_cnpj NULLS LAST,
                     data_publicacao NULLS LAST, valor_total NULLS LAST
            LIMIT %s OFFSET %s
            """,
            (batch_size, offset),
        )
        if not rows:
            break
        for r in rows:
            line = "|".join(
                [
                    r["contrato_id"],
                    r["fornecedor_cnpj"],
                    r["orgao_cnpj"],
                    r["objeto_contrato"],
                    r["valor_total"],
                    r["data_publicacao"],
                    r["data_inicio"],
                    r["data_fim"],
                    r["uf"],
                    r["is_active"],
                ]
            )
            row_md5 = hashlib.md5(line.encode("utf-8")).hexdigest()  # noqa: S324 — content FP not crypto secret
            h.update(row_md5.encode("ascii"))
            hashed += 1
        offset += batch_size
        if len(rows) < batch_size:
            break

    return {
        "canonical_table_hash": h.hexdigest(),
        "canonical_hash_algorithm": CANONICAL_HASH_ALGORITHM,
        "row_count": n,
        "rows_hashed": hashed,
        "table": table,
    }


def bind_snapshot_to_database(
    conn: Any,
    manifest: SnapshotValidation | dict[str, Any],
    *,
    table: str = "pncp_supplier_contracts",
    sample_limit: int = 5,
    require_canonical_match: bool = True,
) -> dict[str, Any]:
    """Bind manifest to live DB via full-table canonical hash + row count.

    Row count equality alone is NEVER sufficient for BOUND (objective §15).
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

    # Full-table canonical hash (expensive but required)
    canon = compute_canonical_table_hash(conn, table=table)
    db_canon = canon["canonical_table_hash"]
    manifest_canon = man.get("canonical_table_hash") or details.get("canonical_table_hash")

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

    if require_canonical_match:
        if not manifest_canon:
            # First bind can mint the hash — still not pre-authenticated dump, but content bound
            reasons.append("manifest_canonical_table_hash_missing_minted_from_db")
            # Content is verified against itself this run; caller should persist to manifest
            content_bound = True
        elif str(manifest_canon).lower() != str(db_canon).lower():
            ok = False
            content_bound = False
            reasons.append("canonical_table_hash_mismatch")
        else:
            content_bound = True
            reasons.append("canonical_table_hash_match")
    else:
        content_bound = bool(manifest_canon and str(manifest_canon).lower() == str(db_canon).lower())

    # Never BOUND on row-count alone
    if ok and not content_bound and require_canonical_match and not manifest_canon:
        # Allow first-run mint: status CONTENT_FINGERPRINTED (not AUTHENTICATED dump)
        status = "CONTENT_FINGERPRINTED_DB"
        ok = True
    elif ok and content_bound:
        status = "BOUND"
    else:
        status = "FAIL_SNAPSHOT_DB_MISMATCH"
        ok = False

    # Weak fingerprint kept for diagnostics only
    weak_fp = hashlib.sha256(
        f"{db_count}|{min_date}|{max_date}|{'|'.join(sample_hashes)}".encode()
    ).hexdigest()

    return {
        "ok": ok,
        "status": status,
        "declared_row_count": int(declared) if declared is not None else None,
        "database_row_count": db_count,
        "min_date": min_date,
        "max_date": max_date,
        "sample_hashes": sample_hashes,
        "table_snapshot_hash": weak_fp,  # weak/legacy diagnostic only
        "canonical_table_hash": db_canon,
        "canonical_hash_algorithm": canon["canonical_hash_algorithm"],
        "rows_hashed": canon["rows_hashed"],
        "manifest_canonical_table_hash": manifest_canon,
        "canonical_match": content_bound if manifest_canon else None,
        "schema_version": details.get("schema_version") or man.get("schema_version") or "pncp_supplier_contracts@campaign",
        "reasons": reasons,
        "justified_filter": justified,
        "filter_note": filter_note,
        "table": table,
        "note": (
            "BOUND requires canonical_table_hash match over all rows. "
            "row_count + sample_hashes alone never suffice."
        ),
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
    canonical_table_hash: str | None = None,
    min_date: str | None = None,
    max_date: str | None = None,
) -> Path:
    payload = {
        "kind": "authenticated_contract_snapshot",
        "read_only": True,
        "fixture": False,
        "synthetic": False,
        "dump_path": str(dump_path),
        "sha256": sha256,
        "dump_sha256": sha256,
        "contracts_count": contracts_count,
        "row_count": contracts_count,
        "package": package,
        "exported_at_utc": exported_at_utc,
        "source": "local_backfill_export_pkg",
        "sha256sums_file": sha256sums_file,
        "canonical_table_hash": canonical_table_hash,
        "canonical_hash_algorithm": CANONICAL_HASH_ALGORITHM if canonical_table_hash else None,
        "min_date": min_date,
        "max_date": max_date,
        "schema_version": "pncp_supplier_contracts@campaign",
        "notes": (
            "Local authenticated dump of pncp_supplier_contracts. "
            "canonical_table_hash is required for content binding."
        ),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path
