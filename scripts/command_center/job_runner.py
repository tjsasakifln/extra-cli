"""Allowlisted job runner with SSE-friendly log streaming."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.command_center.capabilities.base import Availability, Capability, default_parse
from scripts.command_center.capabilities.registry import CapabilityRegistry
from scripts.command_center.config import Settings, git_sha
from scripts.command_center.redaction import redact_mapping, redact_text
from scripts.command_center.security import assert_argv_list
from scripts.command_center.status_normalize import JobState, normalize_exit, public_status_dict
from scripts.command_center.store import (
    NON_TERMINAL_STATES,
    TERMINAL_STATES,
    JobRecord,
    Store,
    TransitionResult,
)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


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
            phrase = (cap.confirmation_phrase or "CONFIRMO").strip()
            if not req.confirmation or req.confirmation.strip() != phrase:
                raise ValueError(f"Confirmação obrigatória. Digite exatamente: {phrase}")

        try:
            argv = assert_argv_list(cap.argv_builder(params))
        except Exception as exc:
            raise ValueError(f"Falha ao montar comando: {exc}") from exc

        job_id = str(uuid.uuid4())
        job_dir = self.settings.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        from scripts.command_center.store import workspace_for_capability

        wid, cid = workspace_for_capability(cap.id, params)
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
            workspace_id=wid,
            client_id=cid,
            project_id=str(params.get("project_id")) if params.get("project_id") else None,
        )
        self.store.create_job(rec)
        # Preset: last params per capability/workflow for rerun without retyping
        try:
            self.store.set_pref(f"last_params:{cap.id}", json.dumps(params, ensure_ascii=False))
        except (OSError, TypeError, ValueError):
            pass
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
            self._finish_terminal(
                job_id,
                target_state=JobState.FAILED.value,
                fields={
                    "human_message": "Não foi possível adquirir slot de execução.",
                    "attention": "blocked_technical",
                    "technical_code": "NO_SLOT",
                },
            )
            return

        try:
            self._execute_job(job_id, cap)
        except Exception as exc:  # noqa: BLE001 — last-resort job failure surface
            self._log(job_id, "system", "error", redact_text(str(exc)))
            # cancel_wins: exception concurrent with cancel → CANCELLED, not FAILED
            self._finish_terminal(
                job_id,
                target_state=JobState.FAILED.value,
                fields={
                    "technical_code": "RUNNER_EXCEPTION",
                    "human_message": f"Falha interna do runner: {redact_text(str(exc))}",
                    "attention": "blocked_technical",
                },
            )
        finally:
            self._sem.release()

    def _is_cancelled(self, job_id: str) -> bool:
        rec = self.store.get_job(job_id)
        return bool(rec and rec.cancel_requested)

    def _duration_ms(self, job_id: str, finished: str) -> int | None:
        rec = self.store.get_job(job_id)
        if not rec or not rec.started_at:
            return None
        try:
            return int(
                (datetime.fromisoformat(finished) - datetime.fromisoformat(rec.started_at)).total_seconds() * 1000
            )
        except ValueError:
            return None

    def _finish_terminal(
        self,
        job_id: str,
        *,
        target_state: str,
        fields: dict[str, Any] | None = None,
        exit_code: int | None = None,
    ) -> TransitionResult:
        """Single path for any terminal write: CAS + cancel_wins + one-shot side effects."""
        finished = _utcnow()
        payload: dict[str, Any] = dict(fields or {})
        if exit_code is not None:
            payload["exit_code"] = exit_code
        payload.setdefault("finished_at", finished)
        duration = self._duration_ms(job_id, finished)
        if duration is not None:
            payload.setdefault("duration_ms", duration)

        result = self.store.transition_job(
            job_id,
            expected_states=NON_TERMINAL_STATES,
            target_state=target_state,
            fields=payload,
            cancel_wins=True,
        )
        if result.applied and result.terminal_confirmed and result.record is not None:
            final_status = result.record.status
            self.store.audit(
                "system",
                "job.finished",
                {"job_id": job_id, "status": final_status, "exit_code": result.record.exit_code},
            )
            self._log(job_id, "system", "info", f"Finalizado: {final_status}")
            self._emit(job_id, {"type": "status", "job": result.record.to_public()})
            self._emit(job_id, None)
        elif result.record is not None and result.record.status in TERMINAL_STATES:
            # Already terminal — ensure stream closed for late subscribers without re-audit
            self._emit(job_id, {"type": "status", "job": result.record.to_public()})
            self._emit(job_id, None)
        return result

    def _finish_cancelled(self, job_id: str, *, exit_code: int | None = None) -> TransitionResult:
        status = normalize_exit(exit_code, cancelled=True)
        public = public_status_dict(status)
        return self._finish_terminal(
            job_id,
            target_state=JobState.CANCELLED.value,
            fields={
                "cancel_requested": True,
                "technical_code": public.get("technical_code"),
                "human_message": public.get("human_message"),
                "attention": public.get("attention"),
                "next_action": public.get("next_action"),
            },
            exit_code=exit_code,
        )

    def _execute_job(self, job_id: str, cap: Capability) -> None:
        rec = self.store.get_job(job_id)
        if rec is None:
            return
        if rec.cancel_requested:
            self._finish_cancelled(job_id)
            return

        rec = (
            self.store.patch_job(
                job_id,
                status=JobState.VALIDATING.value,
                human_message="Validando parâmetros e pré-requisitos.",
                attention="running",
            )
            or rec
        )
        self._emit(job_id, {"type": "status", "job": rec.to_public()})
        self._log(job_id, "system", "info", f"Iniciando {cap.id}")

        if self._is_cancelled(job_id):
            self._finish_cancelled(job_id)
            return

        # Guided workflows: in-process runner (path-free, manifest-primary deliverables)
        if cap.id.startswith("workflow."):
            self._execute_workflow(job_id, cap)
            return

        rec = (
            self.store.patch_job(
                job_id,
                status=JobState.RUNNING.value,
                started_at=_utcnow(),
                human_message="Em execução — acompanhe o progresso nos logs.",
                attention="running",
            )
            or rec
        )
        self._emit(job_id, {"type": "status", "job": rec.to_public()})

        if self._is_cancelled(job_id):
            self._finish_cancelled(job_id)
            return

        timeout = cap.timeout_sec or self.settings.default_job_timeout_sec
        job_dir = Path(rec.stdout_path or str(self.settings.jobs_dir / job_id / "stdout.log")).parent
        job_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(rec.stdout_path or job_dir / "stdout.log")
        stderr_path = Path(rec.stderr_path or job_dir / "stderr.log")
        argv = list(rec.canonical_command)

        try:
            # argv comes only from allowlisted capability builders (never shell=True).
            proc = subprocess.Popen(  # noqa: S603
                argv,
                cwd=str(Path(__file__).resolve().parents[2]),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                bufsize=1,
            )
        except OSError as exc:
            self._log(job_id, "system", "error", redact_text(str(exc)))
            self._finish_terminal(
                job_id,
                target_state=JobState.FAILED.value,
                fields={
                    "human_message": f"Falha ao iniciar processo: {exc}",
                    "attention": "blocked_technical",
                    "technical_code": "SPAWN_ERROR",
                },
                exit_code=127,
            )
            return

        # Cancel may have arrived while we were spawning
        if self._is_cancelled(job_id):
            proc.kill()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            self._finish_cancelled(job_id, exit_code=proc.returncode)
            return

        with self._lock:
            self._processes[job_id] = proc
        self.store.patch_job(job_id, pid=proc.pid)

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
                if stream is not None:
                    stream.close()

        t_out = threading.Thread(target=pump, args=(proc.stdout, "stdout", stdout_buf, stdout_path), daemon=True)
        t_err = threading.Thread(target=pump, args=(proc.stderr, "stderr", stderr_buf, stderr_path), daemon=True)
        t_out.start()
        t_err.start()

        timed_out = False
        # Poll so cancel is observed promptly without waiting full process end
        deadline = time.time() + timeout
        while True:
            if self._is_cancelled(job_id):
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        try:
                            proc.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            pass
                break
            if proc.poll() is not None:
                break
            if time.time() >= deadline:
                timed_out = True
                self.store.patch_job(job_id, status=JobState.CANCELLING.value)
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                break
            time.sleep(0.05)

        t_out.join(timeout=5)
        t_err.join(timeout=5)

        with self._lock:
            self._processes.pop(job_id, None)

        rec = self.store.get_job(job_id)
        if rec is None:
            self._emit(job_id, None)
            return
        exit_code = proc.returncode if proc.returncode is not None else -1
        # cancel_requested OR terminate/kill path: always CANCELLED (not FAILED)
        if rec.cancel_requested:
            self._finish_cancelled(job_id, exit_code=exit_code)
            return

        stdout = "\n".join(stdout_buf[-500:])
        stderr = "\n".join(stderr_buf[-500:])
        parser = cap.parse_result or default_parse
        parsed = parser(exit_code, stdout, stderr, rec.params)
        if timed_out:
            status = normalize_exit(exit_code, timed_out=True, stdout=stdout, stderr=stderr)
            public = public_status_dict(status)
        else:
            public = {
                "state": parsed.get("state") or JobState.FAILED.value,
                "technical_code": parsed.get("technical_code"),
                "human_message": parsed.get("human_message"),
                "attention": parsed.get("attention"),
                "next_action": parsed.get("next_action"),
            }

        # Atomic CAS finish — cancel_wins if cancel arrived after our local read
        result = self._finish_terminal(
            job_id,
            target_state=str(public["state"]),
            fields={
                "technical_code": public.get("technical_code"),
                "human_message": public.get("human_message"),
                "attention": public.get("attention"),
                "next_action": public.get("next_action"),
                "artifacts": list(parsed.get("artifacts") or []),
                "output_paths": list(parsed.get("artifacts") or []),
                "blocker": parsed.get("blocker"),
                "manifests": list(parsed.get("manifests") or []),
                "run_id": parsed.get("run_id"),
            },
            exit_code=exit_code,
        )
        # Enqueue human review only when WE confirmed BLOCKED_HUMAN (not cancel overwrite)
        if (
            result.applied
            and result.record
            and result.record.status == JobState.BLOCKED_HUMAN.value
        ):
            self.store.enqueue_review(
                title=f"Revisão necessária: {result.record.action}",
                source=result.record.capability_id,
                evidence=(
                    f"Job {job_id}; código {result.record.technical_code}; "
                    f"artifacts: {result.record.artifacts[:5]}"
                ),
                limitations=result.record.human_message or "Resultado depende de decisão humana.",
                risks="Usar o resultado sem revisão pode propagar classificação incorreta.",
                job_id=job_id,
                capability_id=result.record.capability_id,
                payload={
                    "technical_code": result.record.technical_code,
                    "artifacts": result.record.artifacts,
                },
            )

    def _execute_workflow(self, job_id: str, cap: Capability) -> None:
        """Run outcome-first workflow with structured progress + run-manifest."""
        from scripts.command_center.workflows.runner import run_workflow

        rec = self.store.get_job(job_id)
        if rec is None:
            return
        job_dir = Path(rec.stdout_path or str(self.settings.jobs_dir / job_id / "stdout.log")).parent
        deliverables_dir = job_dir / "deliverables"
        deliverables_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(rec.stdout_path or job_dir / "stdout.log")
        stderr_path = Path(rec.stderr_path or job_dir / "stderr.log")

        rec = (
            self.store.patch_job(
                job_id,
                status=JobState.RUNNING.value,
                started_at=_utcnow(),
                human_message="Executando fluxo guiado — acompanhe as etapas.",
                attention="running",
            )
            or rec
        )
        self._emit(job_id, {"type": "status", "job": rec.to_public()})
        self._emit(
            job_id,
            {
                "type": "progress",
                "stage_id": "preparing",
                "stage_label": "Preparando",
                "state": "running",
                "message": "Iniciando fluxo consultivo",
            },
        )

        progress_events: list[dict[str, Any]] = []

        def on_progress(ev: dict[str, Any]) -> None:
            progress_events.append(ev)
            msg = f"[{ev.get('stage_label')}] {ev.get('message') or ev.get('state')}"
            self._log(job_id, "stdout", "info", msg)
            self._emit(job_id, {"type": "progress", **ev})
            self._emit(job_id, {"type": "log", "stream": "stdout", "message": msg})

        # Cancel mid-workflow before heavy work completes
        if self._is_cancelled(job_id):
            self._finish_cancelled(job_id)
            return

        try:
            result = run_workflow(
                cap.id,
                dict(rec.params or {}),
                out_dir=deliverables_dir,
                code_sha=rec.code_sha or git_sha(),
                job_id=job_id,
                on_progress=on_progress,
            )
        except Exception as exc:  # noqa: BLE001
            self._log(job_id, "system", "error", redact_text(str(exc)))
            self._finish_terminal(
                job_id,
                target_state=JobState.FAILED.value,
                fields={
                    "technical_code": "WORKFLOW_ERROR",
                    "human_message": f"Falha no fluxo: {redact_text(str(exc))}",
                    "attention": "blocked_technical",
                },
                exit_code=1,
            )
            return

        # Cancel may have arrived while workflow was running
        if self._is_cancelled(job_id):
            self._finish_cancelled(job_id)
            return

        # Write compact stdout for audit
        try:
            stdout_path.write_text(
                json.dumps(
                    {
                        "workflow": cap.id,
                        "status": result.get("status"),
                        "message": result.get("message"),
                        "run_id": result.get("run_id"),
                        "manifest_path": result.get("manifest_path"),
                        "artifacts": result.get("artifacts") or [],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            stderr_path.write_text("", encoding="utf-8")
        except OSError:
            pass

        artifacts = list(result.get("artifacts") or [])
        manifests = [result["manifest_path"]] if result.get("manifest_path") else []
        status = result.get("status") or JobState.SUCCEEDED.value
        data_mode = result.get("data_mode") or (rec.params or {}).get("data_mode")
        blocked_statuses = {
            "BLOCKED_CONFIG",
            "BLOCKED_EXTERNAL",
            "BLOCKED_DATA",
            "BLOCKED_PERMISSION",
            "FAILED",
            "PARTIAL",
        }
        if status in blocked_statuses:
            human = result.get("message") or f"Fluxo {status}."
            attention = "blocked_external" if "EXTERNAL" in status else "blocked_technical"
            exit_code = int(result.get("exit_code") if result.get("exit_code") is not None else 1)
            tech = status
            if status == "BLOCKED_EXTERNAL":
                job_status = JobState.BLOCKED_EXTERNAL.value
            elif status == "PARTIAL":
                job_status = JobState.PARTIAL.value
            else:
                job_status = JobState.FAILED.value
        elif status == "SUCCEEDED" and result.get("empty"):
            human = result.get("message") or "Resultado vazio defensável — nenhum item na shortlist."
            attention = "empty"
            exit_code = 0
            tech = "WORKFLOW_OK"
            job_status = JobState.SUCCEEDED.value
        elif status == "SUCCEEDED":
            human = result.get("message") or "Fluxo concluído. Abra os entregáveis no navegador."
            if data_mode == "FIXTURE":
                human = f"[DEMONSTRAÇÃO] {human}"
            attention = "ok"
            exit_code = 0
            tech = "WORKFLOW_OK"
            job_status = JobState.SUCCEEDED.value
        else:
            human = result.get("message") or "Fluxo terminou com atenção."
            attention = "attention"
            exit_code = int(result.get("exit_code") if result.get("exit_code") is not None else 1)
            tech = status
            job_status = status if status in {s.value for s in JobState} else JobState.FAILED.value

        tr = self._finish_terminal(
            job_id,
            target_state=job_status,
            fields={
                "technical_code": tech,
                "human_message": human,
                "attention": attention,
                "artifacts": artifacts,
                "output_paths": artifacts,
                "manifests": manifests,
                "run_id": result.get("run_id"),
            },
            exit_code=exit_code,
        )

        # Enqueue review items only when our terminal write applied (not cancel overwrite)
        if tr.applied and tr.record and tr.record.status != JobState.CANCELLED.value:
            for item in result.get("reviews") or []:
                self.store.enqueue_review(
                    title=str(item.get("title") or "Revisão"),
                    source=cap.id,
                    evidence=str(item.get("evidence") or ""),
                    limitations=str(item.get("limitations") or ""),
                    risks=str(item.get("risks") or ""),
                    job_id=job_id,
                    capability_id=cap.id,
                    payload={
                        "item_key": item.get("item_key"),
                        "question": item.get("question"),
                        "content_hash": item.get("content_hash"),
                        "artifact_hashes": {"source": item.get("content_hash")},
                        "correctable_fields": item.get("correctable_fields") or [],
                        "progress_events": progress_events[-20:],
                    },
                )
            if tr.record:
                self._emit(
                    job_id,
                    {
                        "type": "manifest",
                        "path": result.get("manifest_path"),
                        "run_id": result.get("run_id"),
                        "artifacts": artifacts,
                    },
                )

    def cancel(self, job_id: str, actor: str = "local-user") -> JobRecord:
        rec = self.store.get_job(job_id)
        if rec is None:
            raise KeyError(job_id)
        cap = self.registry.get(rec.capability_id)
        if cap and not cap.allow_cancel:
            raise ValueError("Esta capability não permite cancelamento.")
        if rec.status == JobState.CANCELLED.value and rec.cancel_requested:
            return rec  # idempotent
        if rec.status in TERMINAL_STATES:
            raise ValueError("Job não está em estado cancelável.")

        tr = self.store.request_cancel(job_id)
        if tr.record is None:
            raise KeyError(job_id)
        rec = tr.record
        if tr.outcome == "already_terminal":
            if rec.status == JobState.CANCELLED.value:
                return rec
            raise ValueError("Job não está em estado cancelável.")

        self.store.audit(actor, "job.cancel", {"job_id": job_id})
        with self._lock:
            proc = self._processes.get(job_id)
        if proc and proc.poll() is None:
            # Terminate/kill is cancel-driven — worker will map to CANCELLED, not FAILED
            proc.terminate()
            try:
                proc.wait(timeout=0.3)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass

        # If worker has not claimed a live process and job never started, finalize CANCELLED now
        with self._lock:
            still = self._processes.get(job_id)
        latest = self.store.get_job(job_id)
        if (
            still is None
            and latest
            and latest.cancel_requested
            and latest.status == JobState.CANCELLING.value
            and latest.pid is None
            and latest.started_at is None
        ):
            # QUEUED / pre-RUNNING: no worker progress yet — confirm terminal here
            # (worker may also try; only first CAS applies)
            self._finish_cancelled(job_id)
            latest = self.store.get_job(job_id) or rec
            return latest

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
            q.put(event)

    def _log(self, job_id: str, stream: str, level: str, message: str) -> None:
        self.store.append_log(job_id, stream, level, redact_text(message))
