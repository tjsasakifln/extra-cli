"""public-read-bofu-evidence/1.0 producer.

Public entry:
  python3 -m scripts.bofu_evidence --out DIR --as-of 2026-08-19T00:00:00Z
"""

from __future__ import annotations

from scripts.bofu_evidence.gates import evaluate_gates
from scripts.bofu_evidence.hashutil import hash_without_content_hash, stamp_hash
from scripts.bofu_evidence.models import FAMILIES, SCHEMA
from scripts.bofu_evidence.producer import build_family_pack, build_packs, write_packs

__all__ = [
    "FAMILIES",
    "SCHEMA",
    "build_family_pack",
    "build_packs",
    "evaluate_gates",
    "hash_without_content_hash",
    "stamp_hash",
    "write_packs",
]
