#!/usr/bin/env python3
"""Parse DOD.md into a conservative requirements matrix (worker)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def parse_dod(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    items: list[dict[str, Any]] = []
    section = ""
    section_re = re.compile(r"^(#{1,4})\s+(.*)")
    check_re = re.compile(r"^(\s*)[-*]\s+\[([ xX])\]\s+(.*)$")

    for i, line in enumerate(lines, start=1):
        m = section_re.match(line)
        if m:
            section = m.group(2).strip()
            continue
        m = check_re.match(line)
        if not m:
            continue
        checked = m.group(2).lower() == "x"
        body = m.group(3).strip()
        # heuristic classification
        classification = "DONE" if checked else "NOT_READY"
        low = body.lower()
        if not checked:
            if "blocked" in low or "BLOCKED" in body:
                classification = "BLOCKED"
            elif "partial" in low or "PARTIAL" in body:
                classification = "PARTIAL"
            elif "not applicable" in low or "N/A" in body:
                classification = "NOT_APPLICABLE"
        items.append(
            {
                "id": f"dod-L{i}",
                "line": i,
                "section": section,
                "text": body[:500],
                "checkbox": checked,
                "classification": classification,
                "evidence_mentioned": bool(
                    re.search(r"evid[eê]ncia|evidence|commit|pytest|make |run ", body, re.I)
                ),
            }
        )

    # supersession / seals from full text
    superseded = []
    if re.search(r"LOCAL_RESILIENCE_READY.*SUPERSEDED|SUPERSEDED.*LOCAL_RESILIENCE", text, re.I | re.S):
        superseded.append(
            {
                "claim": "LOCAL_RESILIENCE_READY",
                "current": "NOT_READY",
                "source": "DOD.md §44",
            }
        )
    if re.search(r"NOT_READY.*PRE_VPS_FINAL_READY|PRE_VPS_FINAL_READY.*NOT_READY", text, re.I):
        superseded.append(
            {
                "claim": "PRE_VPS_FINAL_READY",
                "current": "NOT_READY",
                "source": "DOD.md residual / PR truth gate",
            }
        )

    allowed = []
    forbidden = [
        "VPS provisionada/operacional sem evidência live",
        "Cobertura operacional 95% sem medição estrita",
        "Freshness live garantida por fixtures",
        "LOCAL_RESILIENCE_READY (superseded → NOT_READY)",
        "PRE_VPS_FINAL_READY sem live canary + PG evidence",
        "Stories Done sem QA/PO independentes",
    ]
    if "Mecânica de resiliência local" in text or "reproduzível sem internet" in text:
        allowed.append("Mecânica de resiliência local das fontes prioritárias é reproduzível offline")
    if "0/1.093" in text or "0/1.093 (0%)" in text:
        allowed.append("Cobertura operacional estrita reportada honestamente como 0/1.093 quando evidenciado")

    done = sum(1 for x in items if x["classification"] == "DONE")
    open_ = sum(1 for x in items if x["classification"] != "DONE")

    return {
        "version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dod_path": str(path),
        "dod_sha256": sha256_file(path),
        "item_count": len(items),
        "done_count": done,
        "open_count": open_,
        "items": items,
        "superseded_claims": superseded,
        "allowed_claims": allowed,
        "forbidden_claims": forbidden,
        "veto": {
            "restore_local_resilience_ready": False,
            "reason": "Adversarial truth gate destroyed LOCAL_RESILIENCE_READY; remains NOT_READY until new proof",
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dod", default="DOD.md")
    p.add_argument("--write", action="store_true")
    p.add_argument("-o", "--output", default=None)
    p.add_argument("--summary-only", action="store_true")
    args = p.parse_args(argv)

    path = Path(args.dod)
    if not path.is_file():
        # try repo root detection
        for parent in [Path.cwd(), *Path.cwd().parents]:
            cand = parent / "DOD.md"
            if cand.is_file():
                path = cand
                break
    if not path.is_file():
        print(json.dumps({"error": "DOD.md not found"}), file=sys.stderr)
        return 2

    matrix = parse_dod(path)
    if args.summary_only:
        out = {
            k: matrix[k]
            for k in [
                "version",
                "generated_at",
                "dod_sha256",
                "item_count",
                "done_count",
                "open_count",
                "superseded_claims",
                "allowed_claims",
                "forbidden_claims",
                "veto",
            ]
        }
        # include section tallies
        from collections import Counter

        c = Counter(i["section"][:80] for i in matrix["items"] if not i["checkbox"])
        out["top_open_sections"] = c.most_common(15)
        text = json.dumps(out, indent=2, ensure_ascii=False)
    else:
        text = json.dumps(matrix, indent=2, ensure_ascii=False)

    if args.write or args.output:
        outp = Path(args.output) if args.output else Path("squads/extra-dod-roi/state/requirements") / "latest-matrix.json"
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {outp}", file=sys.stderr)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
