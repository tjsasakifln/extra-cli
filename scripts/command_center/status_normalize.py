"""Normalize CLI/job outcomes into human-readable Command Center states."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class JobState(StrEnum):
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    RUNNING = "RUNNING"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    SUCCEEDED = "SUCCEEDED"
    SUCCEEDED_WITH_WARNINGS = "SUCCEEDED_WITH_WARNINGS"
    PARTIAL = "PARTIAL"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
    BLOCKED_HUMAN = "BLOCKED_HUMAN"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    UNAVAILABLE = "UNAVAILABLE"


class AttentionKind(StrEnum):
    HEALTHY = "healthy"
    ATTENTION = "attention"
    BLOCKED_EXTERNAL = "blocked_external"
    BLOCKED_TECHNICAL = "blocked_technical"
    AWAITING_HUMAN = "awaiting_human"
    NO_DATA = "no_data"
    RUNNING = "running"
    PARTIAL = "partial"
    PROVEN = "proven"


HUMAN_STATUS: dict[str, str] = {
    JobState.QUEUED: "Na fila — a execução ainda não começou.",
    JobState.VALIDATING: "Validando parâmetros e pré-requisitos.",
    JobState.RUNNING: "Em execução — acompanhe o progresso nos logs.",
    JobState.CANCELLING: "Cancelamento solicitado — aguardando o processo encerrar.",
    JobState.CANCELLED: "Cancelado por você antes de concluir.",
    JobState.SUCCEEDED: "Concluído com sucesso e com evidências registradas.",
    JobState.SUCCEEDED_WITH_WARNINGS: "Concluído, mas com avisos que merecem revisão.",
    JobState.PARTIAL: "Conclusão parcial — parte do trabalho ficou pendente.",
    JobState.BLOCKED_EXTERNAL: "Bloqueado por dependência externa (rede, fonte ou credencial).",
    JobState.BLOCKED_HUMAN: "Automação pronta, mas ainda precisa da sua decisão humana.",
    JobState.FAILED: "Falhou por erro técnico — revise os logs e a próxima ação.",
    JobState.TIMED_OUT: "Tempo esgotado — a execução foi interrompida por timeout.",
    JobState.UNAVAILABLE: "Ainda não disponível nesta versão do repositório.",
    "BLOCKED_INSUFFICIENT_HUMAN_LABELS": (
        "A automação foi concluída, mas o ranking ainda precisa da sua avaliação antes de qualquer uso comercial."
    ),
    "BLOCKED_HUMAN_DUAL_LABELING": ("Há evidência parcial, mas o aceite exige rotulagem humana independente."),
    "BLOCKED_EXTERNAL": "Dependência externa indisponível ou não validada.",
    "REAL_DATA_EVIDENCE_PENDING": "Falta evidência com dados reais para fechar este item.",
    "READY_FOR_HUMAN_ACCEPTANCE": "Pronto para revisão humana — nada foi aceito automaticamente.",
    "SUCCESS_ZERO": "Executou sem erro, porém não encontrou itens (resultado zero).",
    "PARTIAL": "Resultado parcial; não trate como sucesso completo.",
    "exit_code=2": "Código de saída 2 — geralmente bloqueio ou uso incorreto, não crash silencioso.",
}


@dataclass(frozen=True)
class NormalizedStatus:
    state: JobState
    technical_code: str
    human_message: str
    attention: AttentionKind
    next_action: str | None = None


def translate_status(code: str | None) -> str:
    if not code:
        return "Status não informado."
    if code in HUMAN_STATUS:
        return HUMAN_STATUS[code]
    upper = code.upper()
    for key, msg in HUMAN_STATUS.items():
        if key.upper() in upper or upper in key.upper():
            return msg
    return f"Estado técnico: {code}. Revise os detalhes e a evidência associada."


def attention_for_state(state: JobState) -> AttentionKind:
    mapping = {
        JobState.SUCCEEDED: AttentionKind.PROVEN,
        JobState.SUCCEEDED_WITH_WARNINGS: AttentionKind.ATTENTION,
        JobState.PARTIAL: AttentionKind.PARTIAL,
        JobState.BLOCKED_EXTERNAL: AttentionKind.BLOCKED_EXTERNAL,
        JobState.BLOCKED_HUMAN: AttentionKind.AWAITING_HUMAN,
        JobState.FAILED: AttentionKind.BLOCKED_TECHNICAL,
        JobState.TIMED_OUT: AttentionKind.BLOCKED_TECHNICAL,
        JobState.RUNNING: AttentionKind.RUNNING,
        JobState.QUEUED: AttentionKind.RUNNING,
        JobState.VALIDATING: AttentionKind.RUNNING,
        JobState.CANCELLING: AttentionKind.RUNNING,
        JobState.CANCELLED: AttentionKind.ATTENTION,
        JobState.UNAVAILABLE: AttentionKind.NO_DATA,
    }
    return mapping.get(state, AttentionKind.ATTENTION)


def normalize_exit(
    exit_code: int | None,
    *,
    cancelled: bool = False,
    timed_out: bool = False,
    stdout: str = "",
    stderr: str = "",
    blocker: str | None = None,
) -> NormalizedStatus:
    combined = f"{stdout}\n{stderr}\n{blocker or ''}".upper()
    if timed_out:
        return NormalizedStatus(
            JobState.TIMED_OUT,
            "TIMED_OUT",
            translate_status(JobState.TIMED_OUT),
            AttentionKind.BLOCKED_TECHNICAL,
            "Reexecute com timeout maior ou investigue a lentidão da fonte.",
        )
    if cancelled:
        return NormalizedStatus(
            JobState.CANCELLED,
            "CANCELLED",
            translate_status(JobState.CANCELLED),
            AttentionKind.ATTENTION,
            "Reexecute se a ação ainda for necessária.",
        )
    if blocker:
        if "HUMAN" in blocker.upper() or "LABEL" in blocker.upper() or "ACCEPTANCE" in blocker.upper():
            return NormalizedStatus(
                JobState.BLOCKED_HUMAN,
                blocker,
                translate_status(blocker),
                AttentionKind.AWAITING_HUMAN,
                "Abra a fila de revisão humana e decida com base nas evidências.",
            )
        if "EXTERNAL" in blocker.upper() or "NETWORK" in blocker.upper() or "AUTH" in blocker.upper():
            return NormalizedStatus(
                JobState.BLOCKED_EXTERNAL,
                blocker,
                translate_status(blocker),
                AttentionKind.BLOCKED_EXTERNAL,
                "Verifique conectividade, credenciais e status da fonte externa.",
            )
        return NormalizedStatus(
            JobState.FAILED,
            blocker,
            translate_status(blocker),
            AttentionKind.BLOCKED_TECHNICAL,
            "Consulte os logs e a documentação da capability.",
        )
    if "BLOCKED_HUMAN" in combined or "INSUFFICIENT_HUMAN" in combined or "READY_FOR_HUMAN" in combined:
        code = "BLOCKED_HUMAN"
        for token in (
            "BLOCKED_INSUFFICIENT_HUMAN_LABELS",
            "BLOCKED_HUMAN_DUAL_LABELING",
            "READY_FOR_HUMAN_ACCEPTANCE",
        ):
            if token in combined:
                code = token
                break
        return NormalizedStatus(
            JobState.BLOCKED_HUMAN,
            code,
            translate_status(code),
            AttentionKind.AWAITING_HUMAN,
            "Revise e registre sua decisão humana.",
        )
    if "BLOCKED_EXTERNAL" in combined:
        return NormalizedStatus(
            JobState.BLOCKED_EXTERNAL,
            "BLOCKED_EXTERNAL",
            translate_status("BLOCKED_EXTERNAL"),
            AttentionKind.BLOCKED_EXTERNAL,
            "Trate a dependência externa antes de reexecutar.",
        )
    if "PARTIAL" in combined or "SUCCESS_ZERO" in combined:
        code = "SUCCESS_ZERO" if "SUCCESS_ZERO" in combined else "PARTIAL"
        return NormalizedStatus(
            JobState.PARTIAL,
            code,
            translate_status(code),
            AttentionKind.PARTIAL,
            "Revise o que faltou e complete a etapa pendente.",
        )
    if "WARNING" in combined or "WARNINGS" in combined:
        if exit_code == 0:
            return NormalizedStatus(
                JobState.SUCCEEDED_WITH_WARNINGS,
                "SUCCEEDED_WITH_WARNINGS",
                translate_status(JobState.SUCCEEDED_WITH_WARNINGS),
                AttentionKind.ATTENTION,
                "Leia os avisos antes de usar o resultado comercialmente.",
            )
    if exit_code == 0:
        return NormalizedStatus(
            JobState.SUCCEEDED,
            "SUCCEEDED",
            translate_status(JobState.SUCCEEDED),
            AttentionKind.PROVEN,
            None,
        )
    if exit_code == 2:
        return NormalizedStatus(
            JobState.BLOCKED_EXTERNAL if "EXTERNAL" in combined else JobState.FAILED,
            "exit_code=2",
            translate_status("exit_code=2"),
            AttentionKind.BLOCKED_TECHNICAL,
            "Verifique parâmetros e pré-requisitos da capability.",
        )
    return NormalizedStatus(
        JobState.FAILED,
        f"exit_code={exit_code}",
        translate_status(JobState.FAILED),
        AttentionKind.BLOCKED_TECHNICAL,
        "Inspecione stderr e corrija a causa raiz.",
    )


def public_status_dict(status: NormalizedStatus) -> dict[str, Any]:
    return {
        "state": status.state.value,
        "technical_code": status.technical_code,
        "human_message": status.human_message,
        "attention": status.attention.value,
        "next_action": status.next_action,
    }
