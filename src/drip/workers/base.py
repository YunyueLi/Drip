"""Worker base class — shared contract between orchestrator and workers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from drip.orchestrator import RunContext


@dataclass
class WorkerResult:
    """Structured return from a worker step.

    `lines` are human-readable progress / summary lines printed by the
    orchestrator. `data` is the machine-readable payload that downstream
    workers consume (stashed in ctx.artifacts under the worker name).
    """

    lines: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


class Worker(ABC):
    """A domain expert that owns one slice of the UA pipeline."""

    name: str = "worker"
    model: str = "claude-sonnet-4-6"

    @abstractmethod
    async def run(self, ctx: "RunContext") -> WorkerResult: ...
