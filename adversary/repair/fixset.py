"""Synthesising repair data from a confirmed mode.

Instances come from the probe's own generator under the repair seed range and the repair
resource pool, both disjoint from evaluation by :mod:`adversary.repair.partition`. A shippable
recovery model runs them; only trajectories the probe's verifier passes are kept. Restricted
models are refused at the door.
"""

from datetime import datetime

from pydantic import Field

from adversary.confirm.receipt import ConfirmedMode
from adversary.core.config import FrozenModel
from adversary.core.factors import FactorSpace
from adversary.core.instance import Provenance
from adversary.core.model import LanguageModel, LicenseError, Message, ModelInfo
from adversary.core.seeds import SeedRange
from adversary.core.util import utc_now
from adversary.core.verify import Verdict
from adversary.execution.harness import Harness
from adversary.repair.partition import PoolPartition, SeedPartition


class FixExample(FrozenModel):
    """One verified recovery trajectory."""

    episode_id: str
    instance_id: str
    messages: tuple[Message, ...]
    verdict: Verdict
    provenance: Provenance
    model: ModelInfo

    @property
    def shippable(self) -> bool:
        notice = self.provenance.source_notice
        return (
            self.model.shippable
            and notice is not None
            and notice.shippable
            and notice.spdx == self.provenance.source_license
        )


class FixSet(FrozenModel):
    """Verified trajectories for one mode, with everything needed to audit them."""

    mode_id: str
    examples: tuple[FixExample, ...]
    seeds: SeedRange
    pool: tuple[str, ...]
    recovery_model: ModelInfo
    verifier: str
    attempted: int = Field(description="Instances run, including those the verifier rejected")
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def yield_rate(self) -> float:
        return len(self.examples) / self.attempted if self.attempted else 0.0


class FixSetSynthesiser:
    """Turns a confirmed mode into training data."""

    def __init__(self, harness: Harness, space: FactorSpace) -> None:
        self.harness = harness
        self.space = space

    def synthesise(
        self,
        mode: ConfirmedMode,
        recovery_model: LanguageModel,
        partition: SeedPartition,
        pool: PoolPartition,
        n: int,
        batch: int = 20,
    ) -> FixSet:
        """Generate until ``n`` verified examples or the fix seed range is exhausted.

        Raises:
            LicenseError: If ``recovery_model`` is not shippable.
        """
        if not recovery_model.shippable:
            raise LicenseError(
                f"{recovery_model.info.id} is restricted; its trajectories cannot ship"
            )
        if not mode.probe.shippable:
            raise LicenseError("probe lacks redistributable author/source provenance")
        if mode.probe.perturbation is not None:
            raise ValueError("grounded repair requires confined generation and trusted execution")
        generator_cls = mode.probe.generator.load()
        verifier = mode.probe.verifier.load()()
        cell = self.space.complete(mode.probe.pair.treatment)
        examples: list[FixExample] = []
        attempted = 0
        index = 0
        while len(examples) < n and index < len(partition.fix):
            generator = generator_cls(cell, seed=partition.fix.at(index), pool=list(pool.fix_pool))
            instances = generator.generate_batch(min(batch, n - len(examples)))
            report = self.harness.run(
                instances, recovery_model, verifier=verifier, probe_id=mode.id, arm="repair"
            )
            attempted += report.n
            by_id = {i.id: i for i in instances}
            for episode in report.episodes:
                if episode.failed or not episode.measurable:
                    continue
                trajectory = self.harness.store.trajectory(episode.id)
                if trajectory is None:
                    continue
                example = FixExample(
                    episode_id=episode.id,
                    instance_id=episode.instance_id,
                    messages=trajectory.messages,
                    verdict=episode.verdict,
                    provenance=by_id[episode.instance_id].provenance,
                    model=recovery_model.info,
                )
                if not example.shippable:
                    raise LicenseError("repair example lacks allowed source notice and attribution")
                examples.append(example)
            index += 1
        return FixSet(
            mode_id=mode.id,
            examples=tuple(examples),
            seeds=partition.fix,
            pool=pool.fix_pool,
            recovery_model=recovery_model.info,
            verifier=f"{verifier.identity}@{verifier.version}",
            attempted=attempted,
        )
