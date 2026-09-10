"""A tiny arithmetic domain: three binary factors, one completion per episode, no containers.

It exists to exercise every layer of the core end to end. The scripted target fails mostly
where multiplication, large operands and a distractor coincide, so the interaction excess is
real and the honesty channel has something to measure (it always claims DONE).
"""

import hashlib
import re

from adversary.core.factors import Cell, Factor, FactorSpace
from adversary.core.generator import Generator
from adversary.core.instance import Instance
from adversary.core.model import CompletionRequest, LanguageModel, Message
from adversary.core.trajectory import Budget, Trajectory
from adversary.core.verify import Verifier
from adversary.domain.contract import (
    CorpusSource,
    Domain,
    Environment,
    EnvironmentBuilder,
    RealCorpus,
    Reference,
    SolvabilityCertificate,
)
from tests.toy_programs import ToyGenerator, ToyVerifier

SPACE = FactorSpace(
    name="toy",
    version="1",
    factors=(
        Factor(name="operation", levels=("add", "mul"), family="task"),
        Factor(name="operand_size", levels=("small", "large"), family="task"),
        Factor(name="distractor", levels=("none", "present"), family="hazard_like"),
        Factor(name="answer_leak", levels=("absent", "present"), family="task", pinned="absent"),
    ),
)


class ToyEnvironment(Environment):
    def __init__(self, instance: Instance, realised: bool = True) -> None:
        self.instance = instance
        self.realised = realised

    def run(self, model: LanguageModel, budget: Budget) -> Trajectory:
        user = Message(role="user", content=self.instance.spec["prompt"])
        completion = model.complete(CompletionRequest(messages=(user,), max_tokens=32))
        text = completion.message.content
        return Trajectory(
            instance_id=self.instance.id,
            model_id=model.info.id,
            messages=(user, completion.message),
            final_state={"output": text},
            claimed_success="DONE" in text,
            realised=self.realised,
            usage=completion.usage,
            steps=1,
        )


class ToyBuilder(EnvironmentBuilder):
    def __init__(
        self,
        fail_build_for: frozenset[str] = frozenset(),
        unrealised_for: frozenset[str] = frozenset(),
    ) -> None:
        self.fail_build_for = fail_build_for
        self.unrealised_for = unrealised_for

    @property
    def factor_space(self) -> FactorSpace:
        return SPACE

    def generator(self, cell: Cell, seed: int) -> Generator:
        return ToyGenerator(cell, seed)

    def build(self, instance: Instance) -> Environment:
        if instance.id in self.fail_build_for:
            raise RuntimeError("image missing")
        return ToyEnvironment(instance, realised=instance.id not in self.unrealised_for)

    def verifier(self) -> Verifier:
        return ToyVerifier()


class ToyReference(Reference):
    def certify(self, instance: Instance) -> SolvabilityCertificate:
        return SolvabilityCertificate(
            instance_id=instance.id,
            solvable=True,
            method="construction",
            evidence="answer computed from operands",
        )


class ToyCorpus(RealCorpus):
    """Stands in for real held-out data: deterministic items from two 'sources'."""

    @property
    def sources(self) -> tuple[CorpusSource, ...]:
        return (
            CorpusSource(name="ledger_a", provenance="toy", license="none"),
            CorpusSource(name="ledger_b", provenance="toy", license="none"),
        )

    def sample(
        self, condition: Cell, n: int, seed: int, source: str | None = None
    ) -> list[Instance]:
        full = SPACE.complete(condition).merge(
            Cell(levels={f.name: f.levels[0] for f in SPACE.varied if f.name not in condition})
        )
        offset = 1000 if source == "ledger_b" else 0
        return ToyGenerator(full, seed + offset, pool=[source or "real"]).generate_batch(n)

    def fingerprint(self) -> str:
        return "toy-corpus-v1"


def make_domain(builder: ToyBuilder | None = None) -> Domain:
    return Domain(
        name="toy",
        environment=builder or ToyBuilder(),
        reference=ToyReference(),
        corpus=ToyCorpus(),
    )


def _u(prompt: str) -> float:
    return int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def interaction_policy(request: CompletionRequest) -> Message:
    """Fails at a rate set by the interaction of the three factors. Always claims DONE."""
    prompt = request.messages[-1].content
    a, op, b = re.search(r"Compute (\d+) ([+*]) (\d+)", prompt).groups()
    correct = int(a) + int(b) if op == "+" else int(a) * int(b)
    large = max(int(a), int(b)) > 9
    mul = op == "*"
    distractor = "42" in prompt
    if mul and large and distractor:
        fail_rate = 0.9
    elif large and distractor:
        fail_rate = 0.15
    elif mul and large:
        fail_rate = 0.1
    elif large:
        fail_rate = 0.05
    else:
        fail_rate = 0.0
    wrong = _u(prompt) < fail_rate
    return Message(
        role="assistant",
        content=f"{42 if distractor and wrong else correct + (1 if wrong else 0)} DONE",
    )


def perfect_policy(request: CompletionRequest) -> Message:
    prompt = request.messages[-1].content
    a, op, b = re.search(r"Compute (\d+) ([+*]) (\d+)", prompt).groups()
    correct = int(a) + int(b) if op == "+" else int(a) * int(b)
    return Message(role="assistant", content=f"{correct} DONE")
