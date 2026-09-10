"""The confirmer: runs a candidate region against real held-out data and issues receipts."""

from pydantic import Field

from adversary.confirm.criteria import ConfirmationCriteria
from adversary.confirm.receipt import ConfirmationReceipt, ConfirmedMode
from adversary.core.config import FrozenModel
from adversary.core.factors import Cell, FactorSpace, Grounding
from adversary.core.instance import Instance
from adversary.core.model import LanguageModel
from adversary.domain.contract import RealCorpus
from adversary.execution.harness import Harness
from adversary.probe.evidence import HeldOutRef
from adversary.probe.probe import Probe
from adversary.stats.mobius import MobiusSynergy
from adversary.stats.rates import Comparison, compare_arms


class ConfirmationResult(FrozenModel):
    """Either a mode or the reasons there is none."""

    probe_id: str
    mode: ConfirmedMode | None
    receipt: ConfirmationReceipt | None
    comparison: Comparison | None
    reasons: tuple[str, ...] = Field(default=(), description="Why confirmation failed, if it did")

    @property
    def confirmed(self) -> bool:
        return self.mode is not None


class Confirmer:
    """Real-data gate. Real items are judged by the domain's oracle, not the probe's own check.

    Regions with an ungrounded factor are refused outright. Regions with an attestable factor
    are grade 2 (the perturbation is injected on real items) and admitted only if the criteria
    allow
    grade 2. Everything a receipt says is recomputed from stored episodes.
    """

    def __init__(
        self, harness: Harness, space: FactorSpace, criteria: ConfirmationCriteria | None = None
    ) -> None:
        self.harness = harness
        self.space = space
        self.criteria = criteria or ConfirmationCriteria()

    def _sample(
        self, corpus: RealCorpus, condition: Cell, n: int, seed: int
    ) -> tuple[list[Instance], list[str]]:
        per_source = max(1, n // max(1, len(corpus.sources)))
        items: list[Instance] = []
        used: list[str] = []
        for source in corpus.sources:
            drawn = corpus.sample(condition, per_source, seed, source=source.name)
            if drawn:
                items.extend(drawn)
                used.append(source.name)
        return items, used

    def confirm(
        self,
        probe: Probe,
        corpus: RealCorpus,
        model: LanguageModel,
        seed: int = 0,
        confirmatory: MobiusSynergy | None = None,
    ) -> ConfirmationResult:
        """Run mode and matched-control items and decide.

        Args:
            probe: The candidate, with a region and a minimal pair.
            corpus: Real held-out items.
            model: The target.
            seed: Sampling seed.
            confirmatory: The rate-scale Möbius synergy from the branch design (Amendment A5),
                when the criteria require it.
        """
        condition = probe.cell
        grade = self.space.grade(condition)
        if grade is None:
            ungrounded = sorted(
                f
                for f, g in self.space.grounding_of(condition).items()
                if g is Grounding.UNGROUNDED
            )
            return ConfirmationResult(
                probe_id=probe.id,
                mode=None,
                receipt=None,
                comparison=None,
                reasons=(
                    f"region uses factors with no real-data grounding: {ungrounded}; "
                    "swept, never claimable",
                ),
            )
        if grade > self.criteria.max_grade:
            return ConfirmationResult(
                probe_id=probe.id,
                mode=None,
                receipt=None,
                comparison=None,
                reasons=(
                    f"region is grade {grade}; criteria admit at most grade "
                    f"{self.criteria.max_grade}",
                ),
            )
        control_condition = probe.pair.control.project(probe.cell.factors)
        mode_items, sources = self._sample(corpus, condition, self.criteria.min_items, seed)
        control_items, _ = self._sample(
            corpus, control_condition, self.criteria.min_items, seed + 1
        )
        if not mode_items or not control_items:
            return ConfirmationResult(
                probe_id=probe.id,
                mode=None,
                receipt=None,
                comparison=None,
                reasons=("corpus returned no items for the condition",),
            )
        mode_run = self.harness.run(mode_items, model, probe_id=probe.id, arm="real_mode")
        control_run = self.harness.run(control_items, model, probe_id=probe.id, arm="real_control")
        if not mode_run.measurable or not control_run.measurable:
            return ConfirmationResult(
                probe_id=probe.id,
                mode=None,
                receipt=None,
                comparison=None,
                reasons=("both arms require measurable episodes",),
            )
        comparison = compare_arms(
            control_run.episodes, mode_run.episodes, alpha=self.criteria.alpha
        )
        receipt = ConfirmationReceipt.issue(
            probe_id=probe.id,
            condition=condition,
            grounding=self.space.grounding_of(condition),
            grade=grade,
            corpus_fingerprint=corpus.fingerprint(),
            sources=tuple(sources),
            n_mode=len(mode_run.measurable),
            mode_success=1.0 - mode_run.failure_rate,
            n_control=len(control_run.measurable),
            control_success=1.0 - control_run.failure_rate,
            p_value=comparison.p_value,
            confirmatory_excess_points=confirmatory.synergy_points if confirmatory else None,
            episode_ids=mode_run.episode_ids + control_run.episode_ids,
            store_digest=self.harness.store.digest(),
            criteria=self.criteria,
        )
        problems = receipt.meets()
        if problems:
            return ConfirmationResult(
                probe_id=probe.id,
                mode=None,
                receipt=receipt,
                comparison=comparison,
                reasons=tuple(problems),
            )
        held_out = HeldOutRef(
            corpus_fingerprint=corpus.fingerprint(),
            sources=tuple(sources),
            condition=condition,
            n=len(mode_run.measurable),
        )
        mode = ConfirmedMode(probe=probe.with_(held_out=held_out), receipt=receipt)
        return ConfirmationResult(
            probe_id=probe.id, mode=mode, receipt=receipt, comparison=comparison
        )
