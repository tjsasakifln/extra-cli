"""Extração de texto de PDFs baixados (PyMuPDF/fitz)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PdfExtract:
    ok: bool
    text: str = ""
    pages_read: int = 0
    pages_total: int = 0
    method: str = "pymupdf"
    confidence: float = 0.0
    error: str = ""
    is_likely_scanned: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "pages_read": self.pages_read,
            "pages_total": self.pages_total,
            "method": self.method,
            "confidence": self.confidence,
            "error": self.error,
            "is_likely_scanned": self.is_likely_scanned,
            "text_chars": len(self.text),
        }


def extract_pdf_text(
    data: bytes,
    *,
    max_pages: int = 25,
    max_chars: int = 80_000,
) -> PdfExtract:
    """Extract text from PDF bytes. OCR not applied — scanned PDFs flagged low confidence."""
    if not data:
        return PdfExtract(ok=False, error="empty_bytes")
    if data[:4] != b"%PDF" and b"%PDF" not in data[:1024]:
        # not a PDF — try as plain/html text
        try:
            t = data.decode("utf-8", errors="replace")
        except Exception:
            t = data.decode("latin-1", errors="replace")
        return PdfExtract(
            ok=bool(t.strip()),
            text=t[:max_chars],
            pages_read=1,
            pages_total=1,
            method="plaintext",
            confidence=0.4 if t.strip() else 0.0,
            error="" if t.strip() else "not_pdf_or_text",
        )

    try:
        import fitz  # PyMuPDF
    except ImportError:
        return PdfExtract(ok=False, error="pymupdf_unavailable")

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        return PdfExtract(ok=False, error=f"open_failed:{exc}")

    try:
        total = doc.page_count
        parts: list[str] = []
        n = min(total, max_pages)
        for i in range(n):
            page = doc.load_page(i)
            parts.append(page.get_text("text") or "")
            if sum(len(p) for p in parts) >= max_chars:
                break
        text = "\n".join(parts)[:max_chars]
        chars_per_page = len(text) / max(n, 1)
        scanned = chars_per_page < 40 and total > 0
        conf = 0.85 if not scanned and len(text) > 200 else (0.35 if scanned else 0.55)
        return PdfExtract(
            ok=bool(text.strip()) or total > 0,
            text=text,
            pages_read=n,
            pages_total=total,
            method="pymupdf",
            confidence=conf,
            is_likely_scanned=scanned,
            error="likely_scanned_no_ocr" if scanned and len(text) < 100 else "",
        )
    except Exception as exc:  # noqa: BLE001
        return PdfExtract(ok=False, error=f"extract_failed:{exc}")
    finally:
        doc.close()


def is_edital_like_title(title: str) -> bool:
    t = (title or "").lower()
    keys = (
        "edital",
        "termo de referencia",
        "termo de referência",
        "tr.pdf",
        "tr ",
        "projeto basico",
        "projeto básico",
        "projeto executivo",
        "memorial",
        "planilha",
        "orcamento",
        "orçamento",
        "cronograma",
        "minuta",
        "anexo",
        "etp",
        "estudo tecnico",
        "estudo técnico",
        "bdi",
        "composicao",
        "composição",
    )
    return any(k in t for k in keys)


def is_pdf_bytes(data: bytes) -> bool:
    return bool(data) and (data[:4] == b"%PDF" or b"%PDF" in data[:1024])
