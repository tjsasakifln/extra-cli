from scripts.cto.executive_sync import build_executive_payload, refresh_executive
from scripts.cto.observer import observe


def test_refresh_injects_panel_without_secrets(cto_repo):
    observe(cto_repo, write=True)
    result = refresh_executive(cto_repo)
    assert result["ok"] is True
    html = (cto_repo / "extra-consultoria-plano-executivo.html").read_text(encoding="utf-8")
    assert "CTO-AUTOPILOT-PANEL:START" in html
    assert "cto-autopilot-panel" in html
    assert "sk-" not in html
    assert "DEEPSEEK_API_KEY" not in html
    payload = build_executive_payload(cto_repo)
    assert "dod" in payload
