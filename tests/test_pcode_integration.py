import pytest

from adversary.confirm.recall import FrozenPredicates, measure_recall
from adversary.core.factors import Cell
from adversary.core.instance import Instance, Provenance
from adversary.domain.contract import CorpusSource
from adversary.stats.equivalence import paired_binary_equivalence
from adversary.stats.footprint import FootprintTable, adjusted_rand, jaccard, partitions
from adversary.stats.mobius import mobius_synergy
from adversary.stats.recall import TaskOutcome, clopper_pearson, outcome_recall
from domains.swe_agents.corpus.real import SweRealCorpus


def item(name, levels):
    return Instance(
        id=name,
        cell=Cell(levels=levels),
        seed=1,
        spec={},
        oracle={},
        provenance=Provenance(generator="fixture", generator_version="1", seed=1),
    )


def test_corpus_samples_observed_cells_without_replacement_and_freezes_bytes():
    first = item("a", {"x": "yes", "y": "unknown"})
    corpus = SweRealCorpus(
        sources=(CorpusSource(name="source", provenance="fixture", license="MIT"),),
        items={"source": (first, item("b", {}))},
    )
    fingerprint = corpus.fingerprint()
    first.cell.levels["x"] = "no"
    draw = corpus.sample(Cell(levels={"x": "yes"}), 20, 0)
    assert [i.id for i in draw] == ["a"]
    assert corpus.fingerprint() == fingerprint
    assert corpus.sample(Cell(levels={"unobserved": "yes"}), 10, 0) == []
    with pytest.raises(ValueError):
        corpus.sample(Cell(levels={}), 1, 0, "missing")


def test_identical_small_samples_do_not_prove_equivalence():
    result = paired_binary_equivalence([True] * 5, [True] * 5)
    assert not result.equivalent and result.ci_low < -0.02 and result.ci_high > 0.02
    large = paired_binary_equivalence([True] * 1000, [True] * 1000)
    assert large.equivalent
    clustered = paired_binary_equivalence([True] * 1000, [True] * 1000, clusters=["same"] * 1000)
    assert not clustered.equivalent and clustered.n == 1


def test_clause_stage_arm_gaming_cannot_print_excess_without_audit():
    rates = {
        frozenset(): 0.1,
        frozenset({"stage"}): 0.1,
        frozenset({"arm"}): 0.1,
        frozenset({"stage", "arm"}): 0.7,
    }
    with pytest.raises(ValueError, match="clause-declaration"):
        mobius_synergy(("stage", "arm"), rates)


def test_d11_unknowns_and_zero_denominators():
    rows = [
        TaskOutcome(task_id="a", resource="a", passed=(False,) * 5),
        TaskOutcome(task_id="b", resource="b", passed=(True, True, False, False, False)),
        TaskOutcome(task_id="c", resource="c", passed=(None, False, False, False, False)),
    ]
    result = outcome_recall(rows, [True, False, True], iid_tasks=True, resamples=10)
    assert result.failures == 1 and result.zero_pass_tasks == 1 and result.unresolved_tasks == 1
    assert result.recall == 1 and result.severity_recall == pytest.approx(1 / 1.6)
    assert outcome_recall([], []).recall is None
    assert clopper_pearson(0, 5)[1] > 0.5


def test_predicates_sealed_before_measurement_cannot_be_changed(tmp_path):
    frozen = FrozenPredicates(
        target_pin="a" * 64,
        corpus_digest="b" * 64,
        predicates={"mode": Cell(levels={"x": "yes"})},
        main_n=1,
    )
    path = tmp_path / "seal.json"
    digest = frozen.seal(path)
    result = measure_recall(
        frozen,
        path,
        digest,
        [item("a", {"x": "yes"})],
        [TaskOutcome(task_id="a", resource="a", passed=(False,) * 5)],
    )
    assert result.recall == 1
    changed = frozen.model_copy(update={"predicates": {}})
    with pytest.raises(ValueError, match="sealing"):
        changed.assert_sealed(path, digest)
    with pytest.raises(FileExistsError):
        frozen.seal(path)


def test_footprint_unknown_and_shared_resampling():
    assert jaccard([False], [False]) is None
    assert jaccard([True, None], [True, False]) is None
    assert adjusted_rand(["a", "a", "b"], ["x", "x", "y"]) == 1
    assert partitions(["a", "b", "c"], [("a", "b"), ("b", "c")]) == (("a", "b", "c"),)
    table = FootprintTable(
        corpus_digest="c",
        target_pin="p",
        task_ids=("a", "b"),
        resources=("a", "b"),
        values={"x": (True, False), "y": (True, False)},
        grades={"x": 1, "y": 1},
    )
    draw = table.resample(4)
    assert draw.values["x"] == draw.values["y"]


def test_operator_queue_consumes_decisions_once():
    from adversary.search.admission import AdmissionEvidence, CandidateOperator, OperatorRegister
    from adversary.search.context import MinedSeed
    from tests.test_observation import program

    register = OperatorRegister()
    candidate = CandidateOperator(
        id="one",
        program=program("return result"),
        seed=MinedSeed(
            instance_id="task",
            repo="owner/name",
            base_commit="a" * 40,
            sha="b" * 40,
            miner="history",
            ts=1,
            subject="fix",
        ),
    )
    register.nominate(candidate)
    register.admit(
        "one",
        AdmissionEvidence(
            policy_digest="c" * 64,
            singleton_receipt="d" * 64,
            channel_receipt="e" * 64,
            effect_receipt="f" * 64,
        ),
    )
    assert register.version == 1 and len(register.fingerprint()) == 64
    with pytest.raises(ValueError):
        register.nominate(candidate)


def test_bounded_selection_retains_indices_and_records_frozen_batch(tmp_path):
    from adversary.core.util import sha256_json
    from adversary.execution.store import EpisodeStore
    from adversary.search.archive import EpochManifest, capped_release
    from adversary.search.context import SearchContext
    from adversary.search.loop import run_frozen_epoch

    context = SearchContext()
    epoch = EpochManifest(
        proposer_pin="p",
        context_digest=sha256_json(context.model_dump(mode="json")),
        generator_checker_digest="g",
        target_pin="t",
        admission_policy_digest="a",
        score_policy_digest="s",
        m=3,
        rho=0.5,
    )
    release = capped_release(epoch, ["same"] * 3, [1, 3, 3], 8)
    assert release.retained_indices == (1, 2) and release.cap == 1.5
    assert release.audited_risk_bound is None
    store = EpisodeStore(tmp_path)
    measured = run_frozen_epoch(
        epoch,
        context,
        [item(str(i), {}) for i in range(3)],
        lambda instance: float(instance.id),
        store,
        3,
    )
    assert measured.released_index in (1, 2)
    assert (tmp_path / "epochs.jsonl").exists()
    with pytest.raises(ValueError, match="incomplete"):
        run_frozen_epoch(epoch, context, [], lambda instance: 1.0, store, 3)


def test_point_matching_uses_call_arguments_and_occurrence_on_failed_trace():
    from adversary.core.model import Message, ToolCall
    from adversary.core.trajectory import Trajectory
    from domains.swe_agents.environment.points import derive_points, eligible_kinds

    call = ToolCall(id="x", name="read_file", arguments={"path": "a.py"})
    trace = Trajectory(
        instance_id="i",
        model_id="m",
        error="failed clean run",
        messages=(Message(role="assistant", content="", tool_calls=(call, call)),),
    )
    points = derive_points(trace, task_pin="task", target_pin="target")
    assert len(points) == 2 and points[1].occurrence == 2
    assert points[1].matches(call, 2) and not points[1].matches(call, 1)
    assert not points[1].matches(call.model_copy(update={"arguments": {"path": "b.py"}}), 2)
    assert eligible_kinds(points[0], {}) == ()


def test_scale_screen_withholds_uninformative_fit():
    from adversary.stats.scales import difficulty_strata, scale_report, sign_class

    result = scale_report({"a": [(0, 5)] * 4})
    assert result["rate_contrast"] == 0 and result["logit"]["informative_tasks"] == 0
    assert result["logit"]["coefficient"] is None
    assert difficulty_strata({"a": 0.2, "b": 0.8}, [0.5]) == {"a": 0, "b": 1}
    assert sign_class(-0.1, 0.5) == "uncertain"


def test_ledger_transfer_overrides_footprints_and_new_pin_requires_confirmation():
    from adversary.confirm.ledger import ModeLedger
    from adversary.confirm.receipt import ConfirmedMode
    from adversary.core.episode import Episode
    from adversary.core.verify import Verdict
    from adversary.stats.footprint import TransferMatrix
    from tests.test_confirm_gate import receipt
    from tests.test_probe import make_probe

    probe = make_probe()
    mode = ConfirmedMode(probe=probe, receipt=receipt(probe.id))
    ledger = ModeLedger("pin")
    anchors = []
    for ep_id in ("ep_1", "ep_2"):
        probe = make_probe().with_(id="probe-" + ep_id)
        mode = ConfirmedMode(probe=probe, receipt=receipt(probe.id))
        ep = Episode(
            id=ep_id,
            instance_id=ep_id,
            cell=probe.cell,
            seed=0,
            model_id="m",
            target_pin="pin",
            probe_id=probe.id,
            verdict=Verdict(passed=False),
            verifier="v",
        )
        anchors.append(ledger.admit(mode, ep, target_pin="pin"))
        assert ledger.admit(mode, ep, target_pin="pin") == anchors[-1]
    table = FootprintTable(
        corpus_digest="c",
        target_pin="pin",
        task_ids=("t",),
        resources=("r",),
        values={a: (True,) for a in anchors},
        grades={a: 1 for a in anchors},
    )
    ledger.apply_footprints(table, 0.8)
    assert len(ledger.resolve()["components"]) == 1
    matrix = TransferMatrix(
        target_pin="pin",
        modes=tuple(anchors),
        values={a: {b: 0.0 for b in anchors} for a in anchors},
        lower={a: {b: 0.0 for b in anchors} for a in anchors},
        evidence_digest="e",
    )
    ledger.apply_transfer(matrix, 0.5)
    assert len(ledger.resolve()["components"]) == 2
    ledger.record_repair(anchors[0], "a" * 64, "b" * 64)
    assert not ledger.bump("new-pin").entries


def test_grounded_builder_requires_matching_seed_and_verified_pin():
    from adversary.search.admission import OperatorRegister
    from adversary.search.context import MinedSeed
    from domains.swe_agents.environment.builder import SweEnvironmentBuilder
    from domains.swe_agents.environment.generator import TaskPool
    from domains.swe_agents.mining.store import SeedStore
    from tests.test_swe_builder_explicit import setup

    instance, runtime, _ = setup()
    pin = instance.spec.pin.model_copy(
        update={"commit": "a" * 40, "verification_receipt": "b" * 64}
    )
    seed = MinedSeed(
        instance_id=pin.key,
        repo=pin.repo,
        base_commit=pin.commit,
        miner="history",
        sha="c" * 40,
        ts=1,
        subject="fix",
    )
    builder = SweEnvironmentBuilder(
        runtime=runtime,
        pool=TaskPool(pins=(pin,)),
        registry=OperatorRegister(),
        seed_store=SeedStore(records=(seed,), digest="d"),
    )
    context, config = builder.proposal_inputs(pin.key)
    assert context.mined_seed == seed and config["spec"]["pin"]["commit"] == pin.commit
    assert config["oracle"]["test_command"] == pin.test_command and not runtime.calls
    with pytest.raises(ValueError, match="seed"):
        builder.proposal_inputs(pin.key, 1)


def test_transfer_zero_denominator_and_eval_leakage_refuse():
    from adversary.repair.transfer import eval_set, real_diagonal

    outcomes = [TaskOutcome(task_id="t", resource="r", passed=(True,) * 5)]
    assert real_diagonal(outcomes, outcomes, outcomes, 0.05)["gain"] is None
    leaked = item("a", {}).model_copy(update={"resource": "fix"})
    with pytest.raises(ValueError, match="disjoint"):
        eval_set([leaked], ["fix"], [])


def test_target_pin_requires_every_unavailable_field_to_be_explicit():
    from adversary.core.model import PinField, TargetPin

    with pytest.raises(ValueError):
        PinField(status="unpinned")
    with pytest.raises(ValueError):
        TargetPin(model="m")
    field = PinField(status="unpinned", reason="unavailable")
    pin = TargetPin(
        model="m",
        checkpoint=field,
        scaffold=field,
        tool_set=field,
        decoding_policy=field,
        quantisation=field,
        serving_kernel=field,
    )
    assert len(pin.fingerprint()) == 64


def test_unidentified_additive_predictions_are_refused():
    import numpy as np

    from adversary.stats.excess import ExcessUnavailable, _fit_predict

    design = np.array([[1.0, 0.0, 0.0], [1.0, 1.0, 1.0], [1.0, 1.0, 0.0]])
    with pytest.raises(ExcessUnavailable, match="not identified"):
        _fit_predict(
            design,
            np.array([0.0, 1.0, 1.0]),
            np.array([True, True, False]),
            np.array([False, False, True]),
        )


def test_critic_chain_does_not_spend_model_tokens_after_static_rejection():
    from adversary.search.critic import CriticChain, Critique, StaticCritic

    class Reject(StaticCritic):
        def critique(self, draft):
            return Critique(accepted=False, critic="static")

    class Expensive:
        def critique(self, draft):
            raise AssertionError("must not be called")

    assert not CriticChain([Expensive(), Reject()]).critique(None).accepted


def test_grade_footprints_preserve_missing_conditions_and_runs():
    from adversary.confirm.footprint import footprints_from_episodes, measure_injected_footprints

    items = [item("a", {"x": "yes"}), item("b", {})]
    clean = [
        TaskOutcome(task_id="a", resource="a", passed=(False,) * 5),
        TaskOutcome(task_id="b", resource="b", passed=(None,) * 5),
    ]
    table = footprints_from_episodes(
        items, clean, {"m": Cell(levels={"x": "yes"})}, corpus_digest="c", target_pin="p"
    )
    assert table.values["m"] == (True, None) and table.grades["m"] == 1
    injected = measure_injected_footprints(clean, {"m": clean}, corpus_digest="c", target_pin="p")
    assert injected.values["m"] == (False, None) and injected.grades["m"] == 2


def test_transfer_square_preserves_missing_evaluations():
    from adversary.core.util import sha256_json
    from adversary.execution.backends.scripted import ScriptedModel
    from adversary.execution.harness import RunReport
    from adversary.repair.transfer import TransferDesign, measure_transfer

    class MissingHarness:
        def run(self, *args, **kwargs):
            return RunReport(episodes=(), unreached=())

    model = ScriptedModel(lambda request: "ok")
    items = {"one": [item("a", {}).model_copy(update={"resource": "r"})]}
    design = TransferDesign(
        modes=("one",),
        target_pin="a" * 64,
        minimum_base_failure=0.05,
        evaluation_digest=sha256_json({"one": [i.model_dump(mode="json") for i in items["one"]]}),
    )
    matrix = measure_transfer(design, MissingHarness(), model, {"one": [model]}, [model], items)
    assert matrix.values == {"one": {"one": None}}
    assert matrix.lower == {"one": {"one": None}}


def test_finite_source_license_is_required_for_training_handoff(tmp_path):
    from adversary.core.model import LicenseClass, ModelInfo
    from adversary.core.seeds import SeedRange
    from adversary.repair.fixset import FixSet
    from adversary.repair.handoff import RepairRecipe, TrainingHandoff

    fixset = FixSet(
        mode_id="m",
        examples=(),
        seeds=SeedRange(start=1, stop=2),
        pool=(),
        recovery_model=ModelInfo(
            id="m", version="1", license=LicenseClass.PERMISSIVE, backend="fixture"
        ),
        verifier="v",
        attempted=0,
    )
    with pytest.raises(ValueError, match="nonempty"):
        TrainingHandoff().write(fixset, RepairRecipe(base_model="m"), tmp_path / "no-output")
    assert not (tmp_path / "no-output").exists()


def test_pin_freeze_precedes_evidence_and_detects_source_drift(tmp_path, monkeypatch):
    import domains.swe_agents.scripts.pin_contract as contract

    monkeypatch.setattr(contract, "bindings", lambda: {"fixture.py": "a" * 64})
    path = tmp_path / "pin.json"
    pin = contract.mint(path)
    assert pin["measurement"] is None and contract.validate(path) == pin
    monkeypatch.setattr(contract, "bindings", lambda: {"fixture.py": "b" * 64})
    with pytest.raises(ValueError, match="stale"):
        contract.validate(path)


def test_confined_generator_never_receives_hidden_payloads(monkeypatch):
    from adversary.probe.executor import ConfinedPrograms
    from adversary.probe.program import ProgramKind, ProgramSource

    executor = ConfinedPrograms()

    def fake_worker(program, **request):
        config = request["config"]
        assert "secret-answer" not in str(config)
        instance = item("i", {}).model_copy(
            update={
                "spec": config["spec"],
                "oracle": config["oracle"],
                "perturbation_config": {"copied": config["oracle"]},
            }
        )
        return {"instances": [instance.model_dump(mode="json")]}

    monkeypatch.setattr(executor, "_call", fake_worker)
    source = ProgramSource(kind=ProgramKind.GENERATOR, entrypoint="G", source="class G: pass")
    result = executor.generate(
        source,
        Cell(levels={}),
        1,
        {"spec": {"hidden": "secret-answer"}, "oracle": "secret-answer"},
        1,
    )[0]
    assert result.oracle == "secret-answer"
    assert "secret-answer" not in str(result.perturbation_config)
