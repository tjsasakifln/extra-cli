import json

import httpx
import pytest

from scripts.cto.config import DeepSeekConfig
from scripts.cto.deepseek_client import (
    DeepSeekClient,
    DeepSeekInvalidResponse,
    DeepSeekUnavailable,
    _parse_json_content,
)


def test_parse_json_content_ok():
    assert _parse_json_content('{"a": 1}') == {"a": 1}


def test_parse_json_empty():
    with pytest.raises(DeepSeekInvalidResponse):
        _parse_json_content("")


def test_parse_json_invalid():
    with pytest.raises(DeepSeekInvalidResponse):
        _parse_json_content("not-json")


def test_parse_json_fenced():
    text = '```json\n{"ok": true}\n```'
    assert _parse_json_content(text)["ok"] is True


def test_missing_api_key():
    client = DeepSeekClient(DeepSeekConfig(api_key=""))
    with pytest.raises(DeepSeekUnavailable):
        client.chat_json(system="s", user="u")


def test_chat_json_success():
    def handler(request: httpx.Request) -> httpx.Response:
        body = {
            "id": "x",
            "model": "deepseek-v4-pro",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": json.dumps({"decision": "NOOP", "ok": True})},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(handler)
    client = DeepSeekClient(
        DeepSeekConfig(api_key="sk-test-key-not-real", max_retries=1),
        transport=transport,
        sleep_fn=lambda _: None,
    )
    result = client.chat_json(system="sys", user="user")
    assert result.content["ok"] is True
    assert result.usage.total_tokens == 15
    # key must not appear in raw content path — we just ensure result redaction elsewhere


def test_chat_json_empty_content():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": ""}}],
                "usage": {},
            },
        )

    client = DeepSeekClient(
        DeepSeekConfig(api_key="sk-test", max_retries=1),
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(DeepSeekInvalidResponse):
        client.chat_json(system="s", user="u")


def test_chat_json_truncated():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": '{"partial":'},
                    }
                ],
                "usage": {},
            },
        )

    client = DeepSeekClient(
        DeepSeekConfig(api_key="sk-test", max_retries=1),
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(DeepSeekInvalidResponse, match="truncated"):
        client.chat_json(system="s", user="u")


def test_chat_json_retry_on_500():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500, json={"error": "tmp"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '{"ok": true}'}}
                ],
                "usage": {"total_tokens": 1},
            },
        )

    client = DeepSeekClient(
        DeepSeekConfig(api_key="sk-test", max_retries=3),
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _: None,
    )
    result = client.chat_json(system="s", user="u")
    assert result.content["ok"] is True
    assert calls["n"] == 3


def test_rate_limit_exhaust():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate"})

    client = DeepSeekClient(
        DeepSeekConfig(api_key="sk-test", max_retries=2),
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(DeepSeekUnavailable):
        client.chat_json(system="s", user="u")
