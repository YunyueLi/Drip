"""LLM provider registry.

One model string, any provider. Format: ``provider/model-id``.

    anthropic/claude-sonnet-4-6
    openai/gpt-4o
    google/gemini-2.0-flash
    deepseek/deepseek-chat
    openrouter/meta-llama/llama-3.3-70b-instruct
    ollama/llama3.1

Two wire protocols cover everything:

- ``anthropic`` — the Messages API (``/v1/messages``).
- ``openai``    — the Chat Completions API (``/chat/completions``). OpenAI,
  OpenRouter, Gemini (OpenAI-compat endpoint), DeepSeek, Qwen/DashScope,
  Moonshot, xAI, Groq, Together, Mistral, Ollama, and vLLM all speak it.

Anything we don't recognise falls back to **OpenRouter**, which itself
routes to hundreds of models — so `drip bench run --agent some/new-model`
just works as long as OpenRouter has it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provider:
    name: str
    protocol: str               # "anthropic" | "openai"
    base_url: str
    key_env: str | None         # None → no auth (local servers)
    base_url_env: str | None = None   # allow overriding base_url (local)
    extra_headers: dict[str, str] = field(default_factory=dict)
    notes: str = ""

    def resolved_base_url(self) -> str:
        if self.base_url_env:
            return os.environ.get(self.base_url_env, self.base_url)
        return self.base_url

    def api_key(self) -> str | None:
        if self.key_env is None:
            # local servers: allow an optional key but don't require it
            return os.environ.get(f"{self.name.upper()}_API_KEY")
        return os.environ.get(self.key_env)


# OpenRouter wants attribution headers; harmless elsewhere.
_OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://github.com/YunyueLi/Drip",
    "X-Title": "Drip",
}


PROVIDERS: dict[str, Provider] = {
    "anthropic": Provider(
        "anthropic", "anthropic", "https://api.anthropic.com/v1",
        "ANTHROPIC_API_KEY", notes="Claude — native Messages API",
    ),
    "openai": Provider(
        "openai", "openai", "https://api.openai.com/v1",
        "OPENAI_API_KEY", notes="GPT / o-series",
    ),
    "openrouter": Provider(
        "openrouter", "openai", "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY", extra_headers=_OPENROUTER_HEADERS,
        notes="Aggregator — hundreds of models; also the fallback router",
    ),
    "google": Provider(
        "google", "openai",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "GEMINI_API_KEY", notes="Gemini via OpenAI-compatible endpoint",
    ),
    "deepseek": Provider(
        "deepseek", "openai", "https://api.deepseek.com/v1",
        "DEEPSEEK_API_KEY", notes="DeepSeek V3 / R1",
    ),
    "dashscope": Provider(
        "dashscope", "openai",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "DASHSCOPE_API_KEY", notes="Alibaba Qwen (DashScope compat mode)",
    ),
    "moonshot": Provider(
        "moonshot", "openai", "https://api.moonshot.cn/v1",
        "MOONSHOT_API_KEY", notes="Moonshot Kimi",
    ),
    "xai": Provider(
        "xai", "openai", "https://api.x.ai/v1",
        "XAI_API_KEY", notes="xAI Grok",
    ),
    "groq": Provider(
        "groq", "openai", "https://api.groq.com/openai/v1",
        "GROQ_API_KEY", notes="Groq LPU — fast open models",
    ),
    "together": Provider(
        "together", "openai", "https://api.together.xyz/v1",
        "TOGETHER_API_KEY", notes="Together — hosted open models",
    ),
    "mistral": Provider(
        "mistral", "openai", "https://api.mistral.ai/v1",
        "MISTRAL_API_KEY", notes="Mistral / Codestral",
    ),
    "ollama": Provider(
        "ollama", "openai", "http://localhost:11434/v1",
        None, base_url_env="OLLAMA_BASE_URL", notes="Local Ollama",
    ),
    "vllm": Provider(
        "vllm", "openai", "http://localhost:8000/v1",
        None, base_url_env="VLLM_BASE_URL", notes="Local / self-hosted vLLM",
    ),
}

# Aliases people are likely to type.
ALIASES = {
    "claude": "anthropic",
    "gpt": "openai",
    "gemini": "google",
    "qwen": "dashscope",
    "kimi": "moonshot",
    "grok": "xai",
    "or": "openrouter",
}


# Bare-name heuristics: when someone types just a model id with no provider.
def _guess_provider(model: str) -> str:
    m = model.lower()
    if m.startswith(("gpt-", "gpt4", "o1", "o1-", "o3", "o3-", "o4", "chatgpt")):
        return "openai"
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gemini"):
        return "google"
    if m.startswith("deepseek"):
        return "deepseek"
    if m.startswith("qwen"):
        return "dashscope"
    if m.startswith(("moonshot", "kimi")):
        return "moonshot"
    if m.startswith("grok"):
        return "xai"
    if m.startswith("mistral") or m.startswith("codestral"):
        return "mistral"
    # Unknown → let OpenRouter route it.
    return "openrouter"


def resolve(spec: str) -> tuple[Provider, str]:
    """Resolve a model spec into (Provider, model_id).

    - ``provider/model`` with a known provider → that provider.
    - a known alias prefix (``claude/…``) → mapped provider.
    - a bare model id → heuristic, else OpenRouter.
    """
    spec = spec.strip()
    head, sep, tail = spec.partition("/")
    if sep:
        if head in PROVIDERS:
            return PROVIDERS[head], tail
        if head in ALIASES:
            return PROVIDERS[ALIASES[head]], tail
        # e.g. "meta-llama/llama-3.3-70b" — no provider prefix, route via OpenRouter
        return PROVIDERS["openrouter"], spec
    # no slash: a bare model id
    return PROVIDERS[_guess_provider(spec)], spec


def list_providers() -> list[Provider]:
    return list(PROVIDERS.values())
