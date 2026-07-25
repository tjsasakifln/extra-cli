"""Geography fit for CONFENGE commercial queue.

Absence of UF is GEOGRAPHY_UNKNOWN — never treated as automatic geographic fit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

RULE_VERSION = "geography-fit-v1"


@dataclass
class GeographyFitResult:
    status: str  # PASS | FAIL | GEOGRAPHY_UNKNOWN | REVIEW_REQUIRED
    reason: str | None = None
    uf: str | None = None
    recovered_from: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    rule_version: str = RULE_VERSION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_geography(
    *,
    uf: str | None,
    allowed_ufs: list[str] | None,
    municipio: str | None = None,
    orgao_uf: str | None = None,
    supplier_uf: str | None = None,
    require_geography: bool = True,
) -> GeographyFitResult:
    """Classify geography for a contract or supplier aggregate.

    If allowed_ufs is empty/None, geography filter is not active → PASS with note.
    """
    allowed = [u.upper().strip() for u in (allowed_ufs or []) if u and str(u).strip()]
    if not require_geography or not allowed:
        return GeographyFitResult(
            status="PASS",
            reason="no_geography_filter",
            uf=(uf or orgao_uf or supplier_uf or None),
        )

    candidates: list[tuple[str, str]] = []
    for value, source in (
        (uf, "contract_uf"),
        (orgao_uf, "orgao_uf"),
        (supplier_uf, "supplier_cadastro_uf"),
    ):
        if value and str(value).strip():
            candidates.append((str(value).upper().strip()[:2], source))

    if not candidates:
        # municipio alone is insufficient without UF mapping table — REVIEW
        if municipio and str(municipio).strip():
            return GeographyFitResult(
                status="REVIEW_REQUIRED",
                reason="missing_geographic_evidence",
                evidence=[{"municipio": municipio, "note": "municipio_without_uf"}],
            )
        return GeographyFitResult(
            status="GEOGRAPHY_UNKNOWN",
            reason="missing_geographic_evidence",
            uf=None,
        )

    for val, source in candidates:
        if val in allowed:
            return GeographyFitResult(
                status="PASS",
                uf=val,
                recovered_from=source,
                evidence=[{"uf": val, "source": source}],
            )

    # Has UF but outside filter
    return GeographyFitResult(
        status="FAIL",
        reason="uf_outside_filter",
        uf=candidates[0][0],
        recovered_from=candidates[0][1],
        evidence=[{"uf": candidates[0][0], "source": candidates[0][1], "allowed": allowed}],
    )


def supplier_geography_from_contracts(
    contracts: list[dict[str, Any]],
    allowed_ufs: list[str],
    *,
    supplier_uf: str | None = None,
) -> GeographyFitResult:
    """Aggregate geography: PASS if any contract has recoverable in-filter UF."""
    allowed = [u.upper() for u in allowed_ufs if u]
    if not allowed:
        return GeographyFitResult(status="PASS", reason="no_geography_filter")

    known_in: list[str] = []
    known_out: list[str] = []
    unknown = 0
    for row in contracts:
        r = classify_geography(
            uf=row.get("uf"),
            allowed_ufs=allowed,
            municipio=row.get("municipio") or row.get("municipio_nome"),
            orgao_uf=row.get("orgao_uf"),
            supplier_uf=supplier_uf,
        )
        if r.status == "PASS" and r.uf:
            known_in.append(r.uf)
        elif r.status == "FAIL" and r.uf:
            known_out.append(r.uf)
        else:
            unknown += 1

    if known_in:
        return GeographyFitResult(
            status="PASS",
            uf=known_in[0],
            recovered_from="contract_aggregate",
            evidence=[{"ufs_in_filter": sorted(set(known_in)), "unknown_count": unknown}],
        )
    if unknown and not known_out:
        return GeographyFitResult(
            status="GEOGRAPHY_UNKNOWN",
            reason="missing_geographic_evidence",
            evidence=[{"unknown_contracts": unknown}],
        )
    if known_out and not known_in:
        return GeographyFitResult(
            status="FAIL",
            reason="uf_outside_filter",
            uf=known_out[0],
            evidence=[{"ufs_out": sorted(set(known_out))}],
        )
    return GeographyFitResult(
        status="REVIEW_REQUIRED",
        reason="missing_geographic_evidence",
    )
