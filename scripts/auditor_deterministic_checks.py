#!/usr/bin/env python3
"""
Deterministic subset of Auditor checks for B2G Report.

Extracts checks C6, C8, C9, C12, C13, C14 from the Auditor prompt
into programmatic validation. These checks are binary and verifiable
without LLM judgment.

Runs BEFORE the LLM Auditor agent to:
  1. Catch obvious failures faster (no LLM latency)
  2. Reduce LLM Auditor workload (focus on judgment calls)
  3. Provide deterministic, reproducible results

Checks implemented:
  C6:  MEI value limit (empresa.mei==true -> valor < R$81k)
  C8:  Link validity (link_valid==true or no link)
  C9:  Veto respect (risk_score.vetoed==true -> NAO RECOMENDADO)
  C12: Acervo not verified + PARTICIPAR -> flagged as risk
  C13: Price benchmark ACIMA + not mentioned in justificativa
  C14: Habilitacao coverage <30% + PARTICIPAR

Checks left to LLM Auditor (require judgment):
  C1:  Justificativa contains >=2 factual statements
  C2:  Distance mentioned in justificativa
  C3:  CAT required but unavailable flagged
  C4:  CNAE incompatible -> max AVALIAR
  C5:  Simples revenue warning mentioned
  C7:  Analise documental filled
  C10: Fiscal risk alto mentioned
  C11: No incorrect legal terms
  C15: Critical alerts in justificativa
  C16: Probability spread sensitivity noted

Usage:
    python scripts/auditor_deterministic_checks.py data.json
    python scripts/auditor_deterministic_checks.py data.json --fix  # Auto-fix (rebaixar)

Exit codes:
    0 = All deterministic checks passed
    1 = Failures found (details in stdout JSON)
"""
from __future__ import annotations

import argparse
import json
import sys
import io
from pathlib import Path
from typing import Any

def _fix_win_encoding():
    """Fix Windows console encoding — only call from __main__."""
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MEI_ANNUAL_LIMIT = 81_000.0  # R$ 81.000 MEI faturamento anual limit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edital_id(edital: dict, idx: int) -> str:
    """Return a human-readable identifier for an edital."""
    return (
        edital.get("_id")
        or edital.get("numero_controle_pncp")
        or f"idx:{idx}"
    )


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------

def _check_c6_mei_limit(edital: dict, empresa: dict, idx: int) -> dict | None:
    """C6: MEI value limit.

    If empresa.mei == True and edital.valor_estimado > R$81k, the edital
    exceeds the MEI annual revenue cap and must not be recommended.
    """
    if not empresa.get("mei"):
        return None

    valor = edital.get("valor_estimado") or edital.get("valor") or 0
    if not isinstance(valor, (int, float)):
        try:
            valor = float(valor)
        except (TypeError, ValueError):
            return None

    if valor > MEI_ANNUAL_LIMIT:
        return {
            "edital_idx": idx,
            "edital_id": _edital_id(edital, idx),
            "check": "C6",
            "status": "FAIL",
            "motivo": (
                f"Empresa MEI com valor estimado R${valor:,.2f} excede limite "
                f"anual MEI de R${MEI_ANNUAL_LIMIT:,.2f}. "
                f"Recomendacao atual: {edital.get('recomendacao', 'N/A')}"
            ),
        }
    return None


def _check_c8_link_valid(edital: dict, idx: int) -> dict | None:
    """C8: Link validity.

    If the edital has link_valid explicitly set to False, flag it.
    Skip if no link or link_valid is not set (absence != invalid).
    """
    link_valid = edital.get("link_valid")
    if link_valid is None:
        return None  # Not set, skip
    if link_valid is True:
        return None  # Valid, pass

    return {
        "edital_idx": idx,
        "edital_id": _edital_id(edital, idx),
        "check": "C8",
        "status": "FAIL",
        "motivo": (
            f"Link do edital marcado como invalido (link_valid=False). "
            f"URL: {edital.get('link', 'N/A')}"
        ),
    }


def _check_c9_veto_respected(edital: dict, idx: int) -> dict | None:
    """C9: Veto respect.

    If risk_score.vetoed == True, recomendacao MUST be NAO RECOMENDADO.
    This check applies to ALL editais regardless of current recomendacao.
    """
    risk_score = edital.get("risk_score", {})
    if not isinstance(risk_score, dict):
        return None

    if not risk_score.get("vetoed", False):
        return None  # Not vetoed, pass

    rec = (edital.get("recomendacao") or "").upper().strip()
    if rec in ("NAO RECOMENDADO", "NÃO RECOMENDADO", "DESCARTADO"):
        return None  # Correctly downgraded, pass

    return {
        "edital_idx": idx,
        "edital_id": _edital_id(edital, idx),
        "check": "C9",
        "status": "FAIL",
        "motivo": (
            f"Edital VETADO (risk_score.vetoed=true) mas recomendacao "
            f"e '{edital.get('recomendacao', 'N/A')}' em vez de "
            f"'NAO RECOMENDADO'. Veto deve ser respeitado incondicionalmente."
        ),
    }


def _check_c12_acervo_unverified(edital: dict, idx: int) -> dict | None:
    """C12: Acervo not verified + PARTICIPAR = risk.

    If acervo_status == 'NAO_VERIFICADO' and recomendacao == 'PARTICIPAR',
    the recommendation lacks technical qualification backing.
    """
    rec = (edital.get("recomendacao") or "").upper().strip()
    if rec != "PARTICIPAR":
        return None

    acervo_status = (edital.get("acervo_status") or "").upper().strip()
    if acervo_status != "NAO_VERIFICADO":
        return None

    return {
        "edital_idx": idx,
        "edital_id": _edital_id(edital, idx),
        "check": "C12",
        "status": "FAIL",
        "motivo": (
            f"Recomendacao PARTICIPAR mas acervo tecnico NAO_VERIFICADO. "
            f"Sem comprovacao de capacidade tecnica, recomendacao deve "
            f"ser rebaixada para AVALIAR COM CAUTELA."
        ),
    }


def _check_c13_price_above(edital: dict, idx: int) -> dict | None:
    """C13: Price benchmark ACIMA not addressed in justificativa.

    If price_benchmark.vs_estimado == 'ACIMA' and the justificativa does
    not mention the overpricing, the analyst failed to address a risk factor.
    """
    rec = (edital.get("recomendacao") or "").upper().strip()
    if rec != "PARTICIPAR":
        return None

    benchmark = edital.get("price_benchmark", {})
    if not isinstance(benchmark, dict):
        return None

    vs_estimado = (benchmark.get("vs_estimado") or "").upper().strip()
    if vs_estimado != "ACIMA":
        return None

    justificativa = (edital.get("justificativa") or "").lower()

    # Check if any price-related term is mentioned
    price_terms = ("acima", "superfaturad", "sobreprec", "sobrepreco", "sobrepreço", "acima do estimado", "preco elevado", "preço elevado")
    if any(term in justificativa for term in price_terms):
        return None  # Addressed, pass

    return {
        "edital_idx": idx,
        "edital_id": _edital_id(edital, idx),
        "check": "C13",
        "status": "FAIL",
        "motivo": (
            f"Price benchmark indica valor ACIMA do estimado mas "
            f"justificativa nao menciona sobrepreco/superfaturamento. "
            f"Risco de preco deve ser explicitamente enderecado."
        ),
    }


def _check_c14_low_habilitacao(edital: dict, idx: int) -> dict | None:
    """C14: Habilitacao coverage <30% + PARTICIPAR.

    If the habilitacao checklist coverage is below 30% and the edital
    is recommended as PARTICIPAR, qualification risk is too high.
    """
    rec = (edital.get("recomendacao") or "").upper().strip()
    if rec != "PARTICIPAR":
        return None

    # Navigate nested structure: habilitacao_analysis.habilitacao_checklist_25.cobertura_pct
    hab_analysis = edital.get("habilitacao_analysis", {})
    if not isinstance(hab_analysis, dict):
        return None

    checklist = hab_analysis.get("habilitacao_checklist_25", {})
    if not isinstance(checklist, dict):
        # Also try top-level habilitacao_checklist_25
        checklist = edital.get("habilitacao_checklist_25", {})
        if not isinstance(checklist, dict):
            return None

    cobertura = checklist.get("cobertura_pct")
    if cobertura is None:
        return None

    if not isinstance(cobertura, (int, float)):
        try:
            cobertura = float(cobertura)
        except (TypeError, ValueError):
            return None

    if cobertura >= 30:
        return None  # Coverage sufficient, pass

    return {
        "edital_idx": idx,
        "edital_id": _edital_id(edital, idx),
        "check": "C14",
        "status": "FAIL",
        "motivo": (
            f"Recomendacao PARTICIPAR mas cobertura de habilitacao e "
            f"apenas {cobertura:.0f}% (< 30%). Risco alto de inabilitacao. "
            f"Rebaixar para AVALIAR COM CAUTELA."
        ),
    }


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_deterministic_checks(data: dict) -> dict:
    """Run all deterministic Auditor checks on the report data.

    Args:
        data: Full report JSON (with empresa, editais, etc.)

    Returns:
        Dict with checks_run, checks_failed, failures, auto_fixes, verdict.
    """
    empresa = data.get("empresa", {})
    editais = data.get("editais", [])
    failures: list[dict] = []

    for idx, edital in enumerate(editais):
        # C9 applies to ALL editais (veto must always be respected)
        result = _check_c9_veto_respected(edital, idx)
        if result:
            failures.append(result)

        # C6 applies to all editais (MEI limit is absolute)
        result = _check_c6_mei_limit(edital, empresa, idx)
        if result:
            failures.append(result)

        # C8 applies to all editais (link validity is objective)
        result = _check_c8_link_valid(edital, idx)
        if result:
            failures.append(result)

        # C12, C13, C14 only apply to PARTICIPAR editais
        # (the individual check functions filter internally)
        result = _check_c12_acervo_unverified(edital, idx)
        if result:
            failures.append(result)

        result = _check_c13_price_above(edital, idx)
        if result:
            failures.append(result)

        result = _check_c14_low_habilitacao(edital, idx)
        if result:
            failures.append(result)

    checks_run = 6  # Number of distinct check types implemented
    checks_failed = len(set(f["check"] for f in failures)) if failures else 0

    return {
        "checks_run": checks_run,
        "checks_failed": checks_failed,
        "failures": failures,
        "auto_fixes": [],
        "verdict": "PASSED" if not failures else "FAILED",
    }


# ---------------------------------------------------------------------------
# Auto-fix logic
# ---------------------------------------------------------------------------

def apply_auto_fixes(data: dict, failures: list[dict]) -> list[str]:
    """Apply automatic fixes (rebaixar recomendacao) for deterministic failures.

    Mutates `data` in place. Returns list of human-readable fix descriptions.

    Fix rules:
        C6  (MEI limit exceeded)     -> rebaixar to NAO RECOMENDADO
        C9  (veto not respected)     -> rebaixar to NAO RECOMENDADO
        C12 (acervo unverified)      -> rebaixar to AVALIAR COM CAUTELA
        C13 (price above unaddressed)-> rebaixar to AVALIAR COM CAUTELA
        C14 (low habilitacao)        -> rebaixar to AVALIAR COM CAUTELA
    """
    editais = data.get("editais", [])
    fixes: list[str] = []

    # Group failures by edital index for efficient processing
    failures_by_idx: dict[int, list[dict]] = {}
    for f in failures:
        idx = f["edital_idx"]
        failures_by_idx.setdefault(idx, []).append(f)

    for idx, edital_failures in failures_by_idx.items():
        if idx >= len(editais):
            continue

        edital = editais[idx]
        edital_id = _edital_id(edital, idx)
        old_rec = edital.get("recomendacao", "N/A")
        checks_hit = [f["check"] for f in edital_failures]

        # Determine target recommendation (most severe wins)
        # C6 and C9 -> NAO RECOMENDADO (hard block)
        # C12, C13, C14 -> AVALIAR COM CAUTELA (soft downgrade)
        hard_block_checks = {"C6", "C9"}
        soft_downgrade_checks = {"C12", "C13", "C14"}

        has_hard_block = bool(hard_block_checks & set(checks_hit))

        if has_hard_block:
            new_rec = "NÃO RECOMENDADO"
        else:
            # Only soft-downgrade if current recommendation is PARTICIPAR
            current_upper = (old_rec or "").upper().strip()
            if current_upper == "PARTICIPAR":
                new_rec = "AVALIAR COM CAUTELA"
            else:
                # Already at AVALIAR COM CAUTELA or lower, no change needed
                continue

        # Skip if already at target or more restrictive
        current_upper = (old_rec or "").upper().strip()
        REC_SEVERITY = {
            "PARTICIPAR": 3,
            "AVALIAR COM CAUTELA": 2,
            "AVALIAR": 2,
            "NÃO RECOMENDADO": 1,
            "NAO RECOMENDADO": 1,
            "DESCARTADO": 0,
        }
        current_severity = REC_SEVERITY.get(current_upper, 2)
        new_severity = REC_SEVERITY.get(new_rec.upper(), 2)

        if new_severity >= current_severity:
            continue  # Already at same or more restrictive level

        edital["recomendacao"] = new_rec

        # Append fix note to justificativa
        fix_note = (
            f" [AUTO-FIX: Rebaixado de '{old_rec}' para '{new_rec}' "
            f"por checks deterministicos {', '.join(checks_hit)}]"
        )
        edital["justificativa"] = (edital.get("justificativa") or "") + fix_note

        fix_desc = (
            f"Edital {edital_id}: {old_rec} -> {new_rec} "
            f"(checks: {', '.join(checks_hit)})"
        )
        fixes.append(fix_desc)

    return fixes


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic Auditor checks for B2G Report data"
    )
    parser.add_argument(
        "json_path",
        help="Path to the report JSON file",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix failures by downgrading recommendations (mutates JSON)",
    )
    args = parser.parse_args()

    path = Path(args.json_path)
    if not path.exists():
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = run_deterministic_checks(data)

    if args.fix and result["failures"]:
        fix_descriptions = apply_auto_fixes(data, result["failures"])
        result["auto_fixes"] = fix_descriptions

        if fix_descriptions:
            # Write back the fixed JSON
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    # Output result as JSON to stdout
    print(json.dumps(result, ensure_ascii=False, indent=2))

    sys.exit(0 if result["verdict"] == "PASSED" else 1)


if __name__ == "__main__":
    _fix_win_encoding()
    main()
