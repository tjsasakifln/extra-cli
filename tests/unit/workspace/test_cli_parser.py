"""Parser tests — all workspace subcommands must be registered."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.workspace.cli import build_parser  # noqa: E402

REQUIRED_COMMANDS = {
    "today",
    "opportunities",
    "dossier",
    "coverage",
    "competitors",
    "expiring-contracts",
    "prices",
    "edital",
    "proposal",
    "contracts",
    "decide",
    "briefing",
    "report",
}


class TestWorkspaceParser:
    def test_all_subcommands_registered(self) -> None:
        parser = build_parser()
        # argparse stores subparsers actions; collect dest=command choices
        subcommands: set[str] = set()
        for action in parser._actions:
            if getattr(action, "dest", None) == "command" and getattr(action, "choices", None):
                subcommands = set(action.choices.keys())
                break
        missing = REQUIRED_COMMANDS - subcommands
        assert not missing, f"Missing subcommands: {missing}"
        assert REQUIRED_COMMANDS <= subcommands

    def test_today_parses(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["today", "--json", "--hours", "24"])
        assert args.command == "today"
        assert args.json is True
        assert args.hours == 24

    def test_opportunities_filters(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "opportunities",
                "--orgao",
                "PMF",
                "--municipio",
                "Florianopolis",
                "--distance",
                "200",
                "--modalidade",
                "pregao",
                "--valor",
                "1000",
                "--prazo",
                "7",
                "--status",
                "open",
                "--score",
                "50",
                "--ranking",
                "GO,REVIEW",
                "--fonte",
                "pncp",
                "--search",
                "reforma",
            ]
        )
        assert args.command == "opportunities"
        assert args.orgao == "PMF"
        assert args.distance == 200.0
        assert args.ranking == "GO,REVIEW"

    def test_dossier_id(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["dossier", "42"])
        assert args.command == "dossier"
        assert args.id == "42"

    def test_edital_analyze(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["edital", "analyze", "/tmp/edital.pdf"])
        assert args.command == "edital"
        assert args.edital_command == "analyze"
        assert args.path_or_url == "/tmp/edital.pdf"

    def test_proposal_support(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["proposal", "support", "99"])
        assert args.command == "proposal"
        assert args.proposal_command == "support"
        assert args.opp_id == "99"

    def test_decide_required(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "decide",
                "--id",
                "1",
                "--decision",
                "approve",
                "--reason",
                "fit",
            ]
        )
        assert args.decision == "approve"

    def test_report_kinds(self) -> None:
        parser = build_parser()
        for kind in ("daily", "weekly"):
            args = parser.parse_args(["report", kind])
            assert args.report_kind == kind

    def test_expiring_contracts_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["expiring-contracts", "--limit", "10"])
        assert args.command == "expiring-contracts"

    def test_no_command_leaves_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None
