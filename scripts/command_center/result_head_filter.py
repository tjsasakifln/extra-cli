#!/usr/bin/env python3
"""Git clean/smudge filter so result.json head_sha matches HEAD on checkout."""
from __future__ import annotations

import re
import subprocess
import sys

PLACEHOLDER = "__GIT_HEAD__"
FIELD = re.compile(r'("head_sha"\s*:\s*")([^"]*)(")')


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "smudge"
    data = sys.stdin.read()
    if mode == "clean":
        data = FIELD.sub(rf"\1{PLACEHOLDER}\3", data)
        sys.stdout.write(data)
        return
    # smudge
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],  # noqa: S607 — git resolved from PATH (dev/CI env)
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        head = PLACEHOLDER
    if PLACEHOLDER in data:
        data = data.replace(PLACEHOLDER, head)
    else:
        data = FIELD.sub(rf"\1{head}\3", data)
    sys.stdout.write(data)


if __name__ == "__main__":
    main()
