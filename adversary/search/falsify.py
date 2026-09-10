"""The falsifier: runs the minimal pair and writes the kill record from measured outcomes.

This is the controller of architecture F. Given a probe with a committed prediction, it runs
both arms through the harness with the same seed so everything but the isolated factor is
held fixed. The i-th instance of each arm is drawn from the same generator seed, so arms are
paired by instance seed and the paired test is McNemar's; the effect and its interval come
from a paired bootstrap. Only measurable episodes (realised, not planted) enter the pairing.
The verdict is whatever the numbers say.

:meth:`Falsifier.reproduce` is Split A: fresh instances from the probe against a held-out
resource pool, to check the probe defines a stable population rather than a compressed dataset.
"""

from collections.abc import Sequence

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.factors import FactorSpace
from adversary.core.model import LanguageModel
from adversary.core.util import short_id
from adversary.execution.harness import Harness, RunReport
from adversary.probe.kill import KillRecord, MeasuredOutcome
from adversary.probe.probe import Probe
from adversary.stats.equivalence import (
    BootstrapResult,
    McNemarResult,
    mcnemar_test,
    paired_bootstrap,
)
from adversary.stats.rates import RateEstimate, rate_estimate


class FalsificationOutcome(FrozenModel):
    """The record plus the raw arms."""

    record: KillRecord
    mcnemar: McNemarResult
    bootstrap: BootstrapResult
    control: RunReport
    treatment: RunReport
    unpaired: int = Field(
        description="Episodes in one arm with no measurable counterpart in the other; dropped"
    )

    @property
    def survived(self) -> bool:
        return self.record.verdict == "survived"


class Reproduction(FrozenModel):
    """Split A: does the probe reproduce its failure rate on fresh instances from a new pool?"""

    probe_id: str
    original: RateEstimate = Field(description="Treatment-arm failure rate from the falsification")
    fresh: RateEstimate = Field(
        description="Failure rate on fresh instances from the held-out pool"
    )
    tolerance_points: float

    @property
    def difference_points(self) -> float:
        return 100.0 * (self.fresh.rate - self.original.rate)

    @property
    def stable(self) -> bool:
        return abs(self.difference_points) <= self.tolerance_points


class Falsifier:
    """Runs minimal pairs."""

    def __init__(
        self,
        harness: Harness,
        space: FactorSpace,
        instances_per_arm: int = 20,
        resamples: int = 2000,
    ) -> None:
        self.harness = harness
        self.space = space
        self.instances_per_arm = instances_per_arm
        self.resamples = resamples

    def _arm(
        self,
        probe: Probe,
        arm: str,
        model: LanguageModel,
        seed: int,
        pool: Sequence[str] | None = None,
    ) -> RunReport:
        if probe.perturbation is not None:
            raise RuntimeError(
                "v2 falsification refused: the runner cannot bind and confine the third program"
            )
        cell = self.space.complete(probe.pair.control if arm == "control" else probe.pair.treatment)
        if not self.space.is_full(cell):
            raise ValueError(f"{arm} arm is not a full configuration: {cell.label()}")
        config = {"pool": list(pool)} if pool is not None else {}
        generator = probe.generator.load()(cell, seed=seed, **config)
        verifier = probe.verifier.load()()
        return self.harness.run(
            generator.generate_batch(self.instances_per_arm),
            model,
            verifier=verifier,
            probe_id=probe.id,
            arm=arm,
        )

    def test(self, probe: Probe, model: LanguageModel, seed: int) -> FalsificationOutcome:
        """Run both arms of ``probe.pair`` against ``model`` and record the outcome.

        Args:
            probe: Must carry loadable programs and a full-configuration pair.
            model: The target.
            seed: Shared generator seed for both arms, which is what pairs them.
        """
        control = self._arm(probe, "control", model, seed)
        treatment = self._arm(probe, "treatment", model, seed)
        by_seed_control = {e.seed: e for e in control.measurable}
        by_seed_treatment = {e.seed: e for e in treatment.measurable}
        shared = sorted(set(by_seed_control) & set(by_seed_treatment))
        if not shared:
            raise RuntimeError("no instance seed has a measurable episode in both arms")
        unpaired = len(by_seed_control) + len(by_seed_treatment) - 2 * len(shared)
        control_failed = [by_seed_control[s].failed for s in shared]
        treatment_failed = [by_seed_treatment[s].failed for s in shared]
        mcnemar = mcnemar_test([not f for f in control_failed], [not f for f in treatment_failed])
        boot = paired_bootstrap(
            [float(f) for f in control_failed],
            [float(f) for f in treatment_failed],
            resamples=self.resamples,
            seed=seed,
        )
        episode_ids = tuple(by_seed_control[s].id for s in shared) + tuple(
            by_seed_treatment[s].id for s in shared
        )
        measured = MeasuredOutcome.from_paired(
            control_failed,
            treatment_failed,
            mcnemar,
            boot,
            episode_ids,
            self.harness.store.digest(),
        )
        record = KillRecord(
            id=short_id("kill", [probe.id, measured.episode_ids]),
            hypothesis=probe.hypothesis,
            pair=probe.pair,
            prediction=probe.prediction,
            measured=measured,
            verdict=KillRecord.verdict_for(measured, probe.prediction),
        )
        return FalsificationOutcome(
            record=record,
            mcnemar=mcnemar,
            bootstrap=boot,
            control=control,
            treatment=treatment,
            unpaired=unpaired,
        )

    def reproduce(
        self,
        probe: Probe,
        model: LanguageModel,
        pool: Sequence[str],
        seed: int,
        tolerance_points: float = 10.0,
    ) -> Reproduction:
        """Split A: fresh treatment-arm instances from a held-out ``pool``."""
        if not probe.kills:
            raise ValueError("reproduce() needs a falsified probe; run test() first")
        latest = probe.kills[-1].measured
        fresh = self._arm(probe, "treatment", model, seed, pool=pool)
        rows = fresh.measurable
        return Reproduction(
            probe_id=probe.id,
            original=rate_estimate(latest.treatment_failures, latest.treatment_n),
            fresh=rate_estimate(sum(1 for e in rows if e.failed), len(rows)),
            tolerance_points=tolerance_points,
        )
