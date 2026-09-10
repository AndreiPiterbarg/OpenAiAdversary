"""D10 witnesses fail closed without turning bounded failures into impossibility."""

import pytest

from adversary.core.factors import Cell
from adversary.core.instance import Instance, Provenance
from adversary.domain.contract import SolvabilityCertificate
from adversary.search.referee import Referee
from domains.swe_agents.reference.solver import SweReference
from tests.test_swe_builder_explicit import setup


def certificate(**changes):
    return SolvabilityCertificate(
        **dict(instance_id="i", method="reference_run", clean_passed=True,
               perturbations=("rewrite",), perturbed_runs=3, perturbed_passed=3,
               evidence="test witness", **changes)
    )


def item(identifier="i"):
    return Instance(id=identifier, cell=Cell(levels={}), seed=1, spec={}, oracle={},
                    provenance=Provenance(generator="test", generator_version="1", seed=1))


@pytest.mark.parametrize("field,value", [
    ("perturbed_runs", True), ("perturbed_passed", 1.5), ("required_runs", float("inf")),
    ("required_runs", 0), ("perturbed_runs", "3"), ("clean_passed", "false"),
])
def test_counts_and_clean_result_are_strict(field, value):
    payload = certificate().model_dump()
    payload[field] = value
    with pytest.raises(ValueError):
        SolvabilityCertificate.model_validate(payload)
    assert not certificate().model_copy(update={field: value}).solvable


def test_impossible_counts_rejected_and_missing_witness_is_not_impossibility():
    payload = certificate().model_dump()
    payload["perturbed_passed"] = 4
    with pytest.raises(ValueError):
        SolvabilityCertificate.model_validate(payload)
    missing = certificate().model_copy(update={"perturbed_runs": 0, "perturbed_passed": 0})
    assert not missing.solvable and missing.witness_failed and not missing.unrecoverable


@pytest.mark.parametrize("value", [True, 0, -1, 1.1, float("nan"), float("inf")])
def test_admission_threshold_is_bounded(value):
    with pytest.raises(ValueError):
        Referee(None, value)


@pytest.mark.parametrize("failure", ["wrong_id", "forged", "exception"])
def test_reference_failures_remain_in_denominator_and_do_not_abort(failure):
    class Reference:
        def certify(self, instance):
            if instance.id == "i":
                if failure == "exception":
                    raise RuntimeError("unavailable")
                return certificate().model_copy(update=(
                    {"instance_id": "other"} if failure == "wrong_id"
                    else {"required_runs": 0}))
            return certificate().model_copy(update={"instance_id": instance.id})

    result = Referee(Reference()).admit([item(), item("second")])
    assert result.unavailable == 1
    assert len(result.certificates) == 2
    assert result.solvable_fraction == 0.5
    assert not result.admitted and result.unrecoverable == 0
    assert "unavailable" in result.certificates[0].evidence


@pytest.mark.parametrize("value", [True, 1.5, 0, float("nan"), float("inf")])
def test_witness_repetition_count_is_positive_integer(value):
    with pytest.raises(ValueError):
        SweReference(None, perturbed_runs=value)


def test_clean_execution_failure_produces_unestablished_certificate():
    instance, _, builder = setup()

    class Model:
        info = type("Info", (), {"id": "model"})()

    reference = SweReference(builder, reference_model=Model())
    reference._run = lambda *args: (_ for _ in ()).throw(RuntimeError("transport down"))
    result = reference.certify(instance)
    assert not result.solvable and not result.unrecoverable
    assert "transport down" in result.evidence


def test_each_witness_failure_is_counted_and_remaining_runs_are_attempted():
    instance, _, builder = setup()
    instance = instance.model_copy(update={"spec": instance.spec.model_copy(
        update={"clause_cell": Cell(levels={"rewrite": "on"})})})

    class Model:
        shippable = True
        info = type("Info", (), {"id": "model"})()

    reference = SweReference(builder, reference_model=Model(), recovery_model=Model())
    calls = []

    def run(*args):
        calls.append(args)
        if len(calls) == 2:
            raise RuntimeError("temporary failure")
        return True, object()

    reference._run = run
    result = reference.certify(instance)
    assert len(calls) == 4
    assert result.perturbed_runs == 3 and result.perturbed_passed == 2
    assert result.witness_failed and not result.solvable and not result.unrecoverable


def test_reference_cannot_omit_active_intervention_witnesses():
    class Reference:
        def certify(self, instance):
            return certificate().model_copy(update={"perturbations": ()})

    instance = item().model_copy(update={"cell": Cell(levels={"rewrite": "on"})})
    result = Referee(Reference()).admit([instance])
    assert not result.admitted
    assert "omits active" in result.certificates[0].evidence
    assert result.unavailable == 1
    assert result.certificates[0].perturbations == ("rewrite",)


def test_nonfinite_witness_budget_is_rejected():
    from adversary.core.trajectory import Budget

    with pytest.raises(ValueError, match="finite"):
        SweReference(None, budget=Budget(max_seconds=float("inf")))


def test_reference_rejects_trajectory_identity_substitution():
    from adversary.core.trajectory import Trajectory
    from adversary.core.verify import Verdict

    instance, _, _ = setup()

    class Model:
        info = type("Info", (), {"id": "model"})()

    class Environment:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def run(self, model, budget):
            return Trajectory(instance_id="other", model_id="model", messages=())

    class Builder:
        def build(self, instance):
            return Environment()

        def verifier(self):
            return self

        def verify(self, trajectory, oracle):
            return Verdict(passed=True)

    result = SweReference(Builder(), reference_model=Model()).certify(instance)
    assert not result.solvable
    assert "identity mismatch" in result.evidence
