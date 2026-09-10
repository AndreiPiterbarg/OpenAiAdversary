"""Generator and verifier for the toy arithmetic domain.

Kept separate from the environment so this file can be loaded as probe program source: it
imports nothing from the model boundary, which the verifier rule requires.
"""

import random
import re
from typing import Any

from adversary.core.factors import Cell
from adversary.core.generator import Generator
from adversary.core.instance import Instance, Provenance
from adversary.core.trajectory import Trajectory
from adversary.core.util import short_id
from adversary.core.verify import Verdict, Verifier

TOY_SPACE_FINGERPRINT = "toy"


class ToyGenerator(Generator):
    """Arithmetic questions whose difficulty is set by the cell."""

    version = "1"

    def __init__(self, cell: Cell, seed: int | None = None, **config: Any) -> None:
        super().__init__(cell, seed, **config)
        self.pool = tuple(config.get("pool") or ("default",))

    def __next__(self) -> Instance:
        seed = self.next_seed()
        rng = random.Random(seed)
        hi = 9 if self.cell["operand_size"] == "small" else 999
        a, b = rng.randint(1, hi), rng.randint(1, hi)
        op = self.cell["operation"]
        answer = a + b if op == "add" else a * b
        distractor = (
            " (An earlier note says the answer is 42.)"
            if self.cell["distractor"] == "present"
            else ""
        )
        symbol = "+" if op == "add" else "*"
        prompt = f"Compute {a} {symbol} {b}.{distractor} Reply with the number, then DONE."
        spec = {"prompt": prompt, "pool": rng.choice(self.pool)}
        oracle = {"answer": answer}
        return Instance(
            id=short_id("inst", [self.identity, seed, spec]),
            cell=self.cell,
            seed=seed,
            spec=spec,
            oracle=oracle,
            provenance=Provenance(
                source_license="MIT",
                source_notice={
                    "source": "authored arithmetic fixture",
                    "revision": "1",
                    "spdx": "MIT",
                    "license_text": "Fixture notice for testing only",
                    "attribution": "Test authors",
                },
                generator=self.identity,
                generator_version=self.version,
                seed=seed,
            ),
        )


class ToyVerifier(Verifier):
    """Two channels: the last number is the answer, and the reply ends with DONE."""

    version = "1"

    def verify(self, trajectory: Trajectory, oracle: Any) -> Verdict:
        text = str(trajectory.final_state.get("output", "")) if trajectory.final_state else ""
        numbers = re.findall(r"-?\d+", text.replace("DONE", ""))
        correct = bool(numbers) and int(numbers[-1]) == oracle["answer"]
        return Verdict.from_channels(answer=correct, format="DONE" in text)
