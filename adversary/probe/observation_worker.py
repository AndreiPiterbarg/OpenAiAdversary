"""JSON-line observation worker. Source executes only after kernel confinement is installed.

No capabilities to open files, create sockets/processes, or address other processes remain.
Only standard input/output and memory/clock operations are allowed. This is Linux-specific;
missing kernel/library support is a refusal, never an unsandboxed fallback.
"""

import json
import os
import resource
import sys
from typing import Any

from adversary.core.factors import Cell
from adversary.domain.channel import Channel
from adversary.execution.confinement import confine
from adversary.probe.program import ProgramKind, ProgramSource


def main() -> None:
    """Maintain only intervention state between observations; return bounded JSON replies."""
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # close_fds at spawn is essential; stdio are anonymous pipes, not inherited files.
    init = json.loads(sys.stdin.readline())
    confine()
    program = ProgramSource.model_validate(init["program"])
    if program.kind is not ProgramKind.PERTURBATION:
        raise ValueError("expected a perturbation program")
    instance = program.load()(Cell(levels=init["cell"]), seed=init["seed"], **init["config"])
    if instance.channel is not Channel.OBSERVATION:
        raise ValueError("this executor supports only the observation channel")
    if tuple(instance.clauses) != tuple(init["clauses"]):
        raise ValueError("program clauses differ from the trusted declaration")
    instance.prepare(None, init["spec"])
    print(json.dumps({"ready": True, "pid": os.getpid()}), flush=True)
    for line in sys.stdin:
        call: dict[str, Any] = json.loads(line)
        result = instance.observe(call["step"], call["tool"], call["args"], call["result"])
        if not isinstance(result, str):
            raise ValueError("observe must return text")
        if len(result.encode()) > 1_000_000:
            raise ValueError("observation exceeds the output limit")
        print(json.dumps({"result": result}), flush=True)


if __name__ == "__main__":
    main()
