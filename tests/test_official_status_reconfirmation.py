from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.official_status_reconfirmation import reconfirm_shortlist

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from collect_report_data import (  # noqa: E402
    PCP_MAX_PAGES,
    _OfficialStatusFetcher,
    _preview_unexecuted_reconfirmation,
)

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def _candidate(reference: str, source: str = "PNCP") -> dict:
    return {
        "numero_controle": reference,
        "fonte": source,
        "recomendacao": "PARTICIPAR",
        "justificativa": "score alto",
    }


def test_every_candidate_has_sao_paulo_timestamp_and_official_evidence() -> None:
    editais = [_candidate("open-1"), _candidate("open-2", "PCP")]

    def fetch(edital: dict) -> dict:
        return {
            "status_native": "Divulgada no portal oficial",
            "deadline_at": "2026-08-20T18:00:00-03:00",
            "evidence_url": f"https://official.example/{edital['numero_controle']}",
        }

    summary = reconfirm_shortlist(editais, fetch, now=NOW)

    assert summary["decisions"] == {"GO": 2, "REVIEW": 0, "NO_GO": 0}
    assert summary["all_candidates_reconfirmed"] is True
    assert all(edital["shortlist_eligible"] for edital in editais)
    for edital in editais:
        evidence = edital["official_reconfirmation"]
        assert evidence["timezone"] == "America/Sao_Paulo"
        assert evidence["checked_at"].endswith("-03:00")
        assert evidence["deadline_at"].endswith("-03:00")
        assert evidence["evidence_url"].startswith("https://official.example/")


def test_terminal_expired_and_ambiguous_statuses_never_enter_shortlist() -> None:
    editais = [_candidate("terminal"), _candidate("expired"), _candidate("ambiguous")]
    observations = {
        "terminal": {
            "status_native": "Processo revogado",
            "deadline_at": "2026-08-20T18:00:00-03:00",
            "evidence_url": "https://official.example/terminal",
        },
        "expired": {
            "status_native": "Recebendo propostas",
            "deadline_at": "2026-08-12T18:00:00-03:00",
            "evidence_url": "https://official.example/expired",
        },
        "ambiguous": {
            "status_native": "Em análise",
            "deadline_at": "2026-08-20T18:00:00-03:00",
            "evidence_url": "https://official.example/ambiguous",
        },
    }

    summary = reconfirm_shortlist(editais, lambda edital: observations[edital["numero_controle"]], now=NOW)

    assert summary["decisions"] == {"GO": 0, "REVIEW": 1, "NO_GO": 2}
    assert summary["shortlist_blocked"] is True
    assert all(edital["recomendacao"] == "NÃO RECOMENDADO" for edital in editais)
    assert editais[0]["status_edital"] == "ENCERRADO"
    assert editais[1]["status_edital"] == "ENCERRADO"
    assert editais[2]["official_reconfirmation"]["decision"] == "REVIEW"
    assert all(edital["official_reconfirmation"]["next_action"] for edital in editais)


def test_terminal_status_without_deadline_is_still_no_go() -> None:
    editais = [_candidate("cancelled-without-deadline")]

    summary = reconfirm_shortlist(
        editais,
        lambda edital: {
            "status_native": "Cancelada",
            "deadline_at": None,
            "evidence_url": f"https://official.example/{edital['numero_controle']}",
        },
        now=NOW,
    )

    assert summary["decisions"] == {"GO": 0, "REVIEW": 0, "NO_GO": 1}
    assert editais[0]["status_edital"] == "ENCERRADO"


def test_missing_reconfirmation_blocks_and_one_source_failure_preserves_other_go() -> None:
    missing = [_candidate("offline")]
    missing_summary = reconfirm_shortlist(missing, None, now=NOW)
    assert missing_summary["shortlist_blocked"] is True
    assert missing[0]["official_reconfirmation"]["blocker"]

    editais = [_candidate("pncp-ok"), _candidate("pcp-failed", "PCP")]

    def fetch(edital: dict) -> dict:
        if edital["fonte"] == "PCP":
            raise TimeoutError("source timeout")
        return {
            "status_native": "Aberta para recebimento de propostas",
            "deadline_at": "2026-08-21T18:00:00Z",
            "evidence_url": "https://pncp.gov.br/app/editais/evidence",
        }

    summary = reconfirm_shortlist(editais, fetch, now=NOW)

    assert summary["decisions"] == {"GO": 1, "REVIEW": 0, "NO_GO": 1}
    assert editais[0]["shortlist_eligible"] is True
    assert editais[1]["shortlist_eligible"] is False
    assert editais[1]["official_reconfirmation"]["next_action"]
    assert summary["source_failures"] == [
        {
            "source": "PCP",
            "reference": "pcp-failed",
            "blocker": "Fonte oficial PCP indisponível na reconfirmação: TimeoutError.",
        }
    ]


def test_source_fetcher_re_reads_pncp_structural_endpoint_and_all_pcp_pages() -> None:
    class FakeApi:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict | None]] = []

        def get(self, url: str, params: dict | None = None, label: str = "") -> tuple[dict, str]:
            self.calls.append((url, params))
            if "pncp.gov.br" in url:
                return {
                    "situacaoCompraNome": "Divulgada no PNCP",
                    "dataEncerramentoProposta": "2026-08-20T18:00:00-03:00",
                }, "API"
            page = int((params or {}).get("pagina", 0))
            if page == 1:
                return {"result": [{"codigoLicitacao": 111}], "pageCount": 2}, "API"
            return {
                "result": [
                    {
                        "codigoLicitacao": 222,
                        "statusProcessoPublico": {"descricao": "Recebendo propostas"},
                        "dataHoraFinalPropostas": "2026-08-21T18:00:00Z",
                        "urlReferencia": "/sc/official-222",
                    }
                ],
                "pageCount": 2,
            }, "API"

    api = FakeApi()
    fetcher = _OfficialStatusFetcher(api)  # type: ignore[arg-type]

    pncp = fetcher(
        {
            "fonte": "PNCP",
            "cnpj_orgao": "12.345.678/0001-90",
            "ano_compra": "2026",
            "sequencial_compra": "9",
        }
    )
    pcp = fetcher(
        {
            "fonte": "PCP",
            "codigo_licitacao": 222,
            "data_publicacao_oficial": "2026-08-13T10:00:00Z",
        }
    )

    assert pncp == {
        "status_native": "Divulgada no PNCP",
        "deadline_at": "2026-08-20T18:00:00-03:00",
        "evidence_url": "https://pncp.gov.br/api/pncp/v1/orgaos/12345678000190/compras/2026/9",
    }
    assert pcp == {
        "status_native": "Recebendo propostas",
        "deadline_at": "2026-08-21T18:00:00Z",
        "evidence_url": "https://www.portaldecompraspublicas.com.br/sc/official-222",
    }
    assert [params["pagina"] for url, params in api.calls if "portaldecompraspublicas" in url] == [1, 2]
    assert all(
        params["dataInicial"] == params["dataFinal"] == "2026-08-13"
        for url, params in api.calls
        if "portaldecompraspublicas" in url
    )


def test_reenrichment_preview_does_not_mutate_existing_recommendation() -> None:
    editais = [_candidate("persisted-go")]

    summary = _preview_unexecuted_reconfirmation(editais)

    assert summary["decisions"]["NO_GO"] == 1
    assert editais == [_candidate("persisted-go")]


def test_pcp_reconfirmation_fails_closed_above_page_safety_bound() -> None:
    class TooManyPagesApi:
        def get(self, url: str, params: dict | None = None, label: str = "") -> tuple[dict, str]:
            del url, label
            return {"result": [], "pageCount": PCP_MAX_PAGES + 1}, "API"

    fetcher = _OfficialStatusFetcher(TooManyPagesApi())  # type: ignore[arg-type]

    try:
        fetcher(
            {
                "fonte": "PCP",
                "codigo_licitacao": 222,
                "data_publicacao_oficial": "2026-08-13T10:00:00Z",
            }
        )
    except RuntimeError as exc:
        assert "safety bound" in str(exc)
    else:
        raise AssertionError("unbounded PCP pagination should fail closed")
