"""Deliverable renderers for Command Center (PDF / XLSX / HTML).

Business rules stay in CLI modules; this layer only formats + packages outputs.
"""

from scripts.command_center.deliverables.excel_render import (
    neutralize_formula_injection,
    write_workbook,
)
from scripts.command_center.deliverables.pdf_render import write_executive_pdf
from scripts.command_center.deliverables.profiles import OutputProfile, profile_supports

__all__ = [
    "OutputProfile",
    "neutralize_formula_injection",
    "profile_supports",
    "write_executive_pdf",
    "write_workbook",
]
