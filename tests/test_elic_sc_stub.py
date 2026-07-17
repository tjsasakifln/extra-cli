"""Contract tests for E-Lic SC HTML structure stub.

Fails loudly when fixture is present and required markers disappear.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.crawl import elic_sc_stub as elic

FIXTURE = Path(__file__).parent / "fixtures" / "elic" / "default_aspx_min.html"


class TestElicStub:
    def test_limitation_documented(self):
        assert "anonymous open JSON" in elic.LIMITATION or "open JSON" in elic.LIMITATION
        assert elic.PUBLIC_URLS["mural"].startswith("https://e-lic.sc.gov.br")

    def test_crawl_stub_returns_empty(self):
        assert elic.crawl("full") == []
        assert elic.transform([]) == []

    def test_structure_ok_on_fixture(self):
        if not FIXTURE.exists():
            pytest.fail(f"Expected fixture missing: {FIXTURE}")
        html = FIXTURE.read_text(encoding="utf-8")
        missing = elic.assert_structure(html)
        assert missing == []

    def test_structure_fails_loudly_when_markers_removed(self):
        html = "<html><body>empty portal shell</body></html>"
        with pytest.raises(AssertionError) as exc:
            elic.assert_structure(html)
        msg = str(exc.value)
        assert "structure changed" in msg.lower() or "missing required" in msg.lower()
        assert "aspnetForm" in msg or "areaConteudo" in msg

    def test_structure_report(self):
        html = FIXTURE.read_text(encoding="utf-8")
        report = elic.structure_report(html)
        assert report["public_json"] is False
        assert report["all_required_ok"] is True
        assert report["markers"]["form#aspnetForm"] is True
