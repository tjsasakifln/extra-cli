"""Allow `python3 -m scripts.budget_audit.gate` via package path.

Actually gate.py has main; this re-exports for module execution.
Prefer: python3 -m scripts.budget_audit.gate
"""

from scripts.budget_audit.gate import main

if __name__ == "__main__":
    raise SystemExit(main())
