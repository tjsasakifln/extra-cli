"""Refs #256 — generic public portal adapter never invents success."""

from __future__ import annotations

from scripts.factory_spine.portal import PortalStrategy, interpret_portal_fetch

HTML_LISTING = """
<table class="licitacoes">
  <tr><td>Edital 10/2026 Pregão Eletrônico</td><td><a href="/docs/edital-10.pdf">PDF</a></td></tr>
</table>
"""
HTML_LOGIN = """
<form id="login"><input type="password" name="senha" /><button>Entrar</button></form>
"""
HTML_CAPTCHA = """
<div class="g-recaptcha" data-sitekey="x"></div>
<p>Resolva o captcha para continuar</p>
"""
HTML_EMPTY = """
<html><body><h1>Portal da Transparência</h1><p>Bem-vindo</p></body></html>
"""
HTML_LAYOUT_V2 = """
<section class="cards">
  <article>Pregão 99/2026 <a href="/anexos/edital-99.pdf">baixar</a></article>
</section>
"""


def test_issue_256_login_captcha_403_are_blocked_not_empty_success() -> None:
    login = interpret_portal_fetch(url="https://pref.example.test/licitacoes", http_status=200, body=HTML_LOGIN)
    captcha = interpret_portal_fetch(url="https://pref.example.test/licitacoes", http_status=200, body=HTML_CAPTCHA)
    forbidden = interpret_portal_fetch(url="https://pref.example.test/licitacoes", http_status=403, body=HTML_LISTING)
    assert login.terminal == "BLOCKED"
    assert captcha.terminal == "BLOCKED"
    assert forbidden.terminal == "BLOCKED"
    assert login.records == ()
    assert forbidden.reason == "login_captcha_or_forbidden"


def test_issue_256_empty_or_error_page_is_never_zero_tenders() -> None:
    empty = interpret_portal_fetch(url="https://pref.example.test/licitacoes", http_status=200, body=HTML_EMPTY)
    server = interpret_portal_fetch(url="https://pref.example.test/licitacoes", http_status=504, body=HTML_EMPTY)
    assert empty.terminal == "FAILED"
    assert empty.reason == "empty_or_layout_unrecognized"
    assert server.terminal == "FAILED"
    assert empty.records == ()


def test_issue_256_html_pdf_and_layout_change_fixtures() -> None:
    found = interpret_portal_fetch(
        url="https://pref.example.test/licitacoes?token=abc", http_status=200, body=HTML_LISTING
    )
    assert found.terminal == "FOUND"
    assert found.records[0].document_url is not None
    assert found.records[0].document_url.endswith(".pdf")
    assert found.sanitized_url is not None
    assert "abc" not in (found.sanitized_url or "") or "token=" in found.sanitized_url
    v1 = interpret_portal_fetch(
        url="https://pref.example.test/licitacoes",
        http_status=200,
        body=HTML_LAYOUT_V2,
        strategy=PortalStrategy(version="generic-public-portal/v1:table"),
    )
    # v2 listing still extracts the PDF link so a layout change does not invent zero.
    assert v1.terminal == "FOUND"
    assert v1.records[0].document_url is not None
    assert v1.strategy_version.endswith(":table")
