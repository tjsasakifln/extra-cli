#!/usr/bin/env python3
"""DEPRECATED shim — use ``python -m scripts.pseo.verify_web_cfg_compat``.

``--apply`` and ``--build`` were permanently removed. This module only
re-exports the read-only web-cfg consumer compatibility verifier.

Writes are limited to ``--out`` notes under extra-cli artifacts/cwd.
The web-cfg tree is never mutated.
"""

from __future__ import annotations

import warnings

from scripts.pseo.verify_web_cfg_compat import (  # noqa: F401
    FORBIDDEN_WRITE_FLAGS,
    main,
    page_changelog,
)


def _warn_deprecated() -> None:
    warnings.warn(
        "scripts.pseo.release_snapshot is deprecated; "
        "use scripts.pseo.verify_web_cfg_compat (read-only). "
        "--apply/--build were removed.",
        DeprecationWarning,
        stacklevel=2,
    )


if __name__ == "__main__":
    _warn_deprecated()
    raise SystemExit(main())
