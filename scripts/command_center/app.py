"""FastAPI application for EXTRA Command Center."""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from scripts.command_center import CAMPAIGN_ID, TERMINAL_READY, __version__
from scripts.command_center.artifact_reader import list_recent_artifacts, read_artifact
from scripts.command_center.capabilities.registry import get_registry
from scripts.command_center.config import Settings, git_sha, load_settings
from scripts.command_center.job_runner import JobRunner, StartJobRequest
from scripts.command_center.overview import build_overview, build_search
from scripts.command_center.redaction import env_presence, redact_text
from scripts.command_center.security import issue_csrf_token, require_csrf, resolve_under_roots
from scripts.command_center.store import Store

STARTED_AT = time.time()


class ExecuteBody(BaseModel):
    capability_id: str = Field(..., min_length=1, max_length=200)
    params: dict[str, Any] = Field(default_factory=dict)
    confirmation: str | None = None
    actor: str = "local-user"


class DecisionBody(BaseModel):
    item_id: str
    decision: str
    rationale: str | None = None
    confirmation: str | None = None
    actor: str = "local-user"
    payload: dict[str, Any] = Field(default_factory=dict)


class PrefBody(BaseModel):
    key: str
    value: str


class ReviewEnqueueBody(BaseModel):
    title: str
    source: str = "manual"
    evidence: str = "Sem evidência anexada."
    limitations: str = "Limitações não informadas."
    risks: str = "Riscos não informados."
    job_id: str | None = None
    capability_id: str | None = None
    actor: str = "local-user"
    payload: dict[str, Any] = Field(default_factory=dict)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    store = Store(settings.db_path)
    registry = get_registry()
    runner = JobRunner(settings, store, registry)

    app = FastAPI(
        title="EXTRA Command Center",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.store = store
    app.state.registry = registry
    app.state.runner = runner

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    def csrf_dep(
        request: Request,
        x_cc_csrf: str | None = Header(default=None, alias="X-CC-CSRF"),
    ) -> None:
        # bind header into request for require_csrf
        require_csrf(
            request,
            cookie_name=settings.csrf_cookie_name,
            header_name=settings.csrf_header_name,
            x_csrf=x_cc_csrf,
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        spa_ok = bool(settings.spa_dist and settings.spa_dist.exists())
        return {
            "status": "ok",
            "service": "extra-command-center",
            "version": __version__,
            "campaign": CAMPAIGN_ID,
            "terminal_status": TERMINAL_READY,
            "sha": git_sha(),
            "uptime_sec": round(time.time() - STARTED_AT, 2),
            "host": settings.host,
            "port": settings.port,
            "bind": f"{settings.host}:{settings.port}",
            "public_bind": settings.host not in {"127.0.0.1", "localhost", "::1"},
            "sqlite": {"path": str(settings.db_path), "ok": settings.db_path.parent.exists()},
            "spa": {"configured": spa_ok, "path": str(settings.spa_dist) if settings.spa_dist else None},
            "jobs": store.job_counts(),
            "capabilities": {
                "total": len(registry.list()),
                "available": len(registry.available_ids()),
                "by_category": registry.categories_summary(),
            },
            "roots": [str(r) for r in settings.allowed_artifact_roots],
            "env": {
                "LOCAL_DATALAKE_DSN": env_presence("LOCAL_DATALAKE_DSN"),
                "OPENAI_API_KEY": env_presence("OPENAI_API_KEY"),
                "DATABASE_URL": env_presence("DATABASE_URL"),
            },
            "max_concurrent_jobs": settings.max_concurrent_jobs,
        }

    @app.get("/api/csrf")
    def csrf(response: Response) -> dict[str, str]:
        token = issue_csrf_token(response, settings.csrf_cookie_name)
        return {"csrf_token": token, "header": settings.csrf_header_name}

    @app.get("/api/overview")
    def overview() -> dict[str, Any]:
        return build_overview(settings, store, registry)

    @app.get("/api/capabilities")
    def capabilities(category: str | None = None) -> dict[str, Any]:
        items = registry.public_list()
        if category:
            items = [c for c in items if c["category"] == category]
        return {"capabilities": items}

    @app.get("/api/capabilities/{capability_id}")
    def capability_detail(capability_id: str) -> dict[str, Any]:
        cap = registry.get(capability_id)
        if not cap:
            raise HTTPException(404, "Capability não encontrada")
        return cap.public_dict()

    @app.post("/api/jobs")
    def start_job(body: ExecuteBody, _: None = Depends(csrf_dep)) -> dict[str, Any]:
        # Hard deny arbitrary command fields
        forbidden = {"command", "shell", "argv", "cmd", "executable"}
        if forbidden.intersection(body.params.keys()):
            raise HTTPException(400, "Parâmetros de comando arbitrário são proibidos.")
        try:
            rec = runner.start(
                StartJobRequest(
                    capability_id=body.capability_id,
                    params=body.params,
                    confirmation=body.confirmation,
                    actor=body.actor,
                )
            )
        except ValueError as exc:
            raise HTTPException(400, redact_text(str(exc))) from exc
        return {"job": rec.to_public()}

    @app.get("/api/jobs")
    def list_jobs(limit: int = 50, status: str | None = None) -> dict[str, Any]:
        jobs = store.list_jobs(limit=limit, status=status)
        return {"jobs": [j.to_public() for j in jobs]}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        rec = store.get_job(job_id)
        if not rec:
            raise HTTPException(404, "Job não encontrado")
        return {"job": rec.to_public()}

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, _: None = Depends(csrf_dep)) -> dict[str, Any]:
        try:
            rec = runner.cancel(job_id)
        except KeyError as exc:
            raise HTTPException(404, "Job não encontrado") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"job": rec.to_public()}

    @app.get("/api/jobs/{job_id}/logs")
    def job_logs(job_id: str, after_id: int = 0, limit: int = 500) -> dict[str, Any]:
        if not store.get_job(job_id):
            raise HTTPException(404, "Job não encontrado")
        return {"logs": store.get_logs(job_id, after_id=after_id, limit=limit)}

    @app.get("/api/jobs/{job_id}/events")
    def job_events(job_id: str) -> StreamingResponse:
        if not store.get_job(job_id):
            raise HTTPException(404, "Job não encontrado")

        def gen() -> Any:
            q = runner.subscribe(job_id)
            try:
                while True:
                    try:
                        event = q.get(timeout=15)
                    except Exception:
                        yield "event: ping\ndata: {}\n\n"
                        continue
                    if event is None:
                        yield "event: end\ndata: {}\n\n"
                        break
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            finally:
                runner.unsubscribe(job_id, q)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/api/artifacts")
    def artifacts(path: str | None = None, recent: bool = False) -> dict[str, Any]:
        if recent or not path:
            return {"recent": list_recent_artifacts(settings)}
        return read_artifact(path, settings)

    @app.get("/api/artifacts/download")
    def download_artifact(path: str = Query(...)) -> FileResponse:
        resolved = resolve_under_roots(path, settings.allowed_artifact_roots)
        if not resolved.is_file():
            raise HTTPException(404, "Arquivo não encontrado")
        return FileResponse(resolved, filename=resolved.name)

    @app.get("/api/search")
    def search(q: str = "") -> dict[str, Any]:
        return build_search(q, store, registry, settings)

    @app.get("/api/audit")
    def audit(limit: int = 100) -> dict[str, Any]:
        return {"audit": store.list_audit(limit=limit)}

    @app.get("/api/decisions")
    def decisions(limit: int = 50) -> dict[str, Any]:
        return {"decisions": store.list_decisions(limit=limit)}

    @app.get("/api/reviews")
    def reviews(status: str | None = "pending", limit: int = 50) -> dict[str, Any]:
        """Human review queue from real pending items (jobs blocked, explicit enqueues)."""
        items = store.list_reviews(status=status, limit=limit)
        # Also surface BLOCKED_HUMAN jobs not yet enqueued as synthetic pending items
        if status in (None, "pending"):
            known = {i.get("job_id") for i in items if i.get("job_id")}
            for j in store.list_jobs(limit=100):
                if j.status == "BLOCKED_HUMAN" and j.job_id not in known:
                    store.enqueue_review(
                        title=f"Revisão necessária: {j.action}",
                        source=j.capability_id,
                        evidence=(
                            f"Job {j.job_id}; status {j.status}; "
                            f"código {j.technical_code}; artifacts: {j.artifacts[:5]}"
                        ),
                        limitations=j.human_message or "Automação concluída, mas a decisão humana ainda é necessária.",
                        risks="Aceitar sem evidência pode propagar classificação incorreta.",
                        job_id=j.job_id,
                        capability_id=j.capability_id,
                        payload={"from_job": True, "technical_code": j.technical_code},
                    )
                    known.add(j.job_id)
            items = store.list_reviews(status=status, limit=limit)
        return {"reviews": items, "count": len(items)}

    @app.post("/api/reviews")
    def enqueue_review_api(body: ReviewEnqueueBody, _: None = Depends(csrf_dep)) -> dict[str, Any]:
        """Explicitly enqueue a review item (local queue only — does not decide)."""
        title = body.title.strip()
        if not title:
            raise HTTPException(400, "title obrigatório")
        rid = store.enqueue_review(
            title=title,
            source=body.source,
            evidence=body.evidence,
            limitations=body.limitations,
            risks=body.risks,
            job_id=body.job_id,
            capability_id=body.capability_id,
            payload=body.payload,
        )
        store.audit(body.actor, "review.enqueue", {"id": rid})
        return {"ok": True, "id": rid}

    @app.post("/api/decisions")
    def post_decision(body: DecisionBody, _: None = Depends(csrf_dep)) -> dict[str, Any]:
        decision = body.decision.upper().strip()
        if decision not in {"ACCEPT", "REJECT", "DEFER"}:
            raise HTTPException(400, "Decisão deve ser ACCEPT, REJECT ou DEFER.")
        # Sensitive decisions require confirmation phrase
        sensitive = body.payload.get("sensitive", True)
        if sensitive and decision == "ACCEPT":
            expected = body.payload.get("confirmation_phrase") or (
                "Confirmo que revisei os dados e autorizo apenas a inclusão deste item na fila manual."
            )
            if not body.confirmation or body.confirmation.strip() != expected:
                raise HTTPException(
                    400,
                    f"Confirmação textual obrigatória para ACCEPT sensível. Digite: {expected}",
                )
        # Never call dod accept automatically
        if body.item_id.upper().startswith("DOD") and decision == "ACCEPT":
            store.audit(
                body.actor,
                "decision.dod_accept_blocked",
                {"item_id": body.item_id, "note": "UI records intent only; use canonical controller manually"},
            )
            return {
                "ok": False,
                "blocked": True,
                "message": (
                    "O Command Center não aceita itens do DOD automaticamente. "
                    "A intenção foi auditada; use o controller canônico com gates."
                ),
            }
        decision_id = store.save_decision(
            item_id=body.item_id,
            decision=decision,
            actor=body.actor,
            rationale=body.rationale,
            confirmation=body.confirmation,
            payload=body.payload,
        )
        store.mark_review_decided(body.item_id, decision)
        store.audit(
            body.actor, "decision.save", {"decision_id": decision_id, "item_id": body.item_id, "decision": decision}
        )
        return {"ok": True, "decision_id": decision_id}

    @app.get("/api/preferences/{key}")
    def get_pref(key: str) -> dict[str, Any]:
        return {"key": key, "value": store.get_pref(key)}

    @app.post("/api/preferences")
    def set_pref(body: PrefBody, _: None = Depends(csrf_dep)) -> dict[str, Any]:
        if body.key in {"env", "secrets", ".env"}:
            raise HTTPException(400, "Preferência proibida.")
        store.set_pref(body.key, body.value)
        return {"ok": True}

    @app.get("/api/onboarding")
    def onboarding() -> dict[str, Any]:
        import shutil
        import sys

        node = shutil.which("node")
        return {
            "python": {"ok": True, "version": sys.version.split()[0]},
            "node": {"ok": bool(node), "path": node},
            "spa_built": bool(settings.spa_dist and settings.spa_dist.exists()),
            "data_dir": str(settings.data_dir),
            "env": {
                "LOCAL_DATALAKE_DSN": env_presence("LOCAL_DATALAKE_DSN"),
                "OPENAI_API_KEY": env_presence("OPENAI_API_KEY"),
            },
            "capabilities_available": len(registry.available_ids()),
            "capabilities_total": len(registry.list()),
            "required_to_open_ui": ["python", "fastapi"],
            "notes": [
                "DSN e secrets nunca são exibidos — apenas status configurada/ausente/inválida.",
                "Capabilities ausentes degradam sem quebrar a UI.",
            ],
        }

    # SPA static (single URL mode)
    if settings.spa_dist and settings.spa_dist.exists():
        assets = settings.spa_dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(settings.spa_dist / "index.html")

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(404)
            candidate = settings.spa_dist / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(settings.spa_dist / "index.html")
    else:

        @app.get("/")
        def index_fallback() -> JSONResponse:
            return JSONResponse(
                {
                    "service": "extra-command-center",
                    "message": "API online. Frontend ainda não buildado (apps/command-center/dist).",
                    "health": "/api/health",
                    "docs": "/api/docs",
                }
            )

    return app


def _loopback_sockets(port: int) -> list[Any]:
    """Listen on IPv4 and IPv6 loopback only (never 0.0.0.0 / ::).

    Browsers often resolve ``localhost`` to ``::1``. Binding only ``127.0.0.1``
    makes ``http://localhost:8765`` fail to load while ``http://127.0.0.1:8765`` works.
    """
    import socket

    sockets: list[Any] = []
    targets: list[tuple[int, str]] = [
        (socket.AF_INET, "127.0.0.1"),
        (socket.AF_INET6, "::1"),
    ]
    for family, host in targets:
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if family == socket.AF_INET6 and hasattr(socket, "IPPROTO_IPV6"):
                # Keep v6-only on this socket; v4 has its own listener.
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            sock.bind((host, port))
            sock.listen(2048)
            sockets.append(sock)
        except OSError as exc:
            # IPv6 may be disabled; IPv4-only is still usable.
            import sys

            print(f"WARN: could not bind loopback {host}:{port}: {exc}", file=sys.stderr)
    return sockets


def main() -> None:
    import uvicorn

    settings = load_settings()
    app = create_app(settings)
    host = settings.host
    port = settings.port

    # Dual loopback when staying on the default local-only host (never public binds).
    use_dual = host in {"127.0.0.1", "localhost", "::1"}
    if use_dual:
        socks = _loopback_sockets(port)
        if not socks:
            raise SystemExit(f"Failed to bind any loopback interface on port {port}")
        print(f"==> EXTRA Command Center listening on loopback port {port}")
        print(f"    http://127.0.0.1:{port}")
        print(f"    http://localhost:{port}")
        config = uvicorn.Config(app, log_level="info", access_log=True)
        server = uvicorn.Server(config)
        server.run(sockets=socks)
        return

    # Explicit host (still refused if public unless CC_ALLOW_PUBLIC_BIND=1 via load_settings)
    print(f"==> EXTRA Command Center http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
