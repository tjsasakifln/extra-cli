"""DoD «Estados, aplicabilidade e bloqueio» — reconstructable requirement states.

Policy (fail-closed):
- Unchecked items stay non-accepted even if partially implemented.
- PARTIAL never counts as DONE.
- BLOCKED stays visible until resolved or formal scope change.
- NOT_APPLICABLE requires justification + date + evidence + allowed basis.
- Missing source fields → SOURCE_UNAVAILABLE or NOT_READY (never 0, never DONE).
- Gates accept only DONE + legitimate NOT_APPLICABLE.
- State reconstructs from ledger JSON + DOD.md, without chat history.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = PROJECT_ROOT / "data" / "requirement_states" / "ledger.json"
DEFAULT_DOD = PROJECT_ROOT / "DOD.md"

# Legitimate bases for NOT_APPLICABLE (DoD text).
NA_BASES = frozenset(
    {
        "conditional_wording",  # redação permite aplicabilidade condicional
        "scope_decision_tiago",  # decisão de escopo registrada por Tiago
    }
)

# Field absence must never be coerced to numeric zero or DONE.
FIELD_ABSENCE_STATES = frozenset({"SOURCE_UNAVAILABLE", "NOT_READY"})


class RequirementState(StrEnum):
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    NOT_READY = "NOT_READY"
    DONE = "DONE"


# States that do NOT count as accepted for gates.
NON_ACCEPTED = frozenset(
    {
        RequirementState.OPEN,
        RequirementState.PARTIAL,
        RequirementState.BLOCKED,
        RequirementState.SOURCE_UNAVAILABLE,
        RequirementState.NOT_READY,
    }
)

GATE_ACCEPTED = frozenset(
    {
        RequirementState.DONE,
        RequirementState.NOT_APPLICABLE,
    }
)


@dataclass
class RequirementRecord:
    """Single requirement state with full reconstructability."""

    item_id: str
    title: str
    state: str
    dod_checkbox: str  # "[ ]" or "[x]"
    section: str = ""
    partial_note: str = ""
    owner: str = ""
    cause: str = ""
    next_test: str = ""
    evidence: list[str] = field(default_factory=list)
    # NOT_APPLICABLE fields
    na_basis: str = ""
    na_justification: str = ""
    na_date: str = ""
    # field-level absence
    field_name: str = ""
    updated_at: str = ""
    updated_by: str = ""

    def is_gate_accepted(self) -> bool:
        """True only for DONE/legitimate NA that pass validate_record."""
        try:
            st = RequirementState(self.state)
        except ValueError:
            return False
        if st not in GATE_ACCEPTED:
            return False
        return not validate_record(self)

    def is_accepted_item(self) -> bool:
        """Checkbox semantics: only DONE is 'accepted' as completed work.

        NOT_APPLICABLE is gate-complete but not a commercial promise flip without
        explicit NA record.
        """
        return (
            self.state == RequirementState.DONE.value
            and self.dod_checkbox.lower() == "[x]"
            and not validate_record(self)
        )


class RequirementStateError(ValueError):
    """Invalid transition or missing mandatory fields."""


def utc_now() -> str:
    return (
        datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _is_unchecked(checkbox: str) -> bool:
    normalized = checkbox.strip().lower().replace(" ", "")
    return normalized in {"[]", "[ ]"} or normalized == "[]" or checkbox.strip() in {
        "[ ]",
        "[]",
        "[  ]",
    }


def is_unchecked_non_accepted(record: RequirementRecord) -> bool:
    """Unchecked items remain non-accepted even when PARTIAL.

    Returns True when the item must NOT be treated as accepted.
    """
    cb = record.dod_checkbox.strip().lower().replace(" ", "")
    unchecked = cb in {"[]", "[ ]"} or record.dod_checkbox.strip() in {"[ ]", "[]", "[  ]"}
    if unchecked:
        # Unchecked is never accepted work, regardless of state label.
        return True
    # Checked only accepted if DONE and valid.
    return not (
        record.state == RequirementState.DONE.value and not validate_record(record)
    )


def validate_not_applicable(record: RequirementRecord) -> list[str]:
    """Return validation errors for a NOT_APPLICABLE record."""
    errs: list[str] = []
    if record.state != RequirementState.NOT_APPLICABLE.value:
        return errs
    if record.na_basis not in NA_BASES:
        errs.append(
            f"na_basis must be one of {sorted(NA_BASES)}; got {record.na_basis!r}"
        )
    if not (record.na_justification or "").strip():
        errs.append("na_justification required")
    if not (record.na_date or "").strip():
        errs.append("na_date required")
    if not record.evidence:
        errs.append("evidence required for NOT_APPLICABLE")
    return errs


def validate_blocked(record: RequirementRecord) -> list[str]:
    errs: list[str] = []
    if record.state != RequirementState.BLOCKED.value:
        return errs
    if not (record.owner or "").strip():
        errs.append("owner required for BLOCKED")
    if not (record.cause or "").strip():
        errs.append("cause required for BLOCKED")
    if not (record.next_test or "").strip():
        errs.append("next_test required for BLOCKED")
    return errs


def validate_field_absence(record: RequirementRecord) -> list[str]:
    errs: list[str] = []
    if record.state not in FIELD_ABSENCE_STATES:
        return errs
    if not (record.field_name or "").strip():
        errs.append("field_name required for SOURCE_UNAVAILABLE/NOT_READY")
    # Never encode absence as zero
    for ev in record.evidence:
        if re.search(r"\bvalue\s*=\s*0\b", ev, re.I) or re.search(
            r"\btreated_as_zero\b", ev, re.I
        ):
            errs.append("field absence must not be encoded as zero")
    return errs


def validate_record(record: RequirementRecord) -> list[str]:
    errs: list[str] = []
    try:
        st = RequirementState(record.state)
    except ValueError:
        return [f"unknown state {record.state!r}"]

    cb = record.dod_checkbox.strip().lower().replace(" ", "")
    unchecked = cb in {"[]", "[ ]"} or record.dod_checkbox.strip() in {"[ ]", "[]", "[  ]"}

    # Unchecked cannot be DONE
    if unchecked and st == RequirementState.DONE:
        errs.append("unchecked item cannot be DONE")

    # PARTIAL never checked
    if st == RequirementState.PARTIAL and not unchecked:
        errs.append("PARTIAL item must remain unchecked")

    # DONE requires evidence and checked box
    if st == RequirementState.DONE:
        if unchecked:
            errs.append("DONE requires checked checkbox")
        if not record.evidence:
            errs.append("DONE requires evidence")

    errs.extend(validate_not_applicable(record))
    errs.extend(validate_blocked(record))
    errs.extend(validate_field_absence(record))
    return errs


def gate_counts(records: list[RequirementRecord]) -> dict[str, Any]:
    """Gates count only DONE + legitimate NOT_APPLICABLE after validate_record."""
    by_state: dict[str, int] = {}
    accepted = 0
    rejected_na = 0
    rejected_done = 0
    non_accepted = 0
    for r in records:
        by_state[r.state] = by_state.get(r.state, 0) + 1
        errs = validate_record(r)
        try:
            st = RequirementState(r.state)
        except ValueError:
            non_accepted += 1
            continue
        if st == RequirementState.NOT_APPLICABLE:
            if errs:
                rejected_na += 1
                non_accepted += 1
            else:
                accepted += 1
        elif st == RequirementState.DONE:
            if errs:
                rejected_done += 1
                non_accepted += 1
            else:
                accepted += 1
        else:
            non_accepted += 1
    return {
        "by_state": by_state,
        "gate_accepted": accepted,
        "gate_non_accepted": non_accepted,
        "illegitimate_not_applicable": rejected_na,
        "illegitimate_done": rejected_done,
        "rule": "only DONE and legitimate NOT_APPLICABLE count as gate-complete",
    }


def parse_dod_checkbox_items(dod_text: str) -> list[dict[str, Any]]:
    """Parse checklist lines from DOD.md with section headers."""
    items: list[dict[str, Any]] = []
    section = ""
    for i, line in enumerate(dod_text.splitlines(), 1):
        hm = re.match(r"^(#{1,4})\s+(.*)$", line)
        if hm:
            section = hm.group(2).strip()
            continue
        m = re.match(r"^(\s*)-\s*\[([ xX])\]\s*(.*)$", line)
        if not m:
            continue
        checked = m.group(2).lower() == "x"
        body = m.group(3).strip()
        items.append(
            {
                "line": i,
                "section": section,
                "dod_checkbox": "[x]" if checked else "[ ]",
                "title": body[:240],
                "checked": checked,
            }
        )
    return items


def field_absence_status(
    *,
    field_name: str,
    source_consulted: bool,
    value_present: bool,
) -> str:
    """Map field availability to SOURCE_UNAVAILABLE or NOT_READY — never zero/DONE."""
    if value_present:
        raise RequirementStateError("value present is not an absence state")
    if not source_consulted:
        return RequirementState.NOT_READY.value
    return RequirementState.SOURCE_UNAVAILABLE.value


def coerce_absence_to_zero_forbidden(value: Any) -> None:
    """Fail-closed: callers must not convert absence into zero-like values."""
    if value is None:
        raise RequirementStateError(
            "field absence must not be silently recorded as None-as-zero"
        )
    if value == 0 or value == 0.0:
        raise RequirementStateError(
            "field absence must not be recorded as numeric zero"
        )
    if isinstance(value, str) and value.strip() in {"0", "0.0", "0,0"}:
        raise RequirementStateError(
            "field absence must not be recorded as string zero"
        )


def make_partial(
    item_id: str,
    title: str,
    note: str,
    *,
    evidence: list[str] | None = None,
    section: str = "",
) -> RequirementRecord:
    return RequirementRecord(
        item_id=item_id,
        title=title,
        state=RequirementState.PARTIAL.value,
        dod_checkbox="[ ]",
        section=section,
        partial_note=note,
        evidence=list(evidence or []),
        updated_at=utc_now(),
        updated_by="requirement_states",
    )


def make_blocked(
    item_id: str,
    title: str,
    *,
    owner: str,
    cause: str,
    next_test: str,
    evidence: list[str] | None = None,
    section: str = "",
) -> RequirementRecord:
    rec = RequirementRecord(
        item_id=item_id,
        title=title,
        state=RequirementState.BLOCKED.value,
        dod_checkbox="[ ]",
        section=section,
        owner=owner,
        cause=cause,
        next_test=next_test,
        evidence=list(evidence or []),
        updated_at=utc_now(),
        updated_by="requirement_states",
    )
    errs = validate_blocked(rec)
    if errs:
        raise RequirementStateError("; ".join(errs))
    return rec


def make_not_applicable(
    item_id: str,
    title: str,
    *,
    basis: str,
    justification: str,
    date: str,
    evidence: list[str],
    section: str = "",
) -> RequirementRecord:
    rec = RequirementRecord(
        item_id=item_id,
        title=title,
        state=RequirementState.NOT_APPLICABLE.value,
        dod_checkbox="[ ]",  # NA is not a silent commercial [x]
        section=section,
        na_basis=basis,
        na_justification=justification,
        na_date=date,
        evidence=list(evidence),
        updated_at=utc_now(),
        updated_by="requirement_states",
    )
    errs = validate_not_applicable(rec)
    if errs:
        raise RequirementStateError("; ".join(errs))
    return rec


def load_ledger(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path or DEFAULT_LEDGER)
    if not p.exists():
        return {
            "version": "1.0.0",
            "policy": "dod_estados_aplicabilidade_bloqueio",
            "records": [],
            "updated_at": None,
        }
    return json.loads(p.read_text(encoding="utf-8"))


def save_ledger(data: dict[str, Any], path: Path | str | None = None) -> Path:
    p = Path(path or DEFAULT_LEDGER)
    p.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = utc_now()
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def records_from_ledger(data: dict[str, Any]) -> list[RequirementRecord]:
    out: list[RequirementRecord] = []
    for raw in data.get("records") or []:
        out.append(RequirementRecord(**{k: raw[k] for k in RequirementRecord.__dataclass_fields__ if k in raw}))
    return out


def upsert_record(data: dict[str, Any], record: RequirementRecord) -> dict[str, Any]:
    errs = validate_record(record)
    if errs:
        raise RequirementStateError("; ".join(errs))
    records = data.setdefault("records", [])
    replaced = False
    payload = asdict(record)
    for i, r in enumerate(records):
        if r.get("item_id") == record.item_id:
            records[i] = payload
            replaced = True
            break
    if not replaced:
        records.append(payload)
    return data


def reconstruct(
    *,
    ledger_path: Path | str | None = None,
    dod_path: Path | str | None = None,
) -> dict[str, Any]:
    """Rebuild requirement view without chat history.

    Honesty bounds:
    - DOD.md inventory (all checkboxes) is always reconstructable from file.
    - Semantic states (PARTIAL/BLOCKED/NA/...) exist only for ledger-tracked items.
    - This does NOT claim a 1:1 semantic state for every DOD checkbox unless present
      in the ledger.
    """
    ledger = load_ledger(ledger_path)
    records = records_from_ledger(ledger)
    dod_text = Path(dod_path or DEFAULT_DOD).read_text(encoding="utf-8")
    dod_items = parse_dod_checkbox_items(dod_text)
    validation = {r.item_id: validate_record(r) for r in records}
    ledger_ids = {r.item_id for r in records}
    return {
        "reconstructed_at": utc_now(),
        "ledger_path": str(ledger_path or DEFAULT_LEDGER),
        "dod_path": str(dod_path or DEFAULT_DOD),
        "dod_item_count": len(dod_items),
        "dod_checked": sum(1 for i in dod_items if i["checked"]),
        "dod_open": sum(1 for i in dod_items if not i["checked"]),
        "ledger_records": len(records),
        "ledger_coverage_of_dod": {
            "tracked": len(ledger_ids),
            "dod_total": len(dod_items),
            "note": "Semantic states only for ledger-tracked items; DOD inventory is checkbox-level",
        },
        "gate": gate_counts(records),
        "validation_errors": {k: v for k, v in validation.items() if v},
        "sample_records": [asdict(r) for r in records[:20]],
        "policy": {
            "unchecked_remains_non_accepted": True,
            "partial_is_not_done": True,
            "blocked_stays_visible": True,
            "not_applicable_requires_justification_date_evidence": True,
            "field_absence_not_zero": True,
            "gates_only_done_and_legitimate_na": True,
            "reconstructable_without_chat": True,
            "reconstruct_scope": "ledger_records_plus_dod_checkbox_inventory",
        },
        "ok": not any(validation.values()),
        "claims_allowed": [
            "Ledger-tracked requirement states reconstruct from JSON without chat",
            "DOD checkbox inventory reconstructs from DOD.md without chat",
            "Gate counts use only validated DONE + legitimate NOT_APPLICABLE",
        ],
        "claims_forbidden": [
            "Every DOD checkbox has a semantic ledger state",
            "Campaign operational gate is fully driven by this module unless integrated",
        ],
    }


def seed_canonical_examples(ledger_path: Path | str | None = None) -> dict[str, Any]:
    """Seed ledger with examples that prove each policy branch (not commercial NA abuse)."""
    data = load_ledger(ledger_path)
    examples = [
        make_partial(
            "dod-state:unchecked-partial-demo",
            "Um item desmarcado permanece não aceito, mesmo que esteja parcialmente implementado.",
            note="Implementation started; checkbox stays open until QA+PO evidence.",
            evidence=["scripts/ops/requirement_states.py", "tests/test_requirement_states.py"],
            section="Estados, aplicabilidade e bloqueio",
        ),
        make_blocked(
            "dod-state:blocked-external-demo",
            "Dependência externa pendente é anotada como BLOCKED.",
            owner="Tiago / ops",
            cause="VPS credentials and contracting not available",
            next_test="re-check after human infra decision",
            evidence=["squads/extra-dod-roi/state/blockers/latest.json"],
            section="Estados, aplicabilidade e bloqueio",
        ),
        make_not_applicable(
            "dod-state:na-scope-demo",
            "Exemplo de requisito fora de escopo com decisão registrada.",
            basis="scope_decision_tiago",
            justification="Illustrative NA for multi-tenant billing (explicit out of scope §2.3).",
            date="2026-07-18",
            evidence=[
                "DOD.md §2.3 escopo excluído",
                "docs/ops/session-2026-07-18-requirement-states/",
            ],
            section="Estados, aplicabilidade e bloqueio",
        ),
        RequirementRecord(
            item_id="dod-state:field-source-unavailable",
            title="Campo indisponível na fonte → SOURCE_UNAVAILABLE",
            state=RequirementState.SOURCE_UNAVAILABLE.value,
            dod_checkbox="[ ]",
            section="Estados, aplicabilidade e bloqueio",
            field_name="valor_homologado",
            evidence=["source consulted; field absent in payload; not coerced to 0"],
            updated_at=utc_now(),
            updated_by="requirement_states",
        ),
        RequirementRecord(
            item_id="dod-state:field-not-ready",
            title="Fonte ainda não consultada → NOT_READY",
            state=RequirementState.NOT_READY.value,
            dod_checkbox="[ ]",
            section="Estados, aplicabilidade e bloqueio",
            field_name="data_abertura",
            evidence=["source not yet fetched this run"],
            updated_at=utc_now(),
            updated_by="requirement_states",
        ),
    ]
    for rec in examples:
        upsert_record(data, rec)
    save_ledger(data, ledger_path)
    return reconstruct(ledger_path=ledger_path)


def campaign_state_report(
    *,
    ledger_path: Path | str | None = None,
    dod_path: Path | str | None = None,
    blockers_path: Path | str | None = None,
) -> dict[str, Any]:
    """Thin integration surface for campaign/ROI gates (honest scope)."""
    base = reconstruct(ledger_path=ledger_path, dod_path=dod_path)
    bp = Path(blockers_path or (PROJECT_ROOT / "squads/extra-dod-roi/state/blockers/latest.json"))
    blockers: list[Any] = []
    if bp.exists():
        try:
            blockers = json.loads(bp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            blockers = []
    open_blockers = [
        b
        for b in blockers
        if isinstance(b, dict) and str(b.get("status", "")).upper() in {"BLOCKED", "PARTIAL"}
    ]
    base["campaign_integration"] = {
        "module": "scripts.ops.requirement_states",
        "blockers_path": str(bp),
        "open_blockers_visible": len(open_blockers),
        "sample_blocker_ids": [b.get("id") for b in open_blockers[:10]],
        "note": "External blockers remain visible; module does not hide them from gates",
    }
    return base


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DoD requirement state ledger")
    p.add_argument(
        "command",
        choices=["reconstruct", "seed", "gate-summary", "validate", "campaign-state"],
    )
    p.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    p.add_argument("--dod", type=Path, default=DEFAULT_DOD)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)

    if args.command == "seed":
        report = seed_canonical_examples(args.ledger)
    elif args.command == "reconstruct":
        report = reconstruct(ledger_path=args.ledger, dod_path=args.dod)
    elif args.command == "campaign-state":
        report = campaign_state_report(ledger_path=args.ledger, dod_path=args.dod)
    elif args.command == "validate":
        report = reconstruct(ledger_path=args.ledger, dod_path=args.dod)
        if not report["ok"]:
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 1
    else:  # gate-summary
        ledger = load_ledger(args.ledger)
        report = gate_counts(records_from_ledger(ledger))

    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

