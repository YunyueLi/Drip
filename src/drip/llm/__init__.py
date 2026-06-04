"""Unified multi-provider LLM layer.

    from drip.llm import chat
    r = chat(model="openai/gpt-4o", messages=[{"role": "user", "content": "hi"}])
    print(r.text)

Supports Anthropic + every OpenAI-compatible provider (OpenAI, OpenRouter,
Gemini, DeepSeek, Qwen, Moonshot, xAI, Groq, Together, Mistral, Ollama,
vLLM). Unknown model names fall back to OpenRouter.
"""

from drip.llm.client import ChatResult, LLMError, MissingKeyError, chat, chat_or_fallback
from drip.llm.providers import PROVIDERS, Provider, list_providers, resolve

__all__ = [
    "PROVIDERS",
    "ChatResult",
    "LLMError",
    "MissingKeyError",
    "Provider",
    "chat",
    "chat_or_fallback",
    "list_providers",
    "resolve",
]
