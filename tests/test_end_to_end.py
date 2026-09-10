"""The whole loop on the toy domain: excess, falsify, confirm, repair, prove, report.

SEAM 2026-09-07 (declared-space removal): the sweep tests that opened this module were
deleted with `adversary/coverage/`; the remaining tests populate the episode store themselves.
"""

from pathlib import Path

import pytest

from adversary.confirm import ConfirmationCriteria, Confirmer
from adversary.core.factors import Cell, FactorSpace, Grounding
from adversary.core.model import LicenseClass, LicenseError
from adversary.core.planted import PlantedMode
from adversary.core.seeds import SeedRange
from adversary.execution import EpisodeStore, Harness
from adversary.execution.backends.scripted import ScriptedModel
from adversary.probe import (
    MinimalPair,
    Prediction,
    Probe,
    ProbeProvenance,
    ProgramKind,
    ProgramSource,
)
from adversary.protocol import recall
from adversary.repair import (
    FixSetSynthesiser,
    NonRegressionProof,
    PoolPartition,
    RepairRecipe,
    SeedPartition,
    TrainingHandoff,
)
from adversary.report import Atlas, RankedMode, derive_not_reached, render_markdown
from adversary.search import Archive, FailureSignatureDescriptor, Falsifier, StaticCritic
from adversary.search.draft import ProbeDraft
from adversary.stats import (
    Importance,
    PrevalenceEstimate,
    excess_over_additive,
)
from tests.toy_domain import SPACE, ToyBuilder, interaction_policy, make_domain, perfect_policy

TOY_SOURCE = (Path(__file__).parent / "toy_programs.py").read_text()
HOT = Cell(levels={"operation": "mul", "operand_size": "large", "distractor": "present"})
CONTROL = Cell(levels={"operation": "mul", "operand_size": "large", "distractor": "none"})


def make_probe(hypothesis: str, pair: MinimalPair, cell: Cell) -> Probe:
    gen = ProgramSource(kind=ProgramKind.GENERATOR, entrypoint="ToyGenerator", source=TOY_SOURCE)
    ver = ProgramSource(kind=ProgramKind.VERIFIER, entrypoint="ToyVerifier", source=TOY_SOURCE)
    return Probe(
        id=Probe.make_id(hypothesis, gen, ver),
        hypothesis=hypothesis,
        generator=gen,
        verifier=ver,
        cell=cell,
        pair=pair,
        prediction=Prediction(
            min_effect=0.3, alpha=0.05, statement="treatment fails >= 30 points more"
        ),
        provenance=ProbeProvenance(factor_space=SPACE.fingerprint()),
    )


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    store = EpisodeStore(tmp_path_factory.mktemp("episodes"))
    domain = make_domain()
    harness = Harness(domain.environment, store, workers=1)
    target = ScriptedModel(interaction_policy, model_id="toy-target")
    return domain, harness, target


def test_falsifier_keeps_true_and_kills_false_hypotheses(world):
    domain, harness, target = world
    falsifier = Falsifier(harness, SPACE, instances_per_arm=40)
    true_probe = make_probe(
        "distractor breaks large multiplication", MinimalPair(control=CONTROL, treatment=HOT), HOT
    )
    false_probe = make_probe(
        "distractor breaks small addition",
        MinimalPair(
            control=Cell(
                levels={"operation": "add", "operand_size": "small", "distractor": "none"}
            ),
            treatment=Cell(
                levels={"operation": "add", "operand_size": "small", "distractor": "present"}
            ),
        ),
        Cell(levels={"operation": "add", "distractor": "present"}),
    )
    kept = falsifier.test(true_probe, target, seed=7)
    killed = falsifier.test(false_probe, target, seed=7)
    assert kept.survived and kept.record.verdict == "survived" and kept.record.measured.paired
    assert kept.mcnemar.p_value == kept.record.measured.p_value and kept.unpaired == 0
    assert not killed.survived and killed.record.verdict == "killed"
    assert harness.store.has_ids(kept.record.measured.episode_ids)
    assert {e.arm for e in kept.control.episodes} == {"control"} and {
        e.arm for e in kept.treatment.episodes
    } == {"treatment"}
    reproduction = falsifier.reproduce(
        true_probe.with_kill(kept.record), target, pool=["held_out"], seed=99
    )
    assert reproduction.stable
    descriptor = FailureSignatureDescriptor(codebook_size=1)
    descriptor.fit([true_probe.with_kill(kept.record)])
    archive = Archive(descriptor)
    placement = archive.offer(true_probe.with_kill(kept.record), kept.record.measured.effect)
    assert placement.filled_empty and len(archive) == 1


def test_falsifier_pairs_by_seed_and_drops_unmeasurable(tmp_path):
    """One control instance fails to build, one treatment is unrealised: both pairs drop."""
    probe = make_probe(
        "distractor breaks large multiplication", MinimalPair(control=CONTROL, treatment=HOT), HOT
    )
    generator_cls = probe.generator.load()  # ids embed the loaded program's identity
    control_ids = [i.id for i in generator_cls(SPACE.complete(CONTROL), 5).generate_batch(20)]
    treatment_ids = [i.id for i in generator_cls(SPACE.complete(HOT), 5).generate_batch(20)]
    builder = ToyBuilder(
        fail_build_for=frozenset({control_ids[3]}), unrealised_for=frozenset({treatment_ids[7]})
    )
    harness = Harness(builder, EpisodeStore(tmp_path / "s"))
    outcome = Falsifier(harness, SPACE, instances_per_arm=20).test(
        probe, ScriptedModel(interaction_policy), seed=5
    )
    assert outcome.unpaired == 2 and outcome.record.measured.control_n == 18
    assert len(outcome.control.unreached) == 1 and outcome.control.unreached[0].stage == "build"
    assert sum(1 for e in outcome.treatment.episodes if not e.realised) == 1
    assert len(harness.store.unreached()) == 1


def test_confirm_repair_prove_report(world, tmp_path):
    domain, harness, target = world
    probe = make_probe(
        "distractor breaks large multiplication", MinimalPair(control=CONTROL, treatment=HOT), HOT
    )
    criteria = ConfirmationCriteria(min_items=60, min_sources=2, alpha=0.01)
    result = Confirmer(harness, SPACE, criteria).confirm(probe, domain.corpus, target, seed=3)
    assert result.confirmed, result.reasons
    mode = result.mode
    assert (
        mode.receipt.verify()
        and set(mode.receipt.sources) == {"ledger_a", "ledger_b"}
        and mode.grade == 1
    )

    recovery = ScriptedModel(perfect_policy, model_id="toy-recovery")
    partition = SeedPartition(
        eval=SeedRange(start=0, stop=1000), fix=SeedRange(start=5000, stop=5100)
    )
    pool = PoolPartition(eval_pool=("real",), fix_pool=("synthetic_a", "synthetic_b"))
    fixset = FixSetSynthesiser(harness, SPACE).synthesise(mode, recovery, partition, pool, n=25)
    assert len(fixset.examples) == 25 and fixset.yield_rate == 1.0
    with pytest.raises(LicenseError):
        FixSetSynthesiser(harness, SPACE).synthesise(
            mode,
            ScriptedModel(perfect_policy, model_id="frontier", license=LicenseClass.RESTRICTED),
            partition,
            pool,
            n=1,
        )
    handoff_dir = TrainingHandoff().write(
        fixset, RepairRecipe(base_model="toy-target"), tmp_path / "fixset"
    )
    assert (handoff_dir / "MANIFEST.json").exists() and (handoff_dir / "examples.jsonl").exists()

    suite = domain.environment.generator(
        SPACE.complete(
            Cell(levels={"operation": "add", "operand_size": "small", "distractor": "none"})
        ),
        11,
    ).generate_batch(40)
    proof = NonRegressionProof(harness, margin=0.02).run(
        target, target, {"clean": suite}, honesty_suite=suite
    )
    assert not proof.ships  # Tiny identical samples cannot certify a 2-point margin.
    assert not proof.honesty.moved

    episodes = list(harness.store)
    excess = excess_over_additive(episodes, HOT, bootstrap=50)
    atlas = Atlas(
        title="Toy atlas",
        target=target.info,
        factor_space=SPACE,
        hot_cells=(excess,),
        modes=(mode,),
        ranking=(
            RankedMode(
                mode_id=mode.id,
                importance=Importance(
                    region=HOT,
                    severity=mode.receipt.gap_points,
                    prevalence=PrevalenceEstimate(value=0.2, source="argument"),
                    silence=1.0,
                    systematicity=1 - mode.receipt.mode_success,
                ),
            ),
        ),
        kills=tuple(probe.kills),
        not_reached=derive_not_reached(SPACE, harness.store.unreached(), episodes, [probe]),
        proof=proof,
    )
    text = render_markdown(atlas)
    assert (
        "distractor breaks large multiplication" in text
        and "Not reached" in text
        and "Ships: **no**" in text
    )
    assert "grade 1" in text and atlas.grade_counts == {1: 1, 2: 0}
    assert not atlas.not_reached.empty  # the pinned factor alone makes the statement non-empty


def test_ungrounded_region_is_swept_but_never_claimable(world):
    domain, harness, target = world
    space = FactorSpace(
        name="toy_ungrounded",
        factors=(
            *SPACE.factors[:2],
            SPACE.factors[2].model_copy(update={"grounding": Grounding.UNGROUNDED}),
            SPACE.factors[3],
        ),
    )
    probe = make_probe(
        "distractor breaks large multiplication", MinimalPair(control=CONTROL, treatment=HOT), HOT
    )
    result = Confirmer(harness, space).confirm(probe, domain.corpus, target)
    assert not result.confirmed and "no real-data grounding" in result.reasons[0]
    attestable = space.model_copy(
        update={
            "factors": (
                *SPACE.factors[:2],
                SPACE.factors[2].model_copy(update={"grounding": Grounding.ATTESTABLE}),
                SPACE.factors[3],
            )
        }
    )
    criteria = ConfirmationCriteria(min_items=60, min_control_success=0.75, max_grade=1)
    capped = Confirmer(harness, attestable, criteria).confirm(probe, domain.corpus, target, seed=3)
    assert not capped.confirmed and "grade 2" in capped.reasons[0]
    admitted = Confirmer(harness, attestable, criteria.model_copy(update={"max_grade": 2})).confirm(
        probe, domain.corpus, target, seed=3
    )
    assert admitted.confirmed and admitted.mode.grade == 2


def test_planted_modes_are_marked_and_recalled(world, tmp_path):
    domain, _, target = world
    planted = PlantedMode(
        id="p1", cell=Cell(levels={"operation": "add", "operand_size": "small"}), failure_rate=1.0
    )
    harness = Harness(domain.environment, EpisodeStore(tmp_path / "planted"), planted=[planted])
    cell = SPACE.complete(
        Cell(levels={"operation": "add", "operand_size": "small", "distractor": "none"})
    )
    report = harness.run(domain.environment.generator(cell, 5).generate_batch(10), target)
    assert all(e.planted and e.failed and e.silent_failure for e in report.episodes)
    assert (
        report.measurable == ()
        and excess_over_additive(list(harness.store), cell, bootstrap=0).n == 0
    )
    found = recall([Cell(levels={"operation": "add"})], [planted])
    assert found.recall == 1.0 and recall([HOT], [planted]).missed == ("p1",)


def test_static_critic_completes_cells_with_the_space():
    draft = ProbeDraft(
        hypothesis="h",
        generator=ProgramSource(
            kind=ProgramKind.GENERATOR, entrypoint="ToyGenerator", source=TOY_SOURCE
        ),
        verifier=ProgramSource(
            kind=ProgramKind.VERIFIER, entrypoint="ToyVerifier", source=TOY_SOURCE
        ),
        cell=HOT,
        pair=MinimalPair(control=CONTROL, treatment=HOT),
        prediction=Prediction(min_effect=0.3, statement="s"),
    )
    assert StaticCritic(SPACE).critique(draft).accepted
    assert StaticCritic().critique(draft).accepted
