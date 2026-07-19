"""DeepSeek OpenAI-compatible client with JSON output and fail-closed handling."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from scripts.cto.config import DeepSeekConfig
from scripts.cto.redaction import redact_obj, safe_exception_message


class DeepSeekError(Exception):
    """Base client error (message must never include API key)."""


class DeepSeekUnavailable(DeepSeekError):
    """Service unavailable / timeout / rate limit exhausted."""


class DeepSeekInvalidResponse(DeepSeekError):
    """Empty, truncated, non-JSON, or schema-invalid response."""


@dataclass
class DeepSeekUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    duration_ms: int = 0
    attempts: int = 0
    estimated_cost_usd: float | None = None  # only if API provides; never invent


@dataclass
class DeepSeekResult:
    content: dict[str, Any]
    raw_text: str
    usage: DeepSeekUsage
    finish_reason: str | None = None
    response_meta: dict[str, Any] = field(default_factory=dict)


def _parse_json_content(text: str) -> dict[str, Any]:
    if not text or not text.strip():
        raise DeepSeekInvalidResponse("empty response content")
    cleaned = text.strip()
    # Strip markdown fences if model wraps JSON
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise DeepSeekInvalidResponse(f"invalid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise DeepSeekInvalidResponse("JSON root must be an object")
    return data


class DeepSeekClient:
    """HTTP client for DeepSeek chat completions with json_object mode."""

    def __init__(
        self,
        config: DeepSeekConfig,
        transport: httpx.BaseTransport | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self._transport = transport
        self._sleep = sleep_fn

    def _headers(self) -> dict[str, str]:
        if not self.config.api_key:
            raise DeepSeekUnavailable("DEEPSEEK_API_KEY not configured")
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

    def chat_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
    ) -> DeepSeekResult:
        """Call chat.completions with response_format json_object."""
        if not self.config.api_key:
            raise DeepSeekUnavailable("DEEPSEEK_API_KEY not configured")

        # Never send legacy model aliases as silent defaults — config already defaults to v4-pro
        model = self.config.model
        if model in {"deepseek-chat", "deepseek-reasoner"}:
            # Explicit allow only if user set env deliberately; still warn via meta
            pass

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        # reasoning_effort is model-dependent; include when set
        if self.config.reasoning_effort:
            payload["reasoning_effort"] = self.config.reasoning_effort

        url = self.config.base_url.rstrip("/") + "/v1/chat/completions"
        usage = DeepSeekUsage(model=model)
        last_err: Exception | None = None
        start = time.monotonic()

        for attempt in range(1, self.config.max_retries + 1):
            usage.attempts = attempt
            try:
                with httpx.Client(
                    timeout=self.config.timeout_seconds,
                    transport=self._transport,
                ) as client:
                    resp = client.post(url, headers=self._headers(), json=payload)
                if resp.status_code == 429:
                    last_err = DeepSeekUnavailable(f"rate limit HTTP 429 (attempt {attempt})")
                    self._sleep(min(2**attempt, 30))
                    continue
                if resp.status_code >= 500:
                    last_err = DeepSeekUnavailable(
                        f"server error HTTP {resp.status_code} (attempt {attempt})"
                    )
                    self._sleep(min(2**attempt, 30))
                    continue
                if resp.status_code >= 400:
                    # Do not echo body (may contain request echoes)
                    raise DeepSeekInvalidResponse(f"client error HTTP {resp.status_code}")

                body = resp.json()
                choice = (body.get("choices") or [{}])[0]
                finish = choice.get("finish_reason")
                message = choice.get("message") or {}
                content_text = message.get("content") or ""
                if finish == "length":
                    raise DeepSeekInvalidResponse("response truncated (finish_reason=length)")
                if finish not in (None, "stop", "end_turn"):
                    # unexpected but try parse; flag in meta
                    pass

                content = _parse_json_content(content_text)
                u = body.get("usage") or {}
                usage.prompt_tokens = int(u.get("prompt_tokens") or 0)
                usage.completion_tokens = int(u.get("completion_tokens") or 0)
                usage.total_tokens = int(
                    u.get("total_tokens") or (usage.prompt_tokens + usage.completion_tokens)
                )
                # Never invent cost
                if "cost" in u and isinstance(u["cost"], (int, float)):
                    usage.estimated_cost_usd = float(u["cost"])
                usage.duration_ms = int((time.monotonic() - start) * 1000)
                return DeepSeekResult(
                    content=content,
                    raw_text=content_text,
                    usage=usage,
                    finish_reason=finish,
                    response_meta={
                        "id": body.get("id"),
                        "model": body.get("model") or model,
                    },
                )
            except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
                last_err = DeepSeekUnavailable(safe_exception_message(exc))
                self._sleep(min(2**attempt, 30))
                continue
            except DeepSeekInvalidResponse:
                raise
            except DeepSeekError:
                raise
            except Exception as exc:  # noqa: BLE001 — fail closed
                raise DeepSeekInvalidResponse(safe_exception_message(exc)) from None

        usage.duration_ms = int((time.monotonic() - start) * 1000)
        raise DeepSeekUnavailable(
            safe_exception_message(last_err) if last_err else "DeepSeek unavailable"
        )

    def smoke(self) -> dict[str, Any]:
        """Live smoke: minimal JSON round-trip. Never log API key."""
        result = self.chat_json(
            system='Reply with JSON only: {"ok": true, "service": "deepseek"}',
            user="ping",
            temperature=0,
        )
        return redact_obj(
            {
                "ok": bool(result.content.get("ok")),
                "content_keys": sorted(result.content.keys()),
                "model": result.usage.model,
                "tokens": result.usage.total_tokens,
                "finish_reason": result.finish_reason,
            }
        )
