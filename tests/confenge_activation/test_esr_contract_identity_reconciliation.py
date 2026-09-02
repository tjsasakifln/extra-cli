"""ESR reconciliation must match evidence by official PNCP identity, end to end.

Chain under test: raw record -> normalize_record -> build_message_spine
(via build_dossier) -> strict_national_esr._primary_contract, which strips the
``cf-contract-``/``ev-contract-`` prefixes off ``fact_evidence_ids`` and joins
back to the live DB rows by ``contract_id``. If the message spine ever
degrades an identified contract's evidence id to a positional surrogate
(``cf-contract-contract-0``), this join silently falls through to
``contracts[0]`` instead of the contract the spine actually cited.
"""

from __future__ import annotations

from datetime import date, timedelta

from scripts.confenge_account_intelligence.pipeline import build_dossier
from scripts.confenge_activation.strict_national_esr import _primary_contract

TODAY = date.today()
OBJECT = (
    "Execução de obra de pavimentação asfáltica em CBUQ, drenagem pluvial e "
    "sinalização viária nas vias urbanas do município"
)


def _raw_bag() -> dict[str, object]:
    return {
        "cnpj14": "02810894000100",
        "razao_social": "ACME CONSTRUTORA LTDA",
        "contracts": [
            {
                "numero_controle_pncp": "07854402000186-1-000123/2024",
                "object": OBJECT,
                "orgao": "DNIT",
                "uf": "SC",
                "value_brl": 4_800_000,
                "start_date": (TODAY - timedelta(days=900)).isoformat(),
                "end_date": (TODAY - timedelta(days=200)).isoformat(),
            }
        ],
    }


def _live_db_rows(official_id: str) -> list[dict[str, object]]:
    """Shape returned by the ESR live-DB contract lookup (contract_id keyed)."""
    return [
        {
            "contract_id": "99999999",  # unrelated decoy row, must NOT be chosen
            "orgao_nome": "OUTRO ORGAO",
            "objeto_contrato": "objeto nao relacionado",
            "uf": "RJ",
            "valor_total": 1,
            "data_publicacao": None,
            "data_inicio": None,
            "data_fim": None,
        },
        {
            "contract_id": official_id,
            "orgao_nome": "DNIT",
            "objeto_contrato": OBJECT,
            "uf": "SC",
            "valor_total": 4_800_000,
            "data_publicacao": None,
            "data_inicio": None,
            "data_fim": None,
        },
    ]


def test_esr_reconciles_the_message_spine_evidence_to_the_official_contract_row() -> None:
    official_id = "07854402000186-1-000123/2024"
    dossier = build_dossier(_raw_bag())

    evidence_ids = list((dossier.get("message_spine") or {}).get("fact_evidence_ids") or [])
    assert evidence_ids == [f"cf-contract-{official_id}"], (
        "precondition: the spine must cite the official id, not a positional surrogate "
        f"— got {evidence_ids}"
    )

    chosen = _primary_contract(dossier, _live_db_rows(official_id))

    assert chosen["contract_id"] == official_id
    assert chosen["agency"] == "DNIT"
