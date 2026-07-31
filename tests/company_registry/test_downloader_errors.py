"""Downloader error classification with a local HTTP server."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from scripts.company_registry.downloader import download_file


class _Handler(BaseHTTPRequestHandler):
    mode = "ok"
    payload = b"PK\x03\x04"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.mode == "404":
            self.send_response(404)
            self.end_headers()
            return
        if self.mode == "403":
            self.send_response(403)
            self.end_headers()
            return
        if self.mode == "429":
            self.send_response(429)
            self.end_headers()
            return
        if self.mode == "500":
            self.send_response(500)
            self.end_headers()
            return
        if self.mode == "html":
            body = b"<!DOCTYPE html><html></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = self.payload
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def http_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}/file.zip", _Handler
    server.shutdown()


def test_http_error_codes(http_server, tmp_path):
    base, handler = http_server
    for mode in ("404", "403", "429", "500"):
        handler.mode = mode
        dest = tmp_path / f"{mode}.zip"
        if dest.exists():
            dest.unlink()
        res = download_file(base, dest, max_attempts=2, timeout=2.0)
        assert res["ok"] is False
        assert res["attempts"] >= 1


def test_html_payload_rejected(http_server, tmp_path):
    base, handler = http_server
    handler.mode = "html"
    dest = tmp_path / "x.zip"
    res = download_file(base, dest, max_attempts=1, timeout=2.0)
    assert res["ok"] is False
