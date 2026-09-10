"""Explicit task inputs and runtime binding; no deleted envelope or implicit empty pool."""

import re
import shlex
from collections.abc import Callable
from pathlib import Path

from adversary.core.factors import Cell, FactorSpace
from adversary.core.generator import Generator
from adversary.core.instance import Instance
from adversary.core.verify import Verifier
from adversary.domain.contract import Environment, EnvironmentBuilder
from adversary.probe.observation import IsolatedObservation
from adversary.probe.program import ProgramKind
from adversary.search.admission import OperatorRegister
from adversary.search.context import SearchContext
from adversary.search.draft import ProbeDraft
from domains.swe_agents.environment.environment import SweEnvironment
from domains.swe_agents.environment.generator import SweCellGenerator, TaskPool
from domains.swe_agents.environment.gold import digest
from domains.swe_agents.environment.oracle import SweDualOracle
from domains.swe_agents.environment.protected_oracle import FinalOracle
from domains.swe_agents.environment.runtime import ContainerRuntime
from domains.swe_agents.environment.spec import PolicyConstraint, SweOracle, SweTaskSpec
from domains.swe_agents.mining.store import SeedStore


class SweEnvironmentBuilder(EnvironmentBuilder):
    """Bind explicitly supplied trusted pins and a runtime to generated task instances.

    Supplying a pool is a caller trust decision, not evidence of gold verification.
    Receipt-based admission must precede production construction of that pool.
    """

    def __init__(
        self,
        *,
        runtime: ContainerRuntime | None = None,
        pool: TaskPool | None = None,
        factor_space: FactorSpace | None = None,
        generator_factory: Callable[[Cell, int], Generator] | None = None,
        envelope: str | None = None,
        registry: OperatorRegister | None = None,
        seed_store: SeedStore | None = None,
        final_oracle_factory: Callable[[Instance], FinalOracle] | None = None,
        require_protected_oracle: bool = False,
    ) -> None:
        if envelope is not None:
            raise ValueError("envelope files were retired; supply explicit task inputs")
        if runtime is None or pool is None or not pool.pins:
            raise ValueError("an explicit runtime and nonempty trusted task pool are required")
        if len({pin.key for pin in pool.pins}) != len(pool.pins):
            raise ValueError("task pool contains duplicate identifiers")
        self.runtime, self.pool = runtime, pool
        self._space, self._generator_factory = factor_space, generator_factory
        self.registry, self.seed_store = registry, seed_store
        self.final_oracle_factory = final_oracle_factory
        self.require_protected_oracle = require_protected_oracle

    def proposal_inputs(self, task_id: str, seed_index: int = 0) -> tuple[SearchContext, dict]:
        """Bind history, admitted operators, and immutable execution inputs in one place."""
        if self.registry is None or self.seed_store is None:
            raise ValueError("grounded proposal requires explicit registry and mined seed store")
        pin = next((p for p in self.pool.pins if p.key == task_id), None)
        if pin is None:
            raise ValueError("task is absent from the trusted pool")
        if pin.verification_receipt is None:
            raise ValueError("grounded proposal requires a verified task receipt")
        seeds = self.seed_store.matching(pin.key, pin.commit)
        if not seeds or seed_index < 0 or seed_index >= len(seeds):
            raise ValueError("no matching mined seed at this index")
        seed = seeds[seed_index]
        if seed.repo != pin.repo:
            raise ValueError("mined seed and task name differ")
        canary = "pcode-" + pin.key
        spec = SweTaskSpec(pin=pin, canary=canary)
        oracle = SweOracle(
            test_command=pin.test_command,
            fail_to_pass=pin.fail_to_pass,
            pass_to_pass=pin.pass_to_pass,
            gold_patch=pin.gold_patch,
            canary=canary,
        )
        return (
            SearchContext(mined_seed=seed, operator_register=tuple(sorted(self.registry.admitted))),
            {
                "spec": spec.model_dump(mode="json"),
                "oracle": oracle.model_dump(mode="json"),
                "resource": pin.repo,
                "source_license": pin.source_notice.spdx if pin.source_notice else None,
            },
        )

    def materialize(self, draft: ProbeDraft, instance: Instance) -> Instance:
        """Attach the checked program; the generator does not get to rewrite trusted inputs."""
        if draft.seed is None or draft.perturbation is None:
            raise ValueError("materialization requires a grounded draft")
        if draft.perturbation.kind is not ProgramKind.PERTURBATION:
            raise ValueError("materialization requires a perturbation program")
        if self.seed_store is None:
            raise ValueError("materialization requires a mined seed store")
        seeds = self.seed_store.matching(draft.seed.instance_id, draft.seed.base_commit)
        if draft.seed not in seeds:
            raise ValueError("draft seed differs from the frozen harvest")
        _, config = self.proposal_inputs(draft.seed.instance_id, seeds.index(draft.seed))
        spec = SweTaskSpec.model_validate(instance.spec)
        pin = spec.pin
        if (
            spec.model_dump(mode="json") != config["spec"]
            or SweOracle.model_validate(instance.oracle).model_dump(mode="json") != config["oracle"]
            or instance.resource != config["resource"]
            or instance.provenance.source_license != config["source_license"]
        ):
            raise ValueError("generated task differs from its trusted grounded inputs")
        if set(instance.cell.levels) != set(draft.clauses) or any(
            level not in ("on", "off") for level in instance.cell.levels.values()
        ):
            raise ValueError("instance must assign every declared clause on or off")
        spec = spec.model_copy(
            update={
                "perturbation": draft.perturbation,
                "perturbation_clauses": draft.clauses,
                "clause_cell": instance.cell,
            }
        )
        provenance = instance.provenance.model_copy(update={"source_notice": pin.source_notice})
        return Instance.model_validate({**dict(instance), "spec": spec, "provenance": provenance})

    @property
    def factor_space(self) -> FactorSpace:
        if self._space is None:
            raise ValueError("this builder has no declared factor space")
        return self._space

    def pool_constraints(self, strength: int) -> list[Cell]:
        return self.pool.unreachable_patterns(self.factor_space, strength)

    def generator(self, cell: Cell, seed: int) -> Generator:
        if self._generator_factory is not None:
            return self._generator_factory(cell, seed)
        if self._space is None:
            raise ValueError("supply the grounded generator factory explicitly")
        return SweCellGenerator(
            cell, seed, task_pool=self.pool, factor_space_fingerprint=self._space.fingerprint()
        )

    def require_protected(self, instance: Instance) -> None:
        """Ask the trusted oracle implementation to establish its actual capability."""
        if not self.require_protected_oracle or self.final_oracle_factory is None:
            raise ValueError("grounded execution requires a protected final oracle")
        self.final_oracle_factory(instance).require_protected()

    def build(self, instance: Instance) -> Environment:
        spec = SweTaskSpec.model_validate(instance.spec)
        oracle = SweOracle.model_validate(instance.oracle)
        pin = next((p for p in self.pool.pins if p.key == spec.pin.key), None)
        if pin is None or pin != spec.pin:
            raise ValueError("generated task differs from its trusted pool pin")
        if (
            oracle.test_command != pin.test_command
            or oracle.fail_to_pass != pin.fail_to_pass
            or oracle.pass_to_pass != pin.pass_to_pass
            or oracle.gold_patch != pin.gold_patch
        ):
            raise ValueError("generated oracle differs from its trusted pool pin")
        protected = (
            pin.protected_paths if PolicyConstraint.PROTECTED_PATH in spec.constraints else ()
        )
        if (
            oracle.protected_paths != protected
            or oracle.canary != spec.canary
            or oracle.forbid_new_dependencies
            != (PolicyConstraint.NO_NEW_DEPENDENCIES in spec.constraints)
        ):
            raise ValueError("generated oracle differs from the declared task constraints")
        if pin.image_sha256 is not None:
            if pin.image is None or digest(Path(pin.image)) != pin.image_sha256:
                raise ValueError("image differs from verified digest")
        observer = None
        if spec.perturbation is not None:
            observer = IsolatedObservation(
                spec.perturbation,
                spec.perturbation_clauses,
                spec.clause_cell,
                instance.seed,
                instance.perturbation_config,
            )
        elif spec.perturbation_clauses or spec.clause_cell.levels or instance.perturbation_config:
            raise ValueError("intervention data requires a perturbation program")
        session = None
        try:
            options = {}
            if pin.workdir is not None or pin.python_env != "image":
                options = {"workdir": pin.workdir, "python_env": pin.python_env}
            session = self.runtime.start(pin.image, pin.url, pin.commit, **options)
            if pin.test_patch:
                code, path, _ = session.exec("mktemp /tmp/pcode-test-XXXXXXXX.patch", 30)
                path = path.strip()
                if code or not re.fullmatch(r"/tmp/pcode-test-[A-Za-z0-9]+\.patch", path):
                    raise ValueError("could not create trusted test-patch input")
                session.write_file(path, pin.test_patch)
                quoted = shlex.quote(path)
                for command in (
                    "git apply --check " + quoted,
                    "git apply " + quoted,
                    "rm -- " + quoted,
                ):
                    code, _, error = session.exec(command, 60)
                    if code:
                        raise ValueError("trusted test patch setup failed: " + error[-1000:])
                session.checkpoint()
            return SweEnvironment(
                instance.id, spec, oracle, session, observer,
                final_oracle=(self.final_oracle_factory(instance)
                              if self.final_oracle_factory else None),
                require_protected_oracle=self.require_protected_oracle,
            )
        except BaseException:
            if observer is not None:
                observer.close()
            if session is not None:
                session.stop()
            raise

    def verifier(self) -> Verifier:
        return SweDualOracle()
