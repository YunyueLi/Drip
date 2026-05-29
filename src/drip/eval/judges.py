"""LLM-as-judge for reasoning quality.

The judge reads each ``reasoning_must_mention`` item and decides whether
the agent's free-text reasoning covers it (full / partial / none).

The model-backed judge runs on the unified :mod:`drip.llm` layer, so the
judge can be any provider (``--judge openai/gpt-4o``). When no key is
available at all, a keyword-heuristic judge keeps local dev unblocked.
"""

from __future__ import annotations

import os
import re
from typing import Literal, Protocol

from drip.eval.schema import ReasoningCheck
from drip.llm import LLMError, chat

DEFAULT_JUDGE_MODEL = "anthropic/claude-sonnet-4-6"


class Judge(Protocol):
    name: str

    def evaluate(
        self, reasoning: str, must_mention: list[str]
    ) -> list[ReasoningCheck]: ...


# --------------------------------------------------------------------------
# Heuristic judge — no API key required
# --------------------------------------------------------------------------


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower())


class HeuristicJudge:
    """Keyword-overlap judge. ≥60% of an item's content words present → full,
    ≥30% → partial, else none. Crude but unblocks no-key development."""

    name = "heuristic"

    def evaluate(
        self, reasoning: str, must_mention: list[str]
    ) -> list[ReasoningCheck]:
        out: list[ReasoningCheck] = []
        r_words = set(_normalize(reasoning).split())
        for mention in must_mention:
            keywords = [w for w in _normalize(mention).split() if len(w) > 3]
            if not keywords:
                out.append(ReasoningCheck(mention=mention, coverage="none",
                                          notes="empty keyword set"))
                continue
            hit = sum(1 for k in keywords if k in r_words) / len(keywords)
            coverage: Literal["full", "partial", "none"] = (
                "full" if hit >= 0.6 else "partial" if hit >= 0.3 else "none"
            )
            out.append(ReasoningCheck(mention=mention, coverage=coverage,
                                      notes=f"keyword hit rate {hit:.0%}"))
        return out


# --------------------------------------------------------------------------
# LLM judge — any provider via drip.llm
# --------------------------------------------------------------------------

JUDGE_SYSTEM = """You are a strict grader for UA-agent reasoning. You read an \
agent's free-text reasoning and a list of "must-mention" points a good answer \
should cover. For each point decide coverage:

- "full"    — the reasoning clearly and specifically makes this point
- "partial" — adjacent or implicit, but not explicit
- "none"    — not addressed

Be strict: a vague gesture is "partial", not "full".

Return ONLY a JSON object of this exact shape:
{"checks": [{"mention": "<verbatim>", "coverage": "full|partial|none", "notes": "<one short sentence>"}]}"""


class LLMJudge:
    def __init__(self, model: str = DEFAULT_JUDGE_MODEL) -> None:
        self.model = model
        self.name = f"judge:{model}"

    def evaluate(
        self, reasoning: str, must_mention: list[str]
    ) -> list[ReasoningCheck]:
        if not must_mention:
            return []
        user = (
            "REASONING TO GRADE:\n"
            f"{reasoning.strip()}\n\n"
            "MUST-MENTION POINTS:\n"
            + "\n".join(f"- {m}" for m in must_mention)
        )
        try:
            result = chat(
                model=self.model,
                system=JUDGE_SYSTEM,
                messages=[{"role": "user", "content": user}],
                json_mode=True,
                max_tokens=1024,
                temperature=0.0,
            )
            payload = result.json()
        except LLMError as exc:
            raise RuntimeError(f"judge '{self.name}' failed: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"judge '{self.name}' returned non-JSON") from exc

        checks_raw = payload.get("checks", []) if isinstance(payload, dict) else []
        out: list[ReasoningCheck] = []
        for item in checks_raw:
            out.append(ReasoningCheck(
                mention=item.get("mention", ""),
                coverage=item.get("coverage", "none"),
                notes=item.get("notes", ""),
            ))
        # Fallback: if the model under-reported, mark the rest as none.
        if len(out) < len(must_mention):
            seen = {c.mention for c in out}
            for m in must_mention:
                if m not in seen:
                    out.append(ReasoningCheck(mention=m, coverage="none",
                                              notes="not returned by judge"))
        return out


def default_judge(model: str | None = None) -> Judge:
    """Pick a judge. Explicit model → LLMJudge. Else if any common key is
    set → LLMJudge on the default model. Else → HeuristicJudge."""
    if model:
        return LLMJudge(model)
    for env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        if os.environ.get(env):
            return LLMJudge(DEFAULT_JUDGE_MODEL if env == "ANTHROPIC_API_KEY"
                            else "openai/gpt-4o" if env == "OPENAI_API_KEY"
                            else "openrouter/anthropic/claude-3.5-sonnet")
    return HeuristicJudge()
