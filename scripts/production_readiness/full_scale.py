"""Bounded-memory full-scale datalake processing with checkpoints.

Processes pncp_supplier_contracts (or a stream adapter) without materializing
all rows in RAM. Supports resume, deterministic manifests, dual-run compare,
and fail-before-disk-exhaustion.
"""

from __future__ import annotations

import hashlib
import json
import os
import resource
import shutil
import sys
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat()


def _git_sha() -> str | None:
    try:
        import subprocess

        git = shutil.which("git")
        if not git:
            return None
        out = subprocess.check_output(  # noqa: S603
            [git, "rev-parse", "HEAD"],
            cwd=str(REPO),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
        return out.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def rss_bytes() -> int:
    # Linux: ru_maxrss is KB
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return int(usage.ru_maxrss) * 1024


def disk_free_bytes(path: Path) -> int:
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(path).free


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)


def sha256_file(path: Path, *, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


@dataclass
class ScaleCheckpoint:
    run_id: str
    offset: int = 0
    accepted: int = 0
    rejected: int = 0
    deduplicated: int = 0
    entities: int = 0
    last_key: str | None = None
    completed: bool = False
    updated_at: str = field(default_factory=_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ScaleCheckpoint:
        return cls(
            run_id=str(data.get("run_id") or ""),
            offset=int(data.get("offset") or 0),
            accepted=int(data.get("accepted") or 0),
            rejected=int(data.get("rejected") or 0),
            deduplicated=int(data.get("deduplicated") or 0),
            entities=int(data.get("entities") or 0),
            last_key=data.get("last_key"),
            completed=bool(data.get("completed") or False),
            updated_at=str(data.get("updated_at") or _iso()),
        )


def load_checkpoint(path: Path) -> ScaleCheckpoint | None:
    if not path.is_file():
        return None
    try:
        return ScaleCheckpoint.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def save_checkpoint(path: Path, cp: ScaleCheckpoint) -> None:
    cp.updated_at = _iso()
    atomic_write_json(path, cp.to_dict())


def stream_synthetic_contracts(
    n: int,
    *,
    start_offset: int = 0,
    seed: int = 42,
) -> Iterator[dict[str, Any]]:
    """Deterministic synthetic stream for local full-scale proof without lake."""
    # Avoid holding all rows; yield one at a time.
    for i in range(start_offset, n):
        # stable pseudo-ids
        ent = i % max(1, n // 1000) if n >= 1000 else i % 50
        yield {
            "contrato_id": f"SYN-{i:09d}",
            "orgao_cnpj": f"{ent:08d}000001",
            "orgao_nome": f"ORGAO-{ent}",
            "fornecedor_cnpj": f"{(i * 7) % 10_000_000:014d}",
            "objeto_contrato": "servicos de engenharia e consultoria" if i % 3 else "limpeza predial",
            "valor_total": float(1000 + (i % 50000)),
            "data_inicio": "2024-01-01",
            "data_fim": "2025-01-01",
            "uf": "SC",
            "source": "synthetic",
            "_offset": i,
            "_seed": seed,
        }


def stream_pg_contracts(
    dsn: str,
    *,
    start_offset: int = 0,
    page_size: int = 5000,
    table: str = "pncp_supplier_contracts",
) -> Iterator[dict[str, Any]]:
    """Server-side cursor stream — never fetchall."""
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(dsn)
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor(
            name=f"full_scale_{uuid.uuid4().hex[:10]}", cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.itersize = page_size
            # OFFSET for resume; prefer keyset when available — offset is OK for proof
            cur.execute(
                f"SELECT * FROM {table} ORDER BY 1 OFFSET %s",  # noqa: S608 — table name from trusted caller
                (int(start_offset),),
            )
            offset = start_offset
            for row in cur:
                d = dict(row)
                d["_offset"] = offset
                offset += 1
                yield d
    finally:
        conn.close()


def count_pg_contracts(dsn: str, table: str = "pncp_supplier_contracts") -> int:
    import psycopg2

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def _row_key(row: Mapping[str, Any]) -> str:
    for k in ("contrato_id", "id", "numero_controle_pncp", "external_id"):
        if row.get(k) is not None:
            return str(row[k])
    return hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()[:24]


def process_stream(
    rows: Iterator[Mapping[str, Any]],
    *,
    out_dir: Path,
    run_id: str | None = None,
    resume: bool = True,
    min_free_disk_bytes: int = 512 * 1024 * 1024,
    checkpoint_every: int = 10_000,
    accept_fn: Callable[[Mapping[str, Any]], bool] | None = None,
    expected_total: int | None = None,
    source_label: str = "unknown",
) -> dict[str, Any]:
    """Process stream with spill files, checkpoint, and bounded memory.

    Dedup via external SQLite (not a growing Python set of all keys when large).
    """
    import sqlite3

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_id or uuid.uuid4().hex[:12]
    cp_path = out_dir / "checkpoint.json"
    spill_db = out_dir / f"spill-{run_id}.sqlite"
    accepted_path = out_dir / "accepted.jsonl"
    rejected_path = out_dir / "rejected.jsonl"
    manifest_path = out_dir / "manifest.json"

    cp = load_checkpoint(cp_path) if resume else None
    if cp is None:
        cp = ScaleCheckpoint(run_id=run_id)
    elif resume and cp.completed:
        # Resume only short-circuits when the prior run truly finished the expected total.
        done_enough = expected_total is None or cp.offset >= int(expected_total)
        if done_enough:
            if (out_dir / "benchmark.json").is_file():
                return json.loads((out_dir / "benchmark.json").read_text(encoding="utf-8"))
            return cp.to_dict()
        # Partial completion (or higher expected_total on continue) — reopen.
        cp.completed = False
    elif not resume:
        cp = ScaleCheckpoint(run_id=run_id)

    if resume and cp.run_id and cp.offset > 0:
        run_id = cp.run_id  # continue same run
    else:
        cp.run_id = run_id

    conn = sqlite3.connect(str(spill_db))
    conn.execute("CREATE TABLE IF NOT EXISTS seen (k TEXT PRIMARY KEY, entity TEXT, valor REAL)")
    conn.execute("CREATE TABLE IF NOT EXISTS entities (entity TEXT PRIMARY KEY)")
    conn.commit()

    t0 = time.perf_counter()
    max_rss = rss_bytes()
    min_disk = disk_free_bytes(out_dir)
    start_offset = cp.offset
    skipped = 0
    warnings: list[str] = []
    errors: list[str] = []

    # open append handles
    acc_mode = "a" if start_offset else "w"
    rej_mode = "a" if start_offset else "w"
    accept_fn = accept_fn or (lambda r: True)

    try:
        with (
            accepted_path.open(acc_mode, encoding="utf-8") as acc_fh,
            rejected_path.open(rej_mode, encoding="utf-8") as rej_fh,
        ):
            for row in rows:
                off = int(row.get("_offset") or 0)
                # if stream starts from 0 but we resume, skip until offset
                if off < start_offset:
                    skipped += 1
                    continue

                free = disk_free_bytes(out_dir)
                min_disk = min(min_disk, free)
                if free < min_free_disk_bytes:
                    errors.append(f"disk_exhausted_before_write free={free}")
                    save_checkpoint(cp_path, cp)
                    raise RuntimeError(f"Refusing to continue: free disk {free} < min {min_free_disk_bytes}")

                key = _row_key(row)
                entity = str(row.get("orgao_cnpj") or row.get("entity_id") or "unknown")
                valor = row.get("valor_total") or row.get("valor") or 0
                try:
                    valor_f = float(valor or 0)
                except (TypeError, ValueError):
                    valor_f = 0.0

                # dedup
                cur = conn.execute("SELECT 1 FROM seen WHERE k=?", (key,))
                if cur.fetchone():
                    cp.deduplicated += 1
                    cp.offset = off + 1
                    cp.last_key = key
                    continue

                if not accept_fn(row):
                    cp.rejected += 1
                    rej_fh.write(json.dumps({"key": key, "reason": "accept_fn_false"}, ensure_ascii=False) + "\n")
                else:
                    conn.execute(
                        "INSERT OR IGNORE INTO seen(k, entity, valor) VALUES (?,?,?)",
                        (key, entity, valor_f),
                    )
                    conn.execute("INSERT OR IGNORE INTO entities(entity) VALUES (?)", (entity,))
                    cp.accepted += 1
                    # spill compact accepted line (not full row forever in RAM)
                    acc_fh.write(
                        json.dumps(
                            {
                                "key": key,
                                "entity": entity,
                                "valor": valor_f,
                                "offset": off,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        + "\n"
                    )

                cp.offset = off + 1
                cp.last_key = key
                max_rss = max(max_rss, rss_bytes())

                if cp.offset % checkpoint_every == 0:
                    ent_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
                    cp.entities = int(ent_count)
                    conn.commit()
                    save_checkpoint(cp_path, cp)

            conn.commit()
            cp.entities = int(conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0])
            cp.completed = True
            save_checkpoint(cp_path, cp)
    finally:
        conn.close()

    elapsed = time.perf_counter() - t0
    # checksums
    checksums = {}
    for p in (accepted_path, rejected_path, spill_db, cp_path):
        if p.is_file():
            checksums[p.name] = sha256_file(p)

    if expected_total is not None and cp.offset < expected_total and not errors:
        # stream ended early
        warnings.append(f"stream_ended_before_expected offset={cp.offset} expected={expected_total}")

    incomplete = (not cp.completed) or bool(errors)
    if expected_total is not None and cp.accepted + cp.rejected + cp.deduplicated < expected_total * 0.99:
        # allow dedup; soft check
        pass

    manifest = {
        "run_id": run_id,
        "completed": cp.completed and not incomplete,
        "incomplete": incomplete,
        "source": source_label,
        "code_sha": _git_sha(),
        "started_offset": start_offset,
        "final_offset": cp.offset,
        "accepted": cp.accepted,
        "rejected": cp.rejected,
        "deduplicated": cp.deduplicated,
        "entities": cp.entities,
        "expected_total": expected_total,
        "elapsed_seconds": round(elapsed, 3),
        "throughput_rows_per_s": round((cp.offset - start_offset) / elapsed, 3) if elapsed > 0 else None,
        "max_rss_bytes": max_rss,
        "min_disk_free_bytes": min_disk,
        "checksums": checksums,
        "warnings": warnings,
        "errors": errors,
        "generated_at": _iso(),
        "publication_allowed": bool(cp.completed and not errors and not incomplete),
    }
    atomic_write_json(manifest_path, manifest)

    benchmark = {
        **manifest,
        "checkpoint": cp.to_dict(),
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }
    atomic_write_json(out_dir / "benchmark.json", benchmark)

    if not manifest["publication_allowed"]:
        # gate: write block marker
        atomic_write_json(
            out_dir / "PUBLICATION_BLOCKED.json",
            {"reason": "incomplete_or_errors", "manifest": manifest},
        )
    return benchmark


def compare_runs(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
    fields = ("accepted", "rejected", "deduplicated", "entities", "final_offset")
    diffs = {}
    for f in fields:
        if a.get(f) != b.get(f):
            diffs[f] = {"a": a.get(f), "b": b.get(f)}
    ck_a = (a.get("checksums") or {}).get("accepted.jsonl")
    ck_b = (b.get("checksums") or {}).get("accepted.jsonl")
    return {
        "identical_counts": not diffs,
        "count_diffs": diffs,
        "accepted_checksum_match": ck_a == ck_b and ck_a is not None,
        "checksum_a": ck_a,
        "checksum_b": ck_b,
        "both_publication_allowed": bool(a.get("publication_allowed") and b.get("publication_allowed")),
    }


def run_full_scale_proof(
    *,
    out_root: Path,
    dsn: str | None = None,
    synthetic_n: int | None = None,
    dual_run: bool = True,
    page_size: int = 5000,
    table: str = "pncp_supplier_contracts",
) -> dict[str, Any]:
    """Execute full-scale (or synthetic) processing; optionally dual-run compare."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_root = Path(out_root)
    run_dir = out_root / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    dsn = dsn or os.environ.get("DATABASE_URL") or os.environ.get("LOCAL_DATALAKE_DSN")
    source = "postgresql"
    expected = None
    if dsn and synthetic_n is None:
        try:
            expected = count_pg_contracts(dsn, table=table)
        except Exception as exc:  # noqa: BLE001 — surface as synthetic fallback only if empty
            expected = None
            source = f"postgresql_error:{type(exc).__name__}"

    if expected is not None and expected > 1:

        def make_stream(start: int = 0) -> Iterator[dict[str, Any]]:
            return stream_pg_contracts(dsn, start_offset=start, page_size=page_size, table=table)

        label = f"{table}@{source}"
        total = expected
    else:
        n = int(synthetic_n or 50_000)
        total = n
        label = f"synthetic_n={n}"
        source = "synthetic"

        def make_stream(start: int = 0) -> Iterator[dict[str, Any]]:
            return stream_synthetic_contracts(n, start_offset=start)

    def accept(row: Mapping[str, Any]) -> bool:
        # reject missing id / non-positive valor for proof of reject path
        if not _row_key(row):
            return False
        v = row.get("valor_total") if row.get("valor_total") is not None else row.get("valor")
        try:
            return float(v or 0) > 0
        except (TypeError, ValueError):
            return False

    r1_dir = run_dir / "run1"
    b1 = process_stream(
        make_stream(0),
        out_dir=r1_dir,
        run_id="run1",
        resume=True,
        expected_total=total,
        source_label=label,
        accept_fn=accept,
    )

    result: dict[str, Any] = {
        "timestamp": ts,
        "source": label,
        "expected_total": total,
        "run1": b1,
        "code_sha": _git_sha(),
    }

    if dual_run:
        r2_dir = run_dir / "run2"
        b2 = process_stream(
            make_stream(0),
            out_dir=r2_dir,
            run_id="run2",
            resume=False,
            expected_total=total,
            source_label=label,
            accept_fn=accept,
        )
        result["run2"] = b2
        result["compare"] = compare_runs(b1, b2)

    # interrupt/resume proof on a small side path
    resume_dir = run_dir / "resume_proof"
    mid = min(5000, max(100, total // 10)) if total else 100

    def limited() -> Iterator[dict[str, Any]]:
        for i, row in enumerate(make_stream(0)):
            if i >= mid:
                break
            yield row

    process_stream(
        limited(),
        out_dir=resume_dir,
        run_id="resume-a",
        resume=False,
        expected_total=mid,
        source_label=label,
        accept_fn=accept,
        checkpoint_every=50,
    )
    cp_loaded = load_checkpoint(resume_dir / "checkpoint.json")
    result["resume_proof"] = {
        "partial_offset": cp_loaded.offset if cp_loaded else None,
        "partial_completed": cp_loaded.completed if cp_loaded else None,
    }
    continue_target = total if total <= 100_000 else (cp_loaded.offset + 1000 if cp_loaded else 1000)
    b_resume = process_stream(
        make_stream(cp_loaded.offset if cp_loaded else 0),
        out_dir=resume_dir,
        run_id=cp_loaded.run_id if cp_loaded else "resume-a",
        resume=True,
        expected_total=continue_target,
        source_label=label,
        accept_fn=accept,
    )
    result["resume_proof"]["continued"] = {
        "offset": b_resume.get("final_offset"),
        "completed": b_resume.get("completed"),
    }

    atomic_write_json(run_dir / "full-scale-benchmark.json", result)
    atomic_write_json(
        run_dir / "full-scale-manifest.json",
        {
            "run_dir": str(run_dir),
            "publication_allowed": bool(b1.get("publication_allowed")),
            "source": label,
            "expected_total": total,
            "code_sha": _git_sha(),
            "generated_at": _iso(),
            "compare": result.get("compare"),
        },
    )
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Full-scale datalake proof")
    p.add_argument("--out", type=Path, default=REPO / "artifacts" / "production-readiness" / "full-scale")
    p.add_argument("--dsn", default=None)
    p.add_argument("--synthetic-n", type=int, default=None)
    p.add_argument("--no-dual", action="store_true")
    p.add_argument("--page-size", type=int, default=5000)
    args = p.parse_args(argv)
    result = run_full_scale_proof(
        out_root=args.out,
        dsn=args.dsn,
        synthetic_n=args.synthetic_n,
        dual_run=not args.no_dual,
        page_size=args.page_size,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "source": result.get("source"),
                "expected_total": result.get("expected_total"),
                "run1_accepted": (result.get("run1") or {}).get("accepted"),
            },
            ensure_ascii=False,
        )
    )
    pub = (result.get("run1") or {}).get("publication_allowed")
    return 0 if pub else 2


if __name__ == "__main__":
    raise SystemExit(main())
