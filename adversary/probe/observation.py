"""Stateful observation programs behind a bounded, kernel-confined subprocess boundary."""

from typing import Any

from adversary.core.factors import Cell
from adversary.domain.channel import Channel
from adversary.domain.perturbation import Perturbation
from adversary.execution.json_worker import JsonWorker, WorkerError
from adversary.probe.program import ProgramKind, ProgramSource

ObservationError = WorkerError


class IsolatedObservation(Perturbation, JsonWorker):
    """Only text and explicit per-instance data cross this boundary, never a live session."""

    channel = Channel.OBSERVATION

    def __init__(
        self,
        program: ProgramSource,
        clauses: tuple[str, ...],
        cell: Cell,
        seed: int,
        config: dict[str, Any],
        *,
        timeout: float = 5.0,
    ) -> None:
        if program.kind is not ProgramKind.PERTURBATION:
            raise ValueError("expected a perturbation program")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.clauses = clauses
        Perturbation.__init__(self, cell, seed, **config)
        self.program, self.seed, self.timeout = program, seed, timeout
        JsonWorker.__init__(self, "adversary.probe.observation_worker", timeout)

    def prepare(self, session: Any, spec: Any) -> None:
        if session is not None:
            raise ValueError("observation programs cannot receive a live session")
        reply = self.start(
            {
                "program": self.program.model_dump(mode="json"),
                "cell": self.cell.levels,
                "clauses": self.clauses,
                "seed": self.seed,
                "config": self.config,
                "spec": spec,
            }
        )
        if reply.get("ready") is not True:
            self.close()
            raise ObservationError("worker did not attest successful initialization")

    def observe(self, step: int, tool: str, args: dict[str, Any], result: str) -> str:
        reply = self._exchange({"step": step, "tool": tool, "args": args, "result": result})
        if set(reply) != {"result"} or not isinstance(reply["result"], str):
            self.close()
            raise ObservationError("observe must return text")
        if not self.active and reply["result"] != result:
            self.close()
            raise ObservationError("inactive intervention changed an observation")
        return reply["result"]

    def close(self) -> None:
        JsonWorker.close(self)
