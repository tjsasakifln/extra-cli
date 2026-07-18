"""Data reliability assessment for operators (DoD §2.4).

Makes untrusted / degraded data explicit and forbids bare percentages
that hide limitations behind generic scores.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, Sequence


class TrustLevel(str, Enum):
    """Operator-facing reliability of a data point or aggregate."""

    TRUSTED = "TRUSTED"
    DEGRADED = "DEGRADED"
    UNTRUSTED = "UNTRUSTED"
    UNKNOWN = "UNKNOWN"


# Freshness SLAs used for assessment (hours). Not claims of live readiness.
DEFAULT_FRESHNESS_SLA_HOURS = 24.0
DEFAULT_STALE_HARD_HOURS = 168.0  # 7 days → UNTRUSTED unless provenance overrides


@dataclass(frozen=True)
class ReliabilityAssessment:
    """Structured answer: is this data trustworthy for decision-making?"""

    trust_level: TrustLevel
    reasons: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    field_flags: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)

    def is_decision_safe(self) -> bool:
        return self.trust_level == TrustLevel.TRUSTED

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["trust_level"] = self.trust_level.value
        d["is_decision_safe"] = self.is_decision_safe()
        return d

    def human_summary(self) -> str:
        lines = [
            f"trust_level={self.trust_level.value}",
            f"decision_safe={self.is_decision_safe()}",
        ]
        if self.reasons:
            lines.append("reasons:")
            lines.extend(f"  - {r}" for r in self.reasons)
        if self.limitations:
            lines.append("limitations:")
            lines.extend(f"  - {lim}" for lim in self.limitations)
        if self.field_flags:
            lines.append("field_flags:")
            for k, v in sorted(self.field_flags.items()):
                lines.append(f"  - {k}: {v}")
        return "\n".join(lines)


def assess_data_reliability(
    *,
    age_hours: float | None = None,
    freshness_sla_hours: float = DEFAULT_FRESHNESS_SLA_HOURS,
    stale_hard_hours: float = DEFAULT_STALE_HARD_HOURS,
    required_fields: Sequence[str] | None = None,
    present_fields: Sequence[str] | None = None,
    provenance_ok: bool | None = None,
    source_health: str | None = None,
    sample_n: int | None = None,
    sample_min: int = 1,
    query_valid: bool | None = None,
    explicit_limitations: Iterable[str] | None = None,
) -> ReliabilityAssessment:
    """Classify reliability from observable signals (no silent greens)."""
    reasons: list[str] = []
    limitations: list[str] = list(explicit_limitations or [])
    field_flags: dict[str, str] = {}
    metrics: dict[str, Any] = {
        "age_hours": age_hours,
        "freshness_sla_hours": freshness_sla_hours,
        "sample_n": sample_n,
        "source_health": source_health,
        "provenance_ok": provenance_ok,
        "query_valid": query_valid,
    }

    # Missing required fields
    req = list(required_fields or [])
    present = set(present_fields or [])
    missing = [f for f in req if f not in present]
    for f in missing:
        field_flags[f] = "MISSING"
    if missing:
        reasons.append(f"campos obrigatórios ausentes: {', '.join(missing)}")
        limitations.append(
            "Campos essenciais ausentes — não trate o registro como completo."
        )

    # Query / consultation validity
    if query_valid is False:
        reasons.append("consulta inválida ou não executada")
        limitations.append(
            "Sem consulta válida — ausência de linhas não prova inexistência."
        )

    # Provenance
    if provenance_ok is False:
        reasons.append("provenance ausente ou inválida")
        limitations.append("Sem provenance por campo/fonte — dado não auditável.")

    # Source health
    health = (source_health or "").strip().lower()
    if health in {"down", "error", "failed", "unhealthy", "broken"}:
        reasons.append(f"source_health={source_health}")
        limitations.append("Fonte em falha — resultados podem estar incompletos.")
    elif health in {"degraded", "partial", "stale"}:
        reasons.append(f"source_health={source_health}")
        limitations.append("Fonte degradada — cobertura/freshness comprometidas.")

    # Sample size
    if sample_n is not None and sample_n < sample_min:
        reasons.append(f"sample_n={sample_n} < min={sample_min}")
        limitations.append(
            f"Amostra insuficiente (N={sample_n}); não generalizar percentuais."
        )

    # Freshness
    if age_hours is not None:
        if age_hours > stale_hard_hours:
            reasons.append(
                f"age_hours={age_hours:.1f} > hard SLA {stale_hard_hours:.0f}h"
            )
            limitations.append(
                f"Dado stale (>{stale_hard_hours:.0f}h) — não usar como oportunidade atual."
            )
        elif age_hours > freshness_sla_hours:
            reasons.append(
                f"age_hours={age_hours:.1f} > SLA {freshness_sla_hours:.0f}h"
            )
            limitations.append(
                f"Freshness acima do SLA ({freshness_sla_hours:.0f}h) — marcar DEGRADED."
            )

    # Trust level resolution (worst signal wins)
    if (
        query_valid is False
        or provenance_ok is False
        or health in {"down", "error", "failed", "unhealthy", "broken"}
        or (age_hours is not None and age_hours > stale_hard_hours)
        or (sample_n is not None and sample_n <= 0 and sample_min > 0)
        or (missing and len(missing) == len(req) and req)
    ):
        level = TrustLevel.UNTRUSTED
    elif (
        missing
        or health in {"degraded", "partial", "stale"}
        or (age_hours is not None and age_hours > freshness_sla_hours)
        or (sample_n is not None and sample_n < sample_min)
    ):
        level = TrustLevel.DEGRADED
    elif (
        age_hours is None
        and provenance_ok is None
        and query_valid is None
        and not health
        and sample_n is None
        and not req
    ):
        level = TrustLevel.UNKNOWN
        reasons.append("sinais insuficientes para classificar")
        limitations.append(
            "Sem sinais de freshness/provenance/consulta — trate como UNKNOWN."
        )
    else:
        level = TrustLevel.TRUSTED
        if not reasons:
            reasons.append("sinais dentro dos SLAs e campos presentes")

    return ReliabilityAssessment(
        trust_level=level,
        reasons=tuple(reasons),
        limitations=tuple(dict.fromkeys(limitations)),  # dedupe preserve order
        field_flags=field_flags,
        metrics=metrics,
    )


def bare_percentage_is_forbidden(
    *,
    percentage: float | None,
    denominator_n: int | None,
    limitations: Iterable[str] | None,
    metric_name: str = "coverage",
) -> dict[str, Any]:
    """DoD: do not hide limitations behind generic scores/percentages.

    A percentage without denominator N and without limitations is rejected.
    """
    lims = [x.strip() for x in (limitations or []) if str(x).strip()]
    ok = True
    messages: list[str] = []

    if percentage is None:
        return {
            "ok": True,
            "rule_id": "no_bare_percentage",
            "message": "Sem percentual — nada a esconder.",
            "metric_name": metric_name,
        }

    if denominator_n is None or denominator_n < 0:
        ok = False
        messages.append(
            f"{metric_name}={percentage}% sem denominador N — percentual genérico proibido."
        )
    elif denominator_n == 0:
        ok = False
        messages.append(
            f"{metric_name}={percentage}% com N=0 — não publique como cobertura."
        )

    if not lims:
        ok = False
        messages.append(
            f"{metric_name}={percentage}% sem limitações explícitas — esconde incerteza."
        )

    return {
        "ok": ok,
        "rule_id": "no_bare_percentage",
        "message": (
            "Percentual com N e limitações — OK."
            if ok
            else "; ".join(messages)
        ),
        "metric_name": metric_name,
        "percentage": percentage,
        "denominator_n": denominator_n,
        "limitations_count": len(lims),
    }


def format_percentage_with_context(
    *,
    percentage: float,
    numerator: int,
    denominator: int,
    limitations: Sequence[str],
    metric_name: str = "coverage",
) -> str:
    """Human-readable percentage that cannot be misread as a naked score."""
    check = bare_percentage_is_forbidden(
        percentage=percentage,
        denominator_n=denominator,
        limitations=limitations,
        metric_name=metric_name,
    )
    if not check["ok"]:
        raise ValueError(check["message"])
    lim_txt = "; ".join(limitations)
    return (
        f"{metric_name}={percentage:.2f}% "
        f"({numerator}/{denominator}); limitations: {lim_txt}"
    )


def attach_reliability_to_run_metadata(
    meta: dict[str, Any],
    assessment: ReliabilityAssessment,
) -> dict[str, Any]:
    """Embed reliability block into report run_metadata (mutates copy)."""
    out = dict(meta)
    out["data_reliability"] = assessment.to_dict()
    claims = dict(out.get("claims") or {})
    forbidden = list(claims.get("forbidden") or [])
    for phrase in (
        "Percentual sem denominador N",
        "Score/percentual sem limitações explícitas",
        "Dado UNTRUSTED apresentado como pronto para decisão",
    ):
        if phrase not in forbidden:
            forbidden.append(phrase)
    claims["forbidden"] = forbidden
    allowed = list(claims.get("allowed") or [])
    for phrase in (
        "Exibir trust_level TRUSTED|DEGRADED|UNTRUSTED|UNKNOWN",
        "Percentuais apenas com N e limitações",
    ):
        if phrase not in allowed:
            allowed.append(phrase)
    claims["allowed"] = allowed
    out["claims"] = claims
    return out


def _demo_assessments() -> list[dict[str, Any]]:
    cases = [
        assess_data_reliability(
            age_hours=2.0,
            required_fields=["url", "prazo"],
            present_fields=["url", "prazo"],
            provenance_ok=True,
            source_health="ok",
            sample_n=50,
            query_valid=True,
        ),
        assess_data_reliability(
            age_hours=48.0,
            required_fields=["url", "prazo"],
            present_fields=["url"],
            provenance_ok=True,
            source_health="degraded",
            sample_n=3,
            query_valid=True,
            explicit_limitations=["Amostra de smoke apenas"],
        ),
        assess_data_reliability(
            age_hours=200.0,
            provenance_ok=False,
            source_health="down",
            sample_n=0,
            query_valid=False,
        ),
        assess_data_reliability(),
    ]
    return [c.to_dict() for c in cases]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Avalia confiabilidade de dados e rejeita percentuais genéricos "
            "(DoD §2.4 — não esconder limitações)."
        )
    )
    p.add_argument("--json", action="store_true", help="Saída JSON")
    p.add_argument("--demo", action="store_true", help="Casos de demonstração")
    p.add_argument("--age-hours", type=float, default=None)
    p.add_argument("--sample-n", type=int, default=None)
    p.add_argument("--source-health", type=str, default=None)
    p.add_argument("--provenance-ok", choices=["true", "false", "unknown"], default="unknown")
    p.add_argument("--query-valid", choices=["true", "false", "unknown"], default="unknown")
    p.add_argument("--pct", type=float, default=None, help="Percentual a validar")
    p.add_argument("--denominator", type=int, default=None)
    p.add_argument(
        "--limitation",
        action="append",
        default=[],
        help="Limitação explícita (repetível)",
    )
    args = p.parse_args(argv)

    if args.demo:
        payload = {"demo": _demo_assessments()}
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            for i, row in enumerate(payload["demo"], 1):
                print(f"--- case {i} ---")
                print(json.dumps(row, indent=2, ensure_ascii=False))
        return 0

    def _tri(v: str) -> bool | None:
        if v == "true":
            return True
        if v == "false":
            return False
        return None

    assessment = assess_data_reliability(
        age_hours=args.age_hours,
        sample_n=args.sample_n,
        source_health=args.source_health,
        provenance_ok=_tri(args.provenance_ok),
        query_valid=_tri(args.query_valid),
        explicit_limitations=args.limitation,
    )
    pct_check = bare_percentage_is_forbidden(
        percentage=args.pct,
        denominator_n=args.denominator,
        limitations=args.limitation or assessment.limitations,
    )
    payload = {
        "assessment": assessment.to_dict(),
        "percentage_check": pct_check,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(assessment.human_summary())
        print("--- percentage_check ---")
        print(pct_check["message"])
        print(f"ok={pct_check['ok']}")
    # Fail-closed when operator asks for a bare percentage
    if args.pct is not None and not pct_check["ok"]:
        return 2
    if assessment.trust_level == TrustLevel.UNTRUSTED and args.pct is not None:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
