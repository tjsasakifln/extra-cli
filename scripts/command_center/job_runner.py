"""Allowlisted job runner with SSE-friendly log streaming."""

from __future__ import annotations

import queue
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scripts.command_center.capabilities.base import Availability, Capability, default_parse
from scripts.command_center.capabilities.registry import CapabilityRegistry
from scripts.command_center.config import Settings, git_sha
from scripts.command_center.redaction import redact_mapping, redact_text
from scripts.command_center.security import assert_argv_list
from scripts.command_center.status_normalize import JobState, normalize_exit, public_status_dict
from scripts.command_center.store import JobRecord, Store


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StartJobRequest:
    capability_id: str
    params: dict[str, Any]
    confirmation: str | None = None
    actor: str = "local-user"


class JobRunner:
    def __init__(self, settings: Settings, store: Store, registry: CapabilityRegistry) -> None:
        self.settings = settings
        self.store = store
        self.registry = registry
        self._lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._subscribers: dict[str, list[queue.Queue[dict[str, Any] | None]]] = {}
        self._sem = threading.Semaphore(settings.max_concurrent_jobs)
        self.settings.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.settings.logs_dir.mkdir(parents=True, exist_ok=True)

    def start(self, req: StartJobRequest) -> JobRecord:
        cap = self.registry.get(req.capability_id)
        if cap is None:
            raise ValueError(f"Capability desconhecida: {req.capability_id}")
        avail, reason = cap.detect_availability()
        if avail != Availability.AVAILABLE:
            raise ValueError(reason or "Capability indisponível nesta versão.")

        params = redact_mapping(dict(req.params or {}))
        self._validate_params(cap, params)

        if cap.requires_confirmation:
            phrase = cap.confirmation_phrase or "CONFIRMO"
            if not req.confirmation or req.confirmation.strip() != phrase:
                raise ValueError(
                    f"Confirmação obrigatória. Digite exatamente: {phrase}"
                )

        try:
            argv = assert_argv_list(cap.argv_builder(params))
        except Exception as exc:
            raise ValueError(f"Falha ao montar comando: {exc}") from exc

        job_id = str(uuid.uuid4())
        job_dir = self.settings.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        rec = JobRecord(
            job_id=job_id,
            capability_id=cap.id,
            action=cap.name,
            params=params,
            status=JobState.QUEUED.value,
            human_message="Na fila — a execução ainda não começou.",
            attention="running",
            canonical_command=argv,
            stdout_path=str(job_dir / "stdout.log"),
            stderr_path=str(job_dir / "stderr.log"),
            code_sha=git_sha(),
        )
        self.store.create_job(rec)
        self.store.audit(req.actor, "job.start", {"job_id": job_id, "capability_id": cap.id, "argv": argv})
        thread = threading.Thread(target=self._run_job, args=(rec.job_id, cap), daemon=True)
        thread.start()
        return rec

    def _validate_params(self, cap: Capability, params: dict[str, Any]) -> None:
        known = {p.name for p in cap.params}
        for key in params:
            if key not in known:
                raise ValueError(f"Parâmetro não permitido: {key}")
        for p in cap.params:
            if p.required and (params.get(p.name) in (None, "")):
                raise ValueError(f"Parâmetro obrigatório ausente: {p.label}")
            if p.type == "select" and p.choices and params.get(p.name) is not None:
                if str(params[p.name]) not in p.choices:
                    raise ValueError(f"Valor inválido para {p.label}")
            if p.type == "int" and params.get(p.name) not in (None, ""):
                try:
                    params[p.name] = int(params[p.name])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{p.label} deve ser inteiro") from exc
            if p.type == "bool" and params.get(p.name) is not None:
                val = params[p.name]
                if isinstance(val, str):
                    params[p.name] = val.lower() in {"1", "true", "yes", "sim"}
                else:
                    params[p.name] = bool(val)

    def _run_job(self, job_id: str, cap: Capability) -> None:
        rec = self.store.get_job(job_id)
        if rec is None:
            return
        acquired = self._sem.acquire(timeout=min(30, self.settings.default_job_timeout_sec))
        if not acquired:
            rec.status = JobState.FAILED.value
            rec.human_message = "Não foi possível adquirir slot de execução."
            rec.finished_at = _utcnow()
            self.store.update_job(rec)
            self._emit(job_id, {"type": "status", "job": rec.to_public()})
            self._emit(job_id, None)
            return

        try:
            self._execute_job(job_id, cap)
        except Exception as exc:  # noqa: BLE001 — last-resort job failure surface
            rec = self.store.get_job(job_id) or rec
            rec.status = JobState.FAILED.value
            rec.technical_code = "RUNNER_EXCEPTION"
            rec.human_message = f"Falha interna do runner: {redact_text(str(exc))}"
            rec.attention = "blocked_technical"
            rec.finished_at = _utcnow()
            self.store.update_job(rec)
            self._log(job_id, "system", "error", redact_text(str(exc)))
            self._emit(job_id, {"type": "status", "job": rec.to_public()})
            self._emit(job_id, None)
        finally:
            self._sem.release()

    def _execute_job(self, job_id: str, cap: Capability) -> None:
        rec = self.store.get_job(job_id)
        if rec is None:
            return
        rec.status = JobState.VALIDATING.value
        rec.human_message = "Validando parâmetros e pré-requisitos."
        self.store.update_job(rec)
        self._emit(job_id, {"type": "status", "job": rec.to_public()})
        self._log(job_id, "system", "info", f"Iniciando {cap.id}")

        rec.status = JobState.RUNNING.value
        rec.started_at = _utcnow()
        rec.human_message = "Em execução — acompanhe o progresso nos logs."
        self.store.update_job(rec)
        self._emit(job_id, {"type": "status", "job": rec.to_public()})

        timeout = cap.timeout_sec or self.settings.default_job_timeout_sec
        job_dir = Path(rec.stdout_path or str(self.settings.jobs_dir / job_id / "stdout.log")).parent
        job_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(rec.stdout_path or job_dir / "stdout.log")
        stderr_path = Path(rec.stderr_path or job_dir / "stderr.log")

        try:
            proc = subprocess.Popen(
                rec.canonical_command,
                cwd=str(Path(__file__).resolve().parents[2]),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                bufsize=1,
            )
        except OSError as exc:
            rec.status = JobState.FAILED.value
            rec.exit_code = 127
            rec.human_message = f"Falha ao iniciar processo: {exc}"
            rec.finished_at = _utcnow()
            self.store.update_job(rec)
            self._log(job_id, "system", "error", redact_text(str(exc)))
            self._emit(job_id, {"type": "status", "job": rec.to_public()})
            self._emit(job_id, None)
            return

        with self._lock:
            self._processes[job_id] = proc
        rec.pid = proc.pid
        self.store.update_job(rec)

        stdout_buf: list[str] = []
        stderr_buf: list[str] = []
        total_bytes = 0

        def pump(stream: Any, name: str, buf: list[str], file_path: Path) -> None:
            nonlocal total_bytes
            try:
                with open(file_path, "w", encoding="utf-8") as file_obj:
                    for line in iter(stream.readline, ""):
                        if not line:
                            break
                        safe = redact_text(line.rstrip("\n"))
                        buf.append(safe)
                        total_bytes += len(safe)
                        if total_bytes < self.settings.max_log_bytes_per_job:
                            file_obj.write(safe + "\n")
                            file_obj.flush()
                            self._log(job_id, name, "info", safe)
                            self._emit(job_id, {"type": "log", "stream": name, "message": safe})
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        t_out = threading.Thread(
            target=pump, args=(proc.stdout, "stdout", stdout_buf, stdout_path), daemon=True
        )
        t_err = threading.Thread(
            target=pump, args=(proc.stderr, "stderr", stderr_buf, stderr_path), daemon=True
        )
        t_out.start()
        t_err.start()

        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            rec.status = JobState.CANCELLING.value
            self.store.update_job(rec)
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

        t_out.join(timeout=5)
        t_err.join(timeout=5)

        with self._lock:
            self._processes.pop(job_id, None)

        rec = self.store.get_job(job_id) or rec
        cancelled = rec.cancel_requested
        exit_code = proc.returncode if proc.returncode is not None else -1
        stdout = "\n".join(stdout_buf[-500:])
        stderr = "\n".join(stderr_buf[-500:])
        parser = cap.parse_result or default_parse
        parsed = parser(exit_code, stdout, stderr, rec.params)
        if timed_out or cancelled:
            status = normalize_exit(
                exit_code, cancelled=cancelled, timed_out=timed_out, stdout=stdout, stderr=stderr
            )
            public = public_status_dict(status)
        else:
            public = {
                "state": parsed.get("state") or JobState.FAILED.value,
                "technical_code": parsed.get("technical_code"),
                "human_message": parsed.get("human_message"),
                "attention": parsed.get("attention"),
                "next_action": parsed.get("next_action"),
            }

        finished = _utcnow()
        started = (
            datetime.fromisoformat(rec.started_at)
            if rec.started_at
            else datetime.now(timezone.utc)
        )
        duration = int((datetime.fromisoformat(finished) - started).total_seconds() * 1000)
        rec.status = public["state"]
        rec.technical_code = public.get("technical_code")
        rec.human_message = public.get("human_message")
        rec.attention = public.get("attention")
        rec.next_action = public.get("next_action")
        rec.exit_code = exit_code
        rec.finished_at = finished
        rec.duration_ms = duration
        rec.artifacts = list(parsed.get("artifacts") or [])
        rec.output_paths = list(parsed.get("artifacts") or [])
        rec.blocker = parsed.get("blocker")
        rec.manifests = list(parsed.get("manifests") or [])
        rec.run_id = parsed.get("run_id")
        self.store.update_job(rec)
        self.store.audit(
            "system",
            "job.finished",
            {"job_id": job_id, "status": rec.status, "exit_code": exit_code},
        )
        self._log(job_id, "system", "info", f"Finalizado: {rec.status}")
        self._emit(job_id, {"type": "status", "job": rec.to_public()})
        self._emit(job_id, None)

    def cancel(self, job_id: str, actor: str = "local-user") -> JobRecord:
        rec = self.store.get_job(job_id)
        if rec is None:
            raise KeyError(job_id)
        cap = self.registry.get(rec.capability_id)
        if cap and not cap.allow_cancel:
            raise ValueError("Esta capability não permite cancelamento.")
        if rec.status not in {
            JobState.QUEUED.value,
            JobState.VALIDATING.value,
            JobState.RUNNING.value,
        }:
            raise ValueError("Job não está em estado cancelável.")
        rec.cancel_requested = True
        rec.status = JobState.CANCELLING.value
        rec.human_message = "Cancelamento solicitado — aguardando o processo encerrar."
        self.store.update_job(rec)
        self.store.audit(actor, "job.cancel", {"job_id": job_id})
        with self._lock:
            proc = self._processes.get(job_id)
        if proc and proc.poll() is None:
            proc.terminate()
            time.sleep(0.3)
            if proc.poll() is None:
                proc.kill()
        self._emit(job_id, {"type": "status", "job": rec.to_public()})
        return rec

    def subscribe(self, job_id: str) -> queue.Queue[dict[str, Any] | None]:
        q: queue.Queue[dict[str, Any] | None] = queue.Queue()
        with self._lock:
            self._subscribers.setdefault(job_id, []).append(q)
        # replay recent logs
        for row in self.store.get_logs(job_id, after_id=0, limit=200):
            q.put({"type": "log", "stream": row["stream"], "message": row["message"], "ts": row["ts"]})
        rec = self.store.get_job(job_id)
        if rec:
            q.put({"type": "status", "job": rec.to_public()})
            if rec.status not in {
                JobState.QUEUED.value,
                JobState.VALIDATING.value,
                JobState.RUNNING.value,
                JobState.CANCELLING.value,
            }:
                q.put(None)
        return q

    def unsubscribe(self, job_id: str, q: queue.Queue[dict[str, Any] | None]) -> None:
        with self._lock:
            subs = self._subscribers.get(job_id, [])
            if q in subs:
                subs.remove(q)

    def _emit(self, job_id: str, event: dict[str, Any] | None) -> None:
        with self._lock:
            subs = list(self._subscribers.get(job_id, []))
        for q in subs:
            try:
                q.put(event)
            except Exception:
                pass

    def _log(self, job_id: str, stream: str, level: str, message: str) -> None:
        self.store.append_log(job_id, stream, level, redact_text(message))
