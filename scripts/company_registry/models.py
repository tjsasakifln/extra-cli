"""Typed models and status machines for the official company registry."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ReleaseStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"
    VALIDATING = "VALIDATING"
    LOADING = "LOADING"
    VALIDATING_LOAD = "VALIDATING_LOAD"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"
    ROLLED_BACK = "ROLLED_BACK"


class OfficialMatchStatus(str, Enum):
    MATCHED = "MATCHED"
    NOT_FOUND_IN_OFFICIAL_RELEASE = "NOT_FOUND_IN_OFFICIAL_RELEASE"
    INVALID_CNPJ = "INVALID_CNPJ"
    MISSING_CNPJ = "MISSING_CNPJ"
    AMBIGUOUS_SOURCE_RECORD = "AMBIGUOUS_SOURCE_RECORD"
    OFFICIAL_REGISTRY_UNAVAILABLE = "OFFICIAL_REGISTRY_UNAVAILABLE"


MATCH_STATUSES = tuple(s.value for s in OfficialMatchStatus)

# Registration status policy for commercial promotion
SITUACAO_CODES = {
    "01": "NULA",
    "02": "ATIVA",
    "03": "SUSPENSA",
    "04": "INAPTA",
    "08": "BAIXADA",
}

# Situações that must not be silently promoted to Top 20
SITUACAO_BLOCK_PROMOTION = frozenset(
    {"BAIXADA", "INAPTA", "SUSPENSA", "NULA", "INATIVA", "01", "03", "04", "08"}
)


@dataclass
class OfficialCompanyRecord:
    cnpj: str
    official_match_status: str
    official_authority: str | None = "RECEITA_FEDERAL"
    official_release_id: str | None = None
    legal_name: str | None = None
    trade_name: str | None = None
    registration_status: str | None = None
    registration_status_date: str | None = None
    registration_status_reason: str | None = None
    primary_cnae: str | None = None
    secondary_cnaes: list[str] = field(default_factory=list)
    legal_nature: str | None = None
    company_size: str | None = None
    capital: float | None = None
    headquarters_or_branch: str | None = None
    city: str | None = None
    state: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    simples: bool | None = None
    mei: bool | None = None
    cnpj_root: str | None = None
    fetched_from_local_registry_at: str | None = None
    source_provenance: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_commercially_usable(self) -> bool:
        if self.official_match_status != OfficialMatchStatus.MATCHED.value:
            return False
        if not self.registration_status or not self.primary_cnae:
            return False
        sit = str(self.registration_status).upper()
        if sit in SITUACAO_BLOCK_PROMOTION:
            return False
        return True


@dataclass
class FileManifestEntry:
    file_name: str
    url: str | None = None
    content_length: int | None = None
    sha256: str | None = None
    compression_type: str | None = None
    local_path: str | None = None
    downloaded: bool = False
    kind: str | None = None  # empresas | estabelecimentos | socios | domain | ...


def empty_release_manifest(
    release_id: str,
    *,
    source_authority: str = "RECEITA_FEDERAL",
    code_commit: str | None = None,
) -> dict[str, Any]:
    return {
        "release_id": release_id,
        "source_authority": source_authority,
        "source_urls": [],
        "discovered_at": None,
        "published_reference_date": None,
        "download_started_at": None,
        "download_finished_at": None,
        "files_expected": [],
        "files_downloaded": [],
        "file_names": [],
        "content_lengths": {},
        "sha256": {},
        "compression_type": {},
        "schema_version": "company-registry-v1",
        "row_counts": {},
        "reject_counts": {},
        "duplicate_counts": {},
        "load_started_at": None,
        "load_finished_at": None,
        "status": ReleaseStatus.DISCOVERED.value,
        "errors": [],
        "warnings": [],
        "database_snapshot_id": None,
        "code_commit": code_commit,
        "mode": None,  # bulk | selective
        "ingestion_mode": None,
    }
