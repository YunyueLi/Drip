"""LLM layer behaviour lock — provider resolution, HTTP error mapping, and the
template fallback. All hermetic: no network, no API keys.
"""

from __future__ import annotations

from typing import Any

import pytest

from drip.llm import LLMError, chat_or_fallback, list_providers, resolve
from drip.llm import client as llm_client
from drip.llm.providers import PROVIDERS

# --- resolve() ---------------------------------------------------------------

def test_resolve_explicit_provider() -> None:
    provider, model = resolve("openai/gpt-4o")
    assert provider.name == "openai"
    assert model == "gpt-4o"


def test_resolve_alias_prefix() -> None:
    provider, model = resolve("claude/claude-sonnet-4-6")
    assert provider.name == "anthropic"
    assert model == "claude-sonnet-4-6"


def test_resolve_bare_name_heuristic() -> None:
    assert resolve("gpt-4o")[0].name == "openai"
    assert resolve("claude-sonnet-4-6")[0].name == "anthropic"
    assert resolve("deepseek-chat")[0].name == "deepseek"


def test_resolve_unknown_routes_via_openrouter() -> None:
    # Unknown bare name and unknown vendor-prefixed name both go to OpenRouter.
    assert resolve("some-new-model-9000")[0].name == "openrouter"
    p, model = resolve("meta-llama/llama-3.3-70b")
    assert p.name == "openrouter"
    assert model == "meta-llama/llama-3.3-70b"  # whole spec preserved for routing


def test_list_providers_covers_the_advertised_set() -> None:
    names = {p.name for p in list_providers()}
    # README advertises "12 + OpenRouter".
    assert {"anthropic", "openai", "openrouter", "ollama"} <= names
    assert len(PROVIDERS) >= 12
    assert {p.protocol for p in list_providers()} <= {"anthropic", "openai"}


# --- _post error mapping (mocked transport) ----------------------------------

class _FakeResp:
    def __init__(self, status: int, text: str) -> None:
        self.status_code = status
        self.text = text

    def json(self) -> Any:
        import json
        return json.loads(self.text)


class _FakeClient:
    def __init__(self, status: int, text: str) -> None:
        self._status, self._text = status, text

    def __call__(self, *a: Any, **k: Any) -> _FakeClient:
        return self

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *a: Any) -> bool:
        return False

    def post(self, url: str, json: Any, headers: Any) -> _FakeResp:
        return _FakeResp(self._status, self._text)


def test_post_maps_http_400_to_llmerror(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_client.httpx, "Client", _FakeClient(400, "bad request"))
    with pytest.raises(LLMError, match="returned 400"):
        llm_client._post(PROVIDERS["openai"], "/chat/completions", {}, {}, 5.0)


# --- chat_or_fallback --------------------------------------------------------

def test_chat_or_fallback_returns_template_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**_: Any) -> Any:
        raise LLMError("simulated failure")

    monkeypatch.setattr(llm_client, "chat", _boom)
    out = chat_or_fallback(
        model="openai/gpt-4o", system="s", user_content="u", fallback="TEMPLATE",
    )
    assert out == "TEMPLATE"
