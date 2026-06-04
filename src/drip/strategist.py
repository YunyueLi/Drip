"""Strategist — turn performance into the next creative test.

This is the hardest, least-automated link in UA: "why did this win, what do
we test next?" Single-window campaign metrics can't do element-level
attribution (that's Feedback's job, with creative tagging), so the Strategist
works at the hypothesis level: rank what's working, propose the next
experiment and a brief.

The LLM writes the brief when a model is set; otherwise a deterministic
template keeps it runnable offline. Importing this module pulls in only the
data contract — drip.llm is lazy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from drip.data.metrics import AdMetrics


@dataclass
class CreativeHypothesis:
    direction: str        # "scale_winner" | "cut_loser" | "test_variant"
    target: str           # campaign label this is about
    rationale: str
    brief: str


@dataclass
class StrategyOutput:
    winners: list[AdMetrics] = field(default_factory=list)
    losers: list[AdMetrics] = field(default_factory=list)
    hypotheses: list[CreativeHypothesis] = field(default_factory=list)


class Strategist:
    def __init__(self, narrate_model: str | None = None) -> None:
        self.narrate_model = narrate_model

    def propose(
        self,
        metrics: list[AdMetrics],
        *,
        roas_target: float,
    ) -> StrategyOutput:
        ranked = sorted(metrics, key=lambda m: m.roas, reverse=True)
        winners = [m for m in ranked if m.roas >= roas_target]
        losers = [m for m in ranked if m.roas < roas_target]

        out = StrategyOutput(winners=winners, losers=losers)
        # Scale the top winner; cut the worst loser — the two highest-signal moves.
        if winners:
            w = winners[0]
            out.hypotheses.append(CreativeHypothesis(
                direction="scale_winner",
                target=w.label,
                rationale=f"ROAS {w.roas:.2f}x ≥ target {roas_target:.1f}x; CTR {w.ctr:.2%}",
                brief=self._brief("scale_winner", w, roas_target),
            ))
        if losers:
            loss = losers[-1]
            out.hypotheses.append(CreativeHypothesis(
                direction="cut_loser",
                target=loss.label,
                rationale=f"ROAS {loss.roas:.2f}x < target; spend ${loss.spend:.0f} better redeployed",
                brief=self._brief("cut_loser", loss, roas_target),
            ))
        return out

    def _brief(self, direction: str, m: AdMetrics, roas_target: float) -> str:
        if self.narrate_model:
            from drip.llm import chat_or_fallback

            ask = (
                "scale the winner: propose 3 creative variants on its winning hook"
                if direction == "scale_winner"
                else "cut the loser: propose a fresh angle to test instead"
            )
            user = (
                f"Campaign {m.label} on {m.platform}: ROAS {m.roas:.2f}x, "
                f"CTR {m.ctr:.2%}, CPP ${m.cpp:.2f}, spend ${m.spend:.0f}.\n"
                f"Task: {ask}. Give a 2-sentence creative brief, concrete."
            )
            template = ""  # filled below if LLM returns nothing
            text = chat_or_fallback(
                model=self.narrate_model,
                system="You are a UA creative strategist. Be concrete and brief.",
                user_content=user,
                max_tokens=200, temperature=0.4,
                fallback=template,
            )
            if text:
                return text
        # Template fallback
        if direction == "scale_winner":
            return (f"Double down on {m.label}: produce 3 variants on its winning "
                    f"hook (ROAS {m.roas:.2f}x). Keep the format, vary the opening 3s.")
        return (f"Cut {m.label} (ROAS {m.roas:.2f}x). Test a new angle for the same "
                f"audience — different hook, different value prop.")
