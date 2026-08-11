"""National process harvest must never treat pilot 50 as capacity."""

from __future__ import annotations

import pytest

from scripts.confenge_activation.operational_metrics import PILOT_ACCEPTANCE_SAMPLE
from scripts.confenge_process_enrichment.national_confirmed import (
    NationalHarvestConfig,
    run_national_process_harvest,
)


def test_refuse_pilot_sample_as_max_companies(tmp_path) -> None:  # noqa: ANN001
    cfg = NationalHarvestConfig(
        output_dir=tmp_path,
        max_companies=PILOT_ACCEPTANCE_SAMPLE,
    )
    with pytest.raises(ValueError, match="pilot sample only"):
        run_national_process_harvest("postgresql://invalid", cfg=cfg)


def test_terminal_from_process_result_mapping() -> None:
    from scripts.confenge_contact_resolution.discovery_state import (
        CONTACT_EXHAUSTED,
        CONTACT_READY,
    )
    from scripts.confenge_process_enrichment.models import TerminalState
    from scripts.confenge_process_enrichment.national_confirmed import (
        _terminal_from_process_result,
    )

    class _R:
        def __init__(self, t: TerminalState) -> None:
            self.terminal_state = t

    assert _terminal_from_process_result(_R(TerminalState.EMAIL_SEND_READY)) == CONTACT_READY
    assert (
        _terminal_from_process_result(_R(TerminalState.NO_CONTACT_FOUND)) == CONTACT_EXHAUSTED
    )
