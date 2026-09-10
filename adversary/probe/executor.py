"""Program evaluation adapters; live model output always uses the confined adapter."""

from copy import deepcopy
from typing import Any

from adversary.core.factors import Cell
from adversary.core.instance import Instance
from adversary.core.trajectory import Trajectory
from adversary.core.verify import Verdict
from adversary.execution.json_worker import JsonWorker
from adversary.probe.program import ProgramKind, ProgramSource


class ProgramExecutor:
    """In-process adapter exclusively for trusted authored code and local contract tests."""

    confined = False

    def inspect(self, program: ProgramSource, cell: Cell) -> dict[str, Any]:
        cls = program.load()
        if program.kind is ProgramKind.PERTURBATION:
            instance = cls(cell, seed=0)
            return {"channel": instance.channel, "clauses": instance.clauses}
        if program.kind is ProgramKind.VERIFIER:
            cls()
        return {"kind": program.kind}

    def generate(
        self,
        program: ProgramSource,
        cell: Cell,
        seed: int,
        config: dict[str, Any],
        n: int,
    ) -> list[Instance]:
        return program.load()(cell, seed=seed, **config).generate_batch(n)

    def verify(self, program: ProgramSource, trajectory: Trajectory, oracle: Any) -> Verdict:
        return program.load()().verify(trajectory, oracle)


class ConfinedPrograms(ProgramExecutor):
    """Source is loaded only after the child installs kernel confinement."""

    confined = True

    def __init__(self, timeout: float = 10) -> None:
        self.timeout = timeout

    def _call(self, program: ProgramSource, **request: Any) -> dict[str, Any]:
        worker = JsonWorker("adversary.probe.program_worker", self.timeout)
        try:
            return worker.start({"program": program.model_dump(mode="json"), **request})
        finally:
            worker.close()

    def inspect(self, program: ProgramSource, cell: Cell) -> dict[str, Any]:
        return self._call(program, operation="inspect", cell=cell.levels)

    def generate(
        self,
        program: ProgramSource,
        cell: Cell,
        seed: int,
        config: dict[str, Any],
        n: int,
    ) -> list[Instance]:
        # Source may copy arbitrary input into its output. Do not expose hidden labels or
        # trusted payloads, even inside the isolated process; rebind them only in the parent.
        hidden = {name: deepcopy(config[name]) for name in ("spec", "oracle") if name in config}
        handles = {name: {"__bound_input__": name} for name in hidden}
        safe_config = {**deepcopy(config), **handles}
        reply = self._call(
            program, operation="generate", cell=cell.levels, seed=seed, config=safe_config, n=n
        )
        instances = [Instance.model_validate(i) for i in reply["instances"]]
        if len(instances) != n:
            raise ValueError("worker returned the wrong draw count")
        rebound = []
        for instance in instances:
            if any(getattr(instance, name) != handles[name] for name in hidden):
                raise ValueError("generator replaced an opaque trusted input")
            rebound.append(Instance.model_validate({**dict(instance), **deepcopy(hidden)}))
        return rebound

    def verify(self, program: ProgramSource, trajectory: Trajectory, oracle: Any) -> Verdict:
        reply = self._call(
            program,
            operation="verify",
            trajectory=trajectory.model_dump(mode="json"),
            oracle=oracle,
        )
        return Verdict.model_validate(reply["verdict"])
