"""One pure program operation per confined process."""

import json
import resource
import sys

from adversary.core.factors import Cell
from adversary.core.trajectory import Trajectory
from adversary.execution.confinement import confine
from adversary.probe.program import ProgramKind, ProgramSource


def main() -> None:
    request = json.loads(sys.stdin.readline())
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    source = ProgramSource.model_validate(request["program"])
    confine()
    cls = source.load()
    operation = request["operation"]
    if operation == "generate" and source.kind is ProgramKind.GENERATOR:
        n = request["n"]
        if type(n) is not int or not 1 <= n <= 100:
            raise ValueError("invalid draw count")
        generator = cls(Cell(levels=request["cell"]), seed=request["seed"], **request["config"])
        result = {"instances": [i.model_dump(mode="json") for i in generator.generate_batch(n)]}
    elif operation == "inspect":
        if source.kind is ProgramKind.PERTURBATION:
            program = cls(Cell(levels=request["cell"]), seed=0)
            result = {"channel": program.channel, "clauses": program.clauses}
        elif source.kind is ProgramKind.VERIFIER:
            cls()
            result = {"kind": source.kind}
        else:
            result = {"kind": source.kind}
    elif operation == "verify" and source.kind is ProgramKind.VERIFIER:
        verdict = cls().verify(Trajectory.model_validate(request["trajectory"]), request["oracle"])
        result = {"verdict": verdict.model_dump(mode="json")}
    else:
        raise ValueError("operation does not match program kind")
    print(json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
