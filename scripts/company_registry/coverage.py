"""Honest coverage metrics for official registry vs commercial universe."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterable

from scripts.company_registry.lookup import batch_lookup, lookup_cnpj, read_active_pointer
from scripts.company_registry.models import OfficialMatchStatus, SITUACAO_BLOCK_PROMOTION
from scripts.company_registry.normalization import is_valid_cnpj14, normalize_cnpj14


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compute_coverage(
    candidates: Iterable[str],
    *,
    ranking_eligible: Iterable[str] | None = None,
    top20: Iterable[str] | None = None,
    release_id: str | None = None,
) -> dict[str, Any]:
    """Compute the four campaign metrics + gap lists.

    Denominators are never shrunk to hit targets.
    OFFICIAL_REGISTRY_UNAVAILABLE is counted separately, not as cadastral absence.
    """
    all_raw = list(candidates)
    eligible = list(ranking_eligible) if ranking_eligible is not None else list(all_raw)
    top = list(top20 or [])

    ptr = read_active_pointer()
    active_id = release_id or (ptr or {}).get("release_id")
    registry_available = bool(ptr and ptr.get("status") == "ACTIVE") or bool(release_id)

    def _analyze(cnpjs: list[str]) -> dict[str, Any]:
        missing = 0
        invalid = 0
        valid = 0
        matched = 0
        not_found = 0
        unavailable = 0
        ambiguous = 0
        usable = 0
        gaps: list[dict[str, Any]] = []
        for raw in cnpjs:
            c = normalize_cnpj14(raw)
            if not c:
                missing += 1
                gaps.append({"cnpj": raw, "status": "MISSING_CNPJ"})
                continue
            if not is_valid_cnpj14(c):
                invalid += 1
                gaps.append({"cnpj": c, "status": "INVALID_CNPJ"})
                continue
            valid += 1
            if not registry_available and not release_id:
                unavailable += 1
                gaps.append({"cnpj": c, "status": "OFFICIAL_REGISTRY_UNAVAILABLE"})
                continue
            rec = lookup_cnpj(c, release_id=active_id)
            st = rec.official_match_status
            if st == OfficialMatchStatus.MATCHED.value:
                matched += 1
                if rec.is_commercially_usable:
                    usable += 1
                else:
                    gaps.append(
                        {
                            "cnpj": c,
                            "status": "MATCHED_NOT_USABLE",
                            "registration_status": rec.registration_status,
                            "primary_cnae": rec.primary_cnae,
                        }
                    )
            elif st == OfficialMatchStatus.NOT_FOUND_IN_OFFICIAL_RELEASE.value:
                not_found += 1
                gaps.append({"cnpj": c, "status": st})
            elif st == OfficialMatchStatus.OFFICIAL_REGISTRY_UNAVAILABLE.value:
                unavailable += 1
                gaps.append({"cnpj": c, "status": st})
            elif st == OfficialMatchStatus.AMBIGUOUS_SOURCE_RECORD.value:
                ambiguous += 1
                gaps.append({"cnpj": c, "status": st})
            else:
                gaps.append({"cnpj": c, "status": st})
        n = len(cnpjs)
        # structural
        valid_cnpj_share = round(valid / n, 6) if n else None
        # official match on valid only — unavailable not in not_found
        # denominator = valid; unavailable rows reduce match rate (honest)
        official_match_coverage = round(matched / valid, 6) if valid else None
        commercial_usable = round(usable / n, 6) if n else None
        return {
            "n": n,
            "missing_cnpj": missing,
            "invalid_cnpj": invalid,
            "valid_cnpj": valid,
            "matched": matched,
            "not_found": not_found,
            "unavailable": unavailable,
            "ambiguous": ambiguous,
            "usable": usable,
            "valid_cnpj_share": valid_cnpj_share,
            "official_match_coverage": official_match_coverage,
            "commercial_registry_usable_coverage": commercial_usable,
            "gaps_sample": gaps[:100],
            "gaps_n": len(gaps),
            "not_found_list": [g["cnpj"] for g in gaps if g.get("status") == "NOT_FOUND_IN_OFFICIAL_RELEASE"],
        }

    all_stats = _analyze(all_raw)
    elig_stats = _analyze(eligible)
    top_stats = _analyze(top) if top else {
        "n": 0,
        "matched": 0,
        "official_match_coverage": None,
        "commercial_registry_usable_coverage": None,
    }

    top20_official = None
    if top:
        # Top20 requires MATCHED + situação + CNAE + release
        ok_n = 0
        for raw in top:
            rec = lookup_cnpj(raw, release_id=active_id)
            if (
                rec.official_match_status == OfficialMatchStatus.MATCHED.value
                and rec.registration_status
                and rec.primary_cnae
                and rec.official_release_id
                and str(rec.registration_status).upper() not in SITUACAO_BLOCK_PROMOTION
            ):
                ok_n += 1
        top20_official = round(ok_n / len(top), 6)

    targets = {
        "official_match_coverage_min": 0.995,
        "commercial_registry_usable_coverage_min": 0.98,
        "top20_official_registry_coverage_min": 1.0,
    }
    gates = {
        "official_match_coverage_ok": (
            all_stats["official_match_coverage"] is not None
            and all_stats["official_match_coverage"] >= targets["official_match_coverage_min"]
        ),
        "commercial_usable_ok": (
            elig_stats["commercial_registry_usable_coverage"] is not None
            and elig_stats["commercial_registry_usable_coverage"]
            >= targets["commercial_registry_usable_coverage_min"]
        ),
        "top20_official_ok": top20_official is not None and top20_official >= 1.0,
        "registry_available": registry_available,
    }

    return {
        "schema_version": "official-registry-coverage-v1",
        "generated_at": utc_now(),
        "active_official_registry_release": active_id,
        "active_pointer": ptr,
        "candidates_total": all_stats["n"],
        "metrics": {
            "valid_cnpj_share": all_stats["valid_cnpj_share"],
            "official_match_coverage": all_stats["official_match_coverage"],
            "commercial_registry_usable_coverage": elig_stats[
                "commercial_registry_usable_coverage"
            ],
            "top20_official_registry_coverage": top20_official,
            # alias used by existing commercial code — same definition as official_match
            "official_registry_coverage": all_stats["official_match_coverage"],
        },
        "counts": {
            "all_candidates": all_stats,
            "ranking_eligible": elig_stats,
            "top20": top_stats,
        },
        "targets": targets,
        "gates": gates,
        "registry_ready": bool(
            gates["registry_available"] and gates["official_match_coverage_ok"]
        ),
        "ranking_ready": bool(
            gates["registry_available"]
            and gates["commercial_usable_ok"]
            and gates["top20_official_ok"]
        ),
        "notes": [
            "official_match_coverage denominator = valid CNPJs only; not gamed.",
            "OFFICIAL_REGISTRY_UNAVAILABLE is not counted as cadastral NOT_FOUND.",
            "Fallbacks outside this module must not inflate official metrics.",
        ],
    }
