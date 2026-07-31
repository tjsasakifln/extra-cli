"""CLI marker entry for workflow capabilities (audit argv only).

Real execution is in-process via JobRunner._execute_workflow.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    print(
        "WORKFLOW_MARKER_ONLY: execução real ocorre no JobRunner do Command Center.",
        flush=True,
    )
    if args:
        print("workflow_id=", args[0], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
