"""Text extraction priority: structured → HTML → PDF text → office → OCR last.

OCR is bounded, hash-addressed, and skipped when embedded text is sufficient.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class TextExtractResult:
    text: str
    origin: str  # structured | html | pdf_embedded | office | ocr | none
    page_count: int | None = None
    ocr_used: bool = False
    content_hash: str | None = None
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin,
            "page_count": self.page_count,
            "ocr_used": self.ocr_used,
            "content_hash": self.content_hash,
            "truncated": self.truncated,
            "text_length": len(self.text or ""),
            "text_preview_hash": hashlib.sha256((self.text or "")[:500].encode()).hexdigest()
            if self.text
            else None,
        }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_from_html(html: str, *, max_chars: int = 200_000) -> TextExtractResult:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html or "")
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    trunc = len(text) > max_chars
    text = text[:max_chars]
    return TextExtractResult(
        text=text,
        origin="html",
        content_hash=hashlib.sha256(text.encode()).hexdigest() if text else None,
        truncated=trunc,
    )


def extract_from_pdf_bytes(
    data: bytes,
    *,
    max_chars: int = 300_000,
    min_embedded_chars: int = 80,
    allow_ocr: bool = False,
    ocr_max_pages: int = 5,
    ocr_cache: dict[str, str] | None = None,
) -> TextExtractResult:
    """Prefer embedded PDF text; OCR only when image-only and allowed."""
    h = _sha256_bytes(data)
    if ocr_cache is not None and h in ocr_cache:
        t = ocr_cache[h]
        return TextExtractResult(text=t, origin="ocr", ocr_used=True, content_hash=h)

    # Try pypdf / PyPDF2
    embedded = ""
    pages = 0
    try:
        from pypdf import PdfReader  # type: ignore
        import io

        reader = PdfReader(io.BytesIO(data))
        pages = len(reader.pages)
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        embedded = "\n".join(parts)
    except Exception:
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=data, filetype="pdf")
            pages = doc.page_count
            parts = [page.get_text() for page in doc]
            embedded = "\n".join(parts)
            doc.close()
        except Exception:
            embedded = ""

    embedded = embedded.strip()
    if len(embedded) >= min_embedded_chars:
        trunc = len(embedded) > max_chars
        return TextExtractResult(
            text=embedded[:max_chars],
            origin="pdf_embedded",
            page_count=pages,
            ocr_used=False,
            content_hash=h,
            truncated=trunc,
        )

    if not allow_ocr:
        return TextExtractResult(
            text=embedded[:max_chars],
            origin="pdf_embedded" if embedded else "none",
            page_count=pages,
            ocr_used=False,
            content_hash=h,
        )

    # Bounded OCR via pytesseract + pymupdf render
    ocr_text = ""
    try:
        import fitz
        import pytesseract
        from PIL import Image
        import io

        doc = fitz.open(stream=data, filetype="pdf")
        pages = doc.page_count
        chunks: list[str] = []
        for i in range(min(pages, ocr_max_pages)):
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            chunks.append(pytesseract.image_to_string(img, lang="por") or "")
        doc.close()
        ocr_text = "\n".join(chunks).strip()
        if ocr_cache is not None and ocr_text:
            ocr_cache[h] = ocr_text[:max_chars]
    except Exception:
        ocr_text = ""

    if ocr_text:
        return TextExtractResult(
            text=ocr_text[:max_chars],
            origin="ocr",
            page_count=pages,
            ocr_used=True,
            content_hash=h,
            truncated=len(ocr_text) > max_chars,
        )
    return TextExtractResult(text="", origin="none", page_count=pages, content_hash=h)


def extract_text(
    *,
    structured_fields: dict[str, Any] | None = None,
    html: str | None = None,
    raw_bytes: bytes | None = None,
    mime: str | None = None,
    filename: str | None = None,
    allow_ocr: bool = False,
    ocr_cache: dict[str, str] | None = None,
) -> TextExtractResult:
    """Unified extraction entry with priority order."""
    if structured_fields:
        parts = []
        for k, v in structured_fields.items():
            if v is not None and str(v).strip():
                parts.append(f"{k}: {v}")
        if parts:
            text = "\n".join(parts)
            return TextExtractResult(
                text=text,
                origin="structured",
                content_hash=hashlib.sha256(text.encode()).hexdigest(),
            )
    if html and html.strip():
        return extract_from_html(html)
    if raw_bytes:
        mime_l = (mime or "").lower()
        name_l = (filename or "").lower()
        if "pdf" in mime_l or name_l.endswith(".pdf") or raw_bytes[:4] == b"%PDF":
            return extract_from_pdf_bytes(raw_bytes, allow_ocr=allow_ocr, ocr_cache=ocr_cache)
        if "html" in mime_l or name_l.endswith((".html", ".htm")):
            try:
                return extract_from_html(raw_bytes.decode("utf-8", errors="replace"))
            except Exception:
                pass
        # plain text fallback
        try:
            text = raw_bytes.decode("utf-8", errors="replace")
            if text.strip():
                return TextExtractResult(
                    text=text[:300_000],
                    origin="office" if "off" in mime_l or name_l.endswith((".docx", ".odt")) else "html",
                    content_hash=_sha256_bytes(raw_bytes),
                )
        except Exception:
            pass
    return TextExtractResult(text="", origin="none")
