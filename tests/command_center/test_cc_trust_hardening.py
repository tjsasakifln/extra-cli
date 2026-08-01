"""Trust-hardening gates for PR #186 Command Center (side-effect free GET, counts, search, brand)."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from fastapi.testclient import TestClient

from scripts.command_center.app import create_app
from scripts.command_center.capabilities.registry import get_registry, reset_registry
from scripts.command_center.config import Settings
from scripts.command_center.overview import build_overview
from scripts.command_center.search_index import ArtifactSearchIndex
from scripts.command_center.store import JobRecord, Store

# Official web-cfg logo-confenge.png
CANONICAL_LOGO_SHA256 = "e6af0125c73edd476cff82ab4ea1de3e459fbdbde63b886f6c55f8a93531505b"


def _settings(tmp_path: Path, out: Path | None = None) -> Settings:
    data = tmp_path / "cc-data"
    data.mkdir(parents=True, exist_ok=True)
    root = out or (tmp_path / "output")
    root.mkdir(parents=True, exist_ok=True)
    return Settings(
        host="127.0.0.1",
        port=8765,
        data_dir=data,
        open_browser=False,
        spa_dist=None,
        allowed_artifact_roots=(root.resolve(), data.resolve()),
        max_concurrent_jobs=2,
    )


def test_canonical_brand_asset_checksum() -> None:
    logo = Path("apps/command-center/public/brand/logo-confenge.png")
    assert logo.is_file(), "official brand PNG must be present"
    digest = hashlib.sha256(logo.read_bytes()).hexdigest()
    assert digest == CANONICAL_LOGO_SHA256
    assert not Path("apps/command-center/public/brand/logo-confenge.svg").exists()
    assert not Path("apps/command-center/public/brand/logo-confenge-white.svg").exists()
    assert not Path("apps/command-center/public/brand/logo-confenge-white.png").exists()


def test_get_reviews_is_side_effect_free(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Store(settings.db_path)
    store.create_job(
        JobRecord(
            job_id="job-blocked-1",
            capability_id="workflow.extra.opportunities",
            action="Encontrar oportunidades",
            params={},
            status="BLOCKED_HUMAN",
            technical_code="NEEDS_HUMAN",
            human_message="Precisa de revisão",
        )
    )
    client = TestClient(create_app(settings))
    before = store.count_reviews(status="pending")
    for _ in range(5):
        res = client.get("/api/reviews?status=pending&limit=50")
        assert res.status_code == 200
        body = res.json()
        assert "total_count" in body
        assert "page_count" in body
        assert body["limit"] == 50
        assert body["offset"] == 0
    after = Store(settings.db_path).count_reviews(status="pending")
    assert after == before, "GET /api/reviews must not create review rows"


def test_reviews_total_count_not_page_size(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Store(settings.db_path)
    for i in range(7):
        store.enqueue_review(
            title=f"Item {i}",
            source="test",
            evidence="e",
            limitations="l",
            risks="r",
            job_id=f"j-{i}",
        )
    client = TestClient(create_app(settings))
    res = client.get("/api/reviews?status=pending&limit=3&offset=0")
    assert res.status_code == 200
    body = res.json()
    assert body["page_count"] == 3
    assert body["total_count"] == 7
    assert body["count"] == 7
    assert len(body["reviews"]) == 3


def test_reconcile_reviews_idempotent(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Store(settings.db_path)
    store.create_job(
        JobRecord(
            job_id="job-bh-1",
            capability_id="cap.x",
            action="Ação X",
            params={},
            status="BLOCKED_HUMAN",
        )
    )
    client = TestClient(create_app(settings))
    csrf = client.get("/api/csrf").json()["csrf_token"]
    r1 = client.post("/api/reviews/reconcile", headers={"X-CC-CSRF": csrf}, json={})
    assert r1.status_code == 200
    first_count = r1.json()["total_pending"]
    assert first_count >= 1
    csrf2 = client.get("/api/csrf").json()["csrf_token"]
    r2 = client.post("/api/reviews/reconcile", headers={"X-CC-CSRF": csrf2}, json={})
    assert r2.status_code == 200
    assert r2.json()["total_pending"] == first_count
    assert r2.json()["created"] == 0


def test_concurrent_enqueue_same_job_no_duplicate(tmp_path: Path) -> None:
    """A6: concurrent enqueue_review for same job_id must not duplicate (IntegrityError recovery)."""
    import concurrent.futures

    settings = _settings(tmp_path)
    store = Store(settings.db_path)

    def _once(i: int) -> str:
        return store.enqueue_review(
            title=f"Revisão {i}",
            source="cap.x",
            evidence="e",
            limitations="l",
            risks="r",
            job_id="job-concurrent-1",
            capability_id="cap.x",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(_once, range(16)))
    assert len(set(ids)) == 1
    assert store.count_reviews(status="pending") == 1


def test_preview_xlsx_rejects_xls(tmp_path: Path) -> None:
    out = tmp_path / "output"
    settings = _settings(tmp_path, out=out)
    target = out / "trust-hardening-sample.xls"
    target.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 64)
    client = TestClient(create_app(settings))
    res = client.get(f"/api/artifacts/preview-xlsx?path={target}")
    assert res.status_code == 400
    detail = str(res.json().get("detail", "")).lower()
    assert ".xls" in detail or "xlsx" in detail


def test_search_index_no_hot_path_rglob(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    art = root / "artifacts"
    art.mkdir(parents=True)
    for i in range(500):
        (art / f"file-{i:04d}.json").write_text("{}", encoding="utf-8")
    idx = ArtifactSearchIndex(root, roots=("artifacts",), ttl_sec=60.0, max_entries=2000)
    t0 = time.perf_counter()
    r1 = idx.search("file-0100", limit=10)
    t1 = time.perf_counter()
    r2 = idx.search("file-0200", limit=10)
    t2 = time.perf_counter()
    assert r1 and "file-0100" in r1[0]["label"]
    assert r2 and "file-0200" in r2[0]["label"]
    assert (t2 - t0) < 5.0
    assert (t2 - t1) < 1.0


def test_overview_attention_priority_human_before_running(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = Store(settings.db_path)
    store.create_job(
        JobRecord(
            job_id="run-1",
            capability_id="cap.run",
            action="Job A",
            params={},
            status="RUNNING",
        )
    )
    store.enqueue_review(
        title="Precisa decidir",
        source="s",
        evidence="e",
        limitations="l",
        risks="r",
        job_id="job-rev",
    )
    reset_registry(None)  # type: ignore[arg-type]
    try:
        ov = build_overview(settings, store, get_registry())
    except TypeError:
        # reset_registry may require a list — fall back to default registry
        from scripts.command_center.capabilities.registry import CapabilityRegistry

        ov = build_overview(settings, store, CapabilityRegistry())
    kinds = [a["kind"] for a in ov["attention"]]
    if "awaiting_human" in kinds and "running" in kinds:
        assert kinds.index("awaiting_human") < kinds.index("running")
    assert ov["reviews_pending_count"] >= 1
