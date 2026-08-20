"""Shared helpers for bid_readiness_public tests. Drive shipped producer only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook

from scripts.bid_readiness_public.compose import produce

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CLOCK = "2026-08-20T12:00:00+00:00"


def clean_workbook(path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Orcamento Analitico"
    ws.append(
        ["Item", "Código", "Descrição", "Unidade", "Quantidade", "Custo Unit", "BDI %", "Preço Unit", "Preço Total"]
    )
    ws.append([1, "FIC-001", "Pavimentacao asfaltica", "m²", 10, 80, 25, 100, 1000])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def incomplete_documents(dest: Path) -> Path:
    """Package missing the technical atestado — coverage must HOLD."""
    dest.mkdir(parents=True, exist_ok=True)
    src = FIXTURES / "documents" / "01_contrato_social.txt"
    (dest / src.name).write_bytes(src.read_bytes())
    return dest


def produce_happy(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    if "planilha" not in overrides:
        planilha = tmp_path / "planilha.xlsx"
        clean_workbook(planilha)
        overrides["planilha"] = planilha
    kwargs = {
        "edital": FIXTURES / "edital.txt",
        "documents": FIXTURES / "documents",
        "acervo": FIXTURES / "acervo.json",
        "requirements": FIXTURES / "requirements.json",
        "work_dir": tmp_path / "work",
        "clock": CLOCK,
        "entity": {
            "cnpj": "12345678000199",
            "razao_social": "EMPRESA FICTICIA LTDA",
            "signatory": "PESSOA FICTICIA",
        },
    }
    kwargs.update(overrides)
    return produce(**kwargs)
