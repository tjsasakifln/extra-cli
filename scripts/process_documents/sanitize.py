"""PII detection and sanitization for public document corpus (text-level).

Does not commit raw documents. Produces redacted text extracts and reports.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from scripts.process_documents.storage import write_json

CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
PHONE_RE = re.compile(r"\b(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?(?:9\d{4}|\d{4})-?\d{4}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
RG_RE = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-?[0-9Xx]\b")
BANK_RE = re.compile(r"\b(?:agencia|ag[eê]ncia|conta)\s*[:#]?\s*\d+", re.I)


@dataclass
class SanitizationFinding:
    kind: str
    count: int
    samples_redacted: list[str] = field(default_factory=list)


def _redact_pattern(text: str, pattern: re.Pattern[str], token: str) -> tuple[str, int, list[str]]:
    samples: list[str] = []
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        if len(samples) < 3:
            samples.append(token)
        digest = hashlib.sha256(m.group(0).encode()).hexdigest()[:8]
        return f"[{token}:{digest}]"

    return pattern.sub(repl, text), count, samples


def sanitize_text(text: str) -> tuple[str, list[SanitizationFinding]]:
    findings: list[SanitizationFinding] = []
    out = text
    for kind, pattern in (
        ("cpf", CPF_RE),
        ("email", EMAIL_RE),
        ("phone", PHONE_RE),
        ("rg", RG_RE),
        ("bank", BANK_RE),
    ):
        out, count, samples = _redact_pattern(out, pattern, kind.upper())
        if count:
            findings.append(SanitizationFinding(kind=kind, count=count, samples_redacted=samples))
    return out, findings


def sanitize_corpus_dir(corpus_dir: Path, *, output_dir: Path | None = None) -> dict[str, Any]:
    corpus_dir = Path(corpus_dir)
    out = Path(output_dir or (corpus_dir / "sanitized"))
    out.mkdir(parents=True, exist_ok=True)
    report_findings: list[dict[str, Any]] = []
    files = 0
    for path in corpus_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".txt", ".md", ".html", ".csv", ".json"}:
            continue
        if "sanitized" in path.parts:
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        cleaned, findings = sanitize_text(raw)
        rel = path.relative_to(corpus_dir)
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(cleaned, encoding="utf-8")
        files += 1
        if findings:
            report_findings.append(
                {
                    "file": str(rel),
                    "findings": [asdict(f) for f in findings],
                }
            )
    report = {
        "files_processed": files,
        "files_with_findings": len(report_findings),
        "findings": report_findings,
        "policy": "deterministic_token_redaction",
        "raw_separated": True,
    }
    write_json(out / "sanitization-report.json", report)
    return report
