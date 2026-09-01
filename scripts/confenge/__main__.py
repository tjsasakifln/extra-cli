"""python -m scripts.confenge <subcommand>"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print(
            "Usage:\n"
            "  python -m scripts.confenge human_review [--sample PATH]\n"
            "  python -m scripts.confenge.human_review\n"
            "  python -m scripts.confenge claim_safety_audit [--dry-run | --apply] [--feed-dir PATH]\n"
            "  python -m scripts.confenge claim_safety_audit rollback\n"
        )
        return 0
    cmd = argv[0]
    rest = argv[1:]
    if cmd in {"human_review", "review"}:
        from scripts.confenge.human_review.cli import main as hr_main

        return hr_main(rest)
    if cmd in {"claim_safety_audit", "claim-safety-audit"}:
        from scripts.confenge.claim_safety_audit.cli import main as cs_main

        return cs_main(rest)
    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
