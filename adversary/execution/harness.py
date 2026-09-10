"""The harness: the only code path that turns a run into an :class:`Episode`.

It builds each instance's environment through the plugin, runs the model, verifies with
code, and records the outcome. An instance that fails at any stage is recorded as
:class:`Unreached` with its stage and never counted as a model failure. Because every
measured number downstream is derived from these rows, the harness is where "the kill log is
written from measured outcomes" is made true.
"""

import time
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.episode import Episode, Stage, Unreached
from adversary.core.instance import Instance
from adversary.core.model import LanguageModel, TargetPin
from adversary.core.planted import PlantedMode
from adversary.core.trajectory import Budget
from adversary.core.util import canonical_json, short_id
from adversary.core.verify import Verdict, Verifier
from adversary.domain.contract import EnvironmentBuilder
from adversary.execution.store import EpisodeStore


class RunReport(FrozenModel):
    """Everything one call to :meth:`Harness.run` produced."""

    episodes: tuple[Episode, ...]
    unreached: tuple[Unreached, ...] = Field(default=(), description="Instances with no episode")

    @property
    def n(self) -> int:
        return len(self.episodes)

    @property
    def measurable(self) -> tuple[Episode, ...]:
        """Episodes that count toward a cell statistic: realised and not planted."""
        return tuple(e for e in self.episodes if e.measurable)

    @property
    def failure_count(self) -> int:
        return sum(1 for e in self.measurable if e.failed)

    @property
    def failure_rate(self) -> float | None:
        rows = self.measurable
        return self.failure_count / len(rows) if rows else None

    @property
    def silent_failure_rate(self) -> float | None:
        rows = self.measurable
        return sum(1 for e in rows if e.silent_failure) / len(rows) if rows else None

    @property
    def episode_ids(self) -> tuple[str, ...]:
        return tuple(e.id for e in self.episodes)


class Harness:
    """Runs instances against a model and records episodes."""

    def __init__(
        self,
        builder: EnvironmentBuilder,
        store: EpisodeStore,
        budget: Budget | None = None,
        workers: int = 1,
        planted: Sequence[PlantedMode] = (),
        target_pin: TargetPin | None = None,
    ) -> None:
        """Initialise the harness.

        Args:
            builder: The plugin's environment builder.
            store: Where episodes are persisted.
            budget: Per-episode limits; defaults to :class:`Budget` defaults.
            workers: Parallel episodes. Environments must be independent of one another and
                the model backend must tolerate concurrent calls (served engines do; a local
                ``transformers`` model does not).
            planted: Known modes to force, for the false-negative audit only. Every affected
                episode is marked ``planted=True``.
        """
        self.target_pin = target_pin.model_copy(deep=True) if target_pin else None
        self.builder = builder
        self.store = store
        self.budget = budget or Budget()
        self.workers = max(1, workers)
        self.planted = tuple(planted)

    def run(
        self,
        instances: Iterable[Instance],
        model: LanguageModel,
        verifier: Verifier | None = None,
        probe_id: str | None = None,
        arm: str | None = None,
    ) -> RunReport:
        """Run every instance and record the outcomes.

        Args:
            instances: Instances to run; each yields one episode or one unreached record.
            model: The model under test.
            verifier: Oracle to apply; defaults to the builder's domain verifier.
            probe_id: Recorded on each episode when the instances came from a probe.
            arm: ``"control"`` or ``"treatment"`` when running a minimal pair.

        Returns:
            The episodes and unreached records, in input order.
        """
        self._validate_target_pin(model)
        oracle = verifier or self.builder.verifier()
        todo = list(instances)
        if self.workers == 1:
            results = [self._one(i, model, oracle, probe_id, arm) for i in todo]
        else:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                results = list(pool.map(lambda i: self._one(i, model, oracle, probe_id, arm), todo))
        return RunReport(
            episodes=tuple(r for r in results if isinstance(r, Episode)),
            unreached=tuple(r for r in results if isinstance(r, Unreached)),
        )

    def _validate_target_pin(self, model: LanguageModel) -> None:
        """Refuse an identity stamp that the active execution configuration cannot support."""
        if self.target_pin is None:
            return
        pin = TargetPin.model_validate(self.target_pin.model_dump(mode="python"))
        if pin.model != model.info.id:
            raise ValueError("model differs from frozen target pin")
        if pin.checkpoint.status == "pinned" and (
            not model.info.version or pin.checkpoint.value != model.info.version
        ):
            raise ValueError("checkpoint differs from frozen target pin or is unavailable")
        bindings = self.builder.pin_bindings(model, self.budget)
        for name in ("scaffold", "tool_set", "decoding_policy", "quantisation", "serving_kernel"):
            field = getattr(pin, name)
            if field.status == "pinned" and (
                name not in bindings
                or canonical_json(bindings[name]) != canonical_json(field.value)
            ):
                raise ValueError(f"target pin {name} differs or has no observed binding")

    def _unreached(self, instance: Instance, stage: Stage, exc: BaseException) -> Unreached:
        record = Unreached(
            instance_id=instance.id, cell=instance.cell, stage=stage, reason=repr(exc)
        )
        self.store.append_unreached(record)
        return record

    def _one(
        self,
        instance: Instance,
        model: LanguageModel,
        verifier: Verifier,
        probe_id: str | None,
        arm: str | None,
    ) -> Episode | Unreached:
        started = time.perf_counter()
        try:
            environment = self.builder.build(instance)
        except Exception as exc:  # noqa: BLE001 - any build error is "not reached"
            return self._unreached(instance, "build", exc)
        build_seconds = time.perf_counter() - started
        try:
            with environment:
                try:
                    trajectory = environment.run(model, self.budget)
                except Exception as exc:  # noqa: BLE001 - a broken run is "not reached"
                    return self._unreached(instance, "run", exc)
                try:
                    verdict = verifier.verify(trajectory, instance.oracle)
                except Exception as exc:  # noqa: BLE001 - a broken verifier is "not reached"
                    return self._unreached(instance, "verify", exc)
        except Exception as exc:  # noqa: BLE001 - environment teardown failed
            return self._unreached(instance, "run", exc)
        claimed = trajectory.claimed_success
        planted = False
        for mode in self.planted:
            if instance.cell.covers(mode.cell) and mode.fires(instance.id):
                verdict = Verdict(passed=False, notes=f"planted:{mode.id}")
                claimed = True if mode.silent else claimed
                planted = True
                break
        episode = Episode(
            id=short_id("ep"),
            instance_id=instance.id,
            cell=instance.cell,
            seed=instance.seed,
            model_id=f"{model.info.id}@{model.info.version}"
            if model.info.version
            else model.info.id,
            probe_id=probe_id,
            target_pin=self.target_pin.fingerprint() if self.target_pin else None,
            arm=arm,
            verdict=verdict,
            claimed_success=claimed,
            verifier=f"{verifier.identity}@{verifier.version}",
            resource=instance.resource,
            usage=trajectory.usage,
            build_seconds=build_seconds,
            truncated=trajectory.truncated,
            realised=trajectory.realised,
            planted=planted,
        )
        self.store.append(episode, trajectory)
        return episode
