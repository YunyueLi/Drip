"""Unified chat client over every provider in the registry.

One function — :func:`chat` — takes a model spec like ``openai/gpt-4o`` or
``anthropic/claude-sonnet-4-6`` and returns a normalized :class:`ChatResult`,
regardless of which wire protocol the provider speaks.

Uses ``httpx`` (already a core dep). No per-vendor SDK required.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from drip.llm.providers import Provider, resolve
from drip.log import logger


class LLMError(RuntimeError):
    """Any failure talking to a provider."""


class MissingKeyError(LLMError):
    def __init__(self, provider: Provider) -> None:
        self.provider = provider
        super().__init__(
            f"provider '{provider.name}' needs ${provider.key_env} to be set"
        )


@dataclass
class ChatResult:
    text: str
    model: str                  # provider/model_id as requested
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict[str, object] = field(default_factory=dict)

    def json(self) -> Any:
        """Parse the response text as JSON, tolerating ```json fences."""
        return _loads_lenient(self.text)


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def chat(
    *,
    model: str,
    messages: list[dict[str, str]],
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    json_mode: bool = False,
    timeout: float = 60.0,
) -> ChatResult:
    """Send a chat request to any provider.

    ``messages`` is a list of ``{"role": "user"|"assistant", "content": str}``.
    ``system`` is the system prompt (hoisted correctly per protocol).
    ``json_mode`` requests strict JSON output where the provider supports it,
    and otherwise appends a JSON-only instruction.
    """
    provider, model_id = resolve(model)
    key = provider.api_key()
    if provider.key_env is not None and not key:
        raise MissingKeyError(provider)

    if provider.protocol == "anthropic":
        return _chat_anthropic(
            provider, model_id, model, messages, system,
            max_tokens, temperature, json_mode, key, timeout,
        )
    return _chat_openai(
        provider, model_id, model, messages, system,
        max_tokens, temperature, json_mode, key, timeout,
    )


# --------------------------------------------------------------------------
# Anthropic Messages API
# --------------------------------------------------------------------------


def _chat_anthropic(
    provider: Provider, model_id: str, requested: str,
    messages: list[dict[str, str]], system: str | None,
    max_tokens: int, temperature: float, json_mode: bool,
    key: str | None, timeout: float,
) -> ChatResult:
    sys_prompt = system or ""
    if json_mode:
        sys_prompt = (sys_prompt + "\n\nRespond with ONLY a valid JSON object, "
                      "no prose, no code fences.").strip()
    body: dict[str, object] = {
        "model": model_id,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if sys_prompt:
        body["system"] = sys_prompt
    headers = {
        "x-api-key": key or "",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        **provider.extra_headers,
    }
    data = _post(provider, "/messages", body, headers, timeout)
    text = "".join(
        b.get("text", "") for b in data.get("content", [])
        if b.get("type") == "text"
    )
    return ChatResult(
        text=text.strip(),
        model=requested,
        provider=provider.name,
        usage=data.get("usage", {}) or {},
        raw=data,
    )


# --------------------------------------------------------------------------
# OpenAI-compatible Chat Completions API
# --------------------------------------------------------------------------


def _chat_openai(
    provider: Provider, model_id: str, requested: str,
    messages: list[dict[str, str]], system: str | None,
    max_tokens: int, temperature: float, json_mode: bool,
    key: str | None, timeout: float,
) -> ChatResult:
    full_messages: list[dict[str, str]] = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    body: dict[str, object] = {
        "model": model_id,
        "messages": full_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    headers = {"content-type": "application/json", **provider.extra_headers}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    data = _post(provider, "/chat/completions", body, headers, timeout)
    try:
        text = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"unexpected response shape from {provider.name}: "
                       f"{json.dumps(data)[:300]}") from exc
    return ChatResult(
        text=text.strip(),
        model=requested,
        provider=provider.name,
        usage=data.get("usage", {}) or {},
        raw=data,
    )


# --------------------------------------------------------------------------
# Transport + helpers
# --------------------------------------------------------------------------


def _post(
    provider: Provider, path: str, body: dict[str, object],
    headers: dict[str, str], timeout: float,
) -> Any:
    url = provider.resolved_base_url().rstrip("/") + path
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=body, headers=headers)
        if resp.status_code >= 400:
            raise LLMError(
                f"{provider.name} returned {resp.status_code}: {resp.text[:400]}"
            )
        return resp.json()
    except httpx.HTTPError as exc:
        raise LLMError(f"network error calling {provider.name} ({url}): {exc}") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMError(
            f"unexpected response from {provider.name} (not JSON): {exc}"
        ) from exc


def chat_or_fallback(
    *,
    model: str,
    system: str,
    user_content: str,
    max_tokens: int = 300,
    temperature: float = 0.0,
    fallback: str,
) -> str:
    """Call :func:`chat` for narration; return *fallback* on any error.

    Logs failures so operations can detect when LLM narration degrades to
    template mode. Used by :mod:`drip.analyst`, :mod:`drip.strategist`, and
    :mod:`drip.engine.engine`.
    """
    try:
        result = chat(
            model=model,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return result.text or fallback
    except LLMError:
        logger.warning("LLM chat failed, falling back to template", exc_info=True)
        return fallback


def _loads_lenient(text: str) -> Any:
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?", "", s).rstrip("`").strip()
    # Some models wrap JSON in prose; grab the first {...} block.
    if not s.startswith("{"):
        match = re.search(r"\{.*\}", s, re.DOTALL)
        if match:
            s = match.group(0)
    return json.loads(s)
