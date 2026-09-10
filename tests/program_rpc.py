"""Transport only: source execution stays in the existing confined worker."""

import json
import sys

from adversary.probe.executor import ConfinedPrograms
from adversary.probe.program import ProgramSource

if __name__ == "__main__":
    request = json.load(sys.stdin)
    source = ProgramSource.model_validate(request.pop("program"))
    try:
        result = ConfinedPrograms()._call(source, **request)
        print(json.dumps({"result": result}, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"program_error": str(exc)}))
