"""Offline, bounded PDF text fallback for the approved news-producer bundle.

This module imports no optional dependency until its isolated subprocess runs.
The exact pure-Python wheel is verified before zipimport; no installation or
network call is made on the production host.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PYPDF_WHEEL = "scripts/public_exports/vendor/pypdf-6.21.4-py3-none-any.whl"
PYPDF_SHA256 = "33e4fb41ca352810eb4e9838aa0d82d6888a5f8bf682f43e99cce5faa666255c"
MAX_WHEEL_BYTES = 512 * 1024
MAX_PDF_BYTES = 2 * 1024 * 1024
MAX_PAGES = 20
MAX_OUTPUT_BYTES = 256 * 1024


def verified_wheel(root: Path | None = None) -> Path:
    root = root or Path(__file__).resolve().parents[2]
    wheel = root / PYPDF_WHEEL
    if (not wheel.is_file() or wheel.is_symlink() or wheel.stat().st_size > MAX_WHEEL_BYTES
            or hashlib.sha256(wheel.read_bytes()).hexdigest() != PYPDF_SHA256):
        raise ValueError("pdf_dependency_digest_mismatch")
    return wheel


def extract(source: Path, destination: Path) -> dict[str, object]:
    if (not source.is_file() or source.is_symlink() or source.stat().st_size > MAX_PDF_BYTES
            or destination.exists() or destination.is_symlink()):
        raise ValueError("invalid_pdf_paths")
    wheel = verified_wheel()
    sys.path.insert(0, str(wheel))
    # This process is started with -S; optional site packages cannot satisfy the
    # import. The verified wheel is deliberately the first import location.
    from pypdf import PdfReader  # type: ignore[import-not-found]

    reader = PdfReader(str(source), strict=False)
    if reader.is_encrypted:
        raise ValueError("encrypted_document")
    pages = len(reader.pages)
    if not 1 <= pages <= MAX_PAGES:
        raise ValueError("document_page_limit_or_invalid")
    output = []
    pages_without_text = []
    size = 0
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if len(" ".join(text.split())) < 40:
            pages_without_text.append(number)
        size += len(text.encode("utf-8")) + 1
        if size > MAX_OUTPUT_BYTES:
            raise ValueError("document_text_out_of_bounds")
        output.append(text)
    with destination.open("x", encoding="utf-8") as handle:
        handle.write("\n".join(output))
    destination.chmod(0o600)
    return {"pages": pages, "pages_without_text": pages_without_text}


def main() -> int:
    if len(sys.argv) != 3:
        print('{"error":"invalid_pdf_arguments"}')
        return 1
    try:
        result = extract(Path(sys.argv[1]), Path(sys.argv[2]))
    except Exception:  # noqa: BLE001 - never echo PDF text, document paths or parser internals
        print('{"error":"pdf_fallback_unavailable"}')
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
