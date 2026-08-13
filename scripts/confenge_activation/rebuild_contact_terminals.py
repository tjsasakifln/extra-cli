"""Rebuild honest contact terminals from process harvest + web enrich evidence.

Never stamps CONTACT_EXHAUSTED for process-only sources. Merges:
  - process harvest accounts / terminals
  - enrich-batch confenge-contact-candidates-v1.jsonl adapters
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.confenge_contact_resolution.discovery_state import (
    CONTACT_EXHAUSTED,
    CONTACT_READY,
    CONTACT_RETRY_PENDING,
    DEFAULT_SOURCE_LADDER,
    classify_contact_terminal,
    measure_terminal_coverage,
    sources_cover_required_ladder,
)

ADAPTER_TO_SOURCE = {
    "registry": "official_registry",
    "site": "official_site",
    "public_docs": "public_docs_datalake",
    "contact_page": "company_public_pages",
    "web_search": "company_public_pages",
    "site_crawl": "official_site",
    "datalake": "public_docs_datalake",
}


def _root8(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) >= 14:
        return digits[:8]
    return digits[:8] if len(digits) >= 8 else digits


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                out.append(row)
    return out


def _sources_from_enrich_row(row: dict[str, Any]) -> list[str]:
    """Map enrich adapters to ladder steps only when the adapter actually ran.

    resolver.py records:
      adapters_used = collect() returned observations
      adapters_skipped = f"{name}:empty" | f"{name}:error:..." after collect() ran

    Bare names without :empty/:error are NOT counted (never prove a run).
    """
    sources: list[str] = []
    seen: set[str] = set()

    def _add(adapter_token: str, *, require_status: bool) -> None:
        raw = str(adapter_token or "").strip()
        if not raw:
            return
        parts = raw.split(":")
        name = parts[0]
        status = parts[1] if len(parts) > 1 else ""
        if require_status and status not in {"empty", "error", "timeout", "blocked"}:
            # Unqualified skip tokens do not prove the adapter ran.
            return
        if require_status and status == "error" and len(parts) < 2:
            return
        src = ADAPTER_TO_SOURCE.get(name, name)
        if src and src not in seen:
            seen.add(src)
            sources.append(src)

    for a in row.get("adapters_used") or []:
        # Used always means collect() returned data — status implicit "hit"
        name = str(a).split(":")[0]
        src = ADAPTER_TO_SOURCE.get(name, name)
        if src and src not in seen:
            seen.add(src)
            sources.append(src)
    for a in row.get("adapters_skipped") or []:
        _add(str(a), require_status=True)
    return sources


def rebuild(
    *,
    process_dir: Path,
    enrich_dir: Path | None,
    confirmed_roots: list[str] | None = None,
    out_path: Path | None = None,
) -> dict[str, Any]:
    process_dir = Path(process_dir)
    accounts_dir = process_dir / "accounts"
    prior = _load_jsonl(process_dir / "contact-discovery-terminals.jsonl")
    prior_by_root = {_root8(r.get("cnpj_raiz")): r for r in prior if _root8(r.get("cnpj_raiz"))}

    enrich_by_root: dict[str, dict[str, Any]] = {}
    if enrich_dir:
        for name in (
            "confenge-contact-candidates-v1.jsonl",
            "contacts_review_required.jsonl",
        ):
            for row in _load_jsonl(Path(enrich_dir) / name):
                root = _root8(row.get("cnpj14") or row.get("account_key") or row.get("cnpj_raiz"))
                if not root:
                    continue
                # Prefer richer adapter evidence (do not let a sparse later file wipe sources)
                prev = enrich_by_root.get(root)
                if prev is None:
                    enrich_by_root[root] = row
                    continue
                prev_n = len(prev.get("adapters_used") or []) + len(prev.get("adapters_skipped") or [])
                new_n = len(row.get("adapters_used") or []) + len(row.get("adapters_skipped") or [])
                if new_n >= prev_n:
                    enrich_by_root[root] = row

    # Emails from process candidates
    process_emails: dict[str, int] = {}
    for row in _load_jsonl(process_dir / "contact-candidates.jsonl"):
        root = _root8(row.get("cnpj_raiz"))
        if root and row.get("email") and not row.get("pattern_guessed"):
            process_emails[root] = process_emails.get(root, 0) + 1

    if confirmed_roots is None:
        roots = set(prior_by_root) | set(enrich_by_root) | set(process_emails)
        if accounts_dir.is_dir():
            for p in accounts_dir.glob("*.json"):
                roots.add(_root8(p.stem))
        confirmed_roots = sorted(r for r in roots if len(r) == 8)

    terminals: list[dict[str, Any]] = []
    for root in confirmed_roots:
        sources: list[str] = []
        # Always record process path if prior or account exists
        if root in prior_by_root or (accounts_dir / f"{root}.json").is_file() or root in process_emails:
            sources.extend(["process_administrative_docs", "pncp_annexes"])
        er = enrich_by_root.get(root)
        if er:
            sources.extend(_sources_from_enrich_row(er))
        # de-dupe preserve order
        seen: set[str] = set()
        deduped: list[str] = []
        for s in sources:
            if s and s not in seen:
                seen.add(s)
                deduped.append(s)
        sources = deduped

        n_email = process_emails.get(root, 0)
        if er:
            cands = er.get("candidates") or er.get("contacts") or []
            for c in cands:
                if isinstance(c, dict) and c.get("email"):
                    n_email += 1
            if er.get("commercial_contact_state") == "CONTACT_READY":
                n_email = max(n_email, 1)

        full = sources_cover_required_ladder(sources)
        # send_ready proxy only from process CONTACT_READY prior or enrich READY
        esr = 0
        if prior_by_root.get(root, {}).get("terminal_state") == CONTACT_READY:
            esr = 1
        if er and er.get("commercial_contact_state") == "CONTACT_READY":
            esr = 1

        st = classify_contact_terminal(
            cnpj_raiz=root,
            sources_attempted=sources,
            network_discovery=True,
            ladder_complete=full,
            email_candidates=n_email,
            email_send_ready=esr,
            attempt_count=max(1, len(sources)),
            meta={
                "rebuild": "honest_merge_process_enrich",
                "full_ladder": full,
                "enrich_state": (er or {}).get("commercial_contact_state"),
            },
        )
        terminals.append(st.as_dict())

    out_path = out_path or (process_dir / "contact-discovery-terminals.jsonl")
    with out_path.open("w", encoding="utf-8") as fh:
        for t in terminals:
            fh.write(json.dumps(t, ensure_ascii=False) + "\n")

    cov = measure_terminal_coverage(terminals, population_total=len(confirmed_roots))
    counts = Counter(t["terminal_state"] for t in terminals)
    full_n = sum(1 for t in terminals if t.get("ladder_complete"))
    # READY/FOUND may short-circuit before full ladder; EXHAUSTED must be full.
    exhausted_incomplete = sum(
        1
        for t in terminals
        if t.get("terminal_state") == CONTACT_EXHAUSTED and not t.get("ladder_complete")
    )
    report = {
        "schema": "confenge.rebuild_contact_terminals.v1",
        "roots": len(confirmed_roots),
        "terminal_counts": dict(counts),
        "full_ladder_complete_roots": full_n,
        "exhausted_incomplete": exhausted_incomplete,
        "full_source_ladder_complete": (
            counts.get(CONTACT_RETRY_PENDING, 0) == 0 and exhausted_incomplete == 0
        ),
        "coverage": cov,
        "out_path": str(out_path),
        "DEFAULT_SOURCE_LADDER": list(DEFAULT_SOURCE_LADDER),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--process-dir",
        type=Path,
        default=Path("artifacts/confenge/process-first-national-confirmed"),
    )
    p.add_argument(
        "--enrich-dir",
        type=Path,
        default=Path("artifacts/confenge/contact-enrichment/continuous-national-20260810"),
    )
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)
    report = rebuild(
        process_dir=args.process_dir,
        enrich_dir=args.enrich_dir if args.enrich_dir.is_dir() else None,
        out_path=args.out,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
