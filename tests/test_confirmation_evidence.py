"""Adversarial evidence checks; these do not establish a D11 confirmation path."""

import pytest

from adversary.confirm.ledger import ModeLedger
from adversary.confirm.receipt import ConfirmedMode
from adversary.core.episode import Episode
from adversary.core.util import sha256_json
from adversary.core.verify import Verdict
from tests.test_confirm_gate import receipt
from tests.test_probe import make_probe


@pytest.mark.parametrize("field", ["mode_success", "control_success", "p_value"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), -0.1, 1.1])
def test_receipt_rejects_invalid_probabilities(field, value):
    with pytest.raises(ValueError):
        receipt("probe", **{field: value})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_receipt_rejects_nonfinite_excess(value):
    with pytest.raises(ValueError):
        receipt("probe", confirmatory_excess_points=value)


def test_control_sample_cannot_be_smaller_than_required_support():
    probe = make_probe()
    underpowered = receipt(probe.id, n_control=1)
    assert any("control items" in reason for reason in underpowered.meets())
    with pytest.raises(ValueError, match="control items"):
        ConfirmedMode(probe=probe, receipt=underpowered)


@pytest.mark.parametrize(
    "field", ["mode_success", "control_success", "p_value", "confirmatory_excess_points"]
)
def test_rehashed_bypassed_validation_cannot_admit_nan(field):
    probe = make_probe()
    poisoned = receipt(probe.id).model_copy(update={field: float("nan")})
    poisoned = poisoned.model_copy(update={"digest": sha256_json(poisoned._payload())})
    assert poisoned.verify()
    with pytest.raises(ValueError, match="finite"):
        ConfirmedMode(probe=probe, receipt=poisoned)


@pytest.mark.parametrize("actual_pin", [None, "previous"])
def test_ledger_rejects_unstamped_or_old_anchor_without_mutation(actual_pin):
    probe = make_probe()
    mode = ConfirmedMode(probe=probe, receipt=receipt(probe.id))
    anchor = Episode(
        id="ep_1",
        instance_id="task",
        cell=probe.cell,
        seed=0,
        model_id="model",
        target_pin=actual_pin,
        probe_id=probe.id,
        verdict=Verdict(passed=False),
        verifier="v",
    )
    ledger = ModeLedger("current")
    with pytest.raises(ValueError, match="current-pin"):
        ledger.admit(mode, anchor, target_pin="current")
    assert ledger.entries == {} and ledger.history == [] and ledger.version == 0
    current = anchor.model_copy(update={"target_pin": "current"})
    assert ledger.admit(mode, current, target_pin="current") in ledger.entries


@pytest.mark.parametrize("field", ["n_mode", "n_control"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), 300.5, True])
def test_rehashed_invalid_counts_cannot_admit(field, value):
    probe = make_probe()
    poisoned = receipt(probe.id).model_copy(update={field: value})
    poisoned = poisoned.model_copy(update={"digest": sha256_json(poisoned._payload())})
    with pytest.raises(ValueError):
        ConfirmedMode(probe=probe, receipt=poisoned)


def test_rehashed_nested_criteria_cannot_remove_support_requirement():
    probe = make_probe()
    original = receipt(probe.id, n_control=1)
    criteria = original.criteria.model_copy(update={"min_items": float("nan")})
    poisoned = original.model_copy(update={"criteria": criteria})
    poisoned = poisoned.model_copy(update={"digest": sha256_json(poisoned._payload())})
    with pytest.raises(ValueError):
        ConfirmedMode(probe=probe, receipt=poisoned)


def test_ledger_revalidates_preconstructed_mode():
    probe = make_probe()
    mode = ConfirmedMode(probe=probe, receipt=receipt(probe.id))
    mode = mode.model_copy(update={"receipt": receipt(probe.id, n_control=1)})
    anchor = Episode(
        id="ep_1",
        instance_id="task",
        cell=probe.cell,
        seed=0,
        model_id="model",
        target_pin="current",
        probe_id=probe.id,
        verdict=Verdict(passed=False),
        verifier="v",
    )
    ledger = ModeLedger("current")
    with pytest.raises(ValueError, match="control items"):
        ledger.admit(mode, anchor, target_pin="current")
    assert not ledger.entries and not ledger.history


@pytest.mark.parametrize("sources", [("", " "), ("a", " a")])
def test_empty_or_whitespace_alias_sources_cannot_support_receipt(sources):
    probe = make_probe()
    with pytest.raises(ValueError, match="sources"):
        ConfirmedMode(probe=probe, receipt=receipt(probe.id, sources=sources))


def test_receipt_cannot_substitute_another_condition():
    from adversary.core.factors import Cell

    probe = make_probe()
    with pytest.raises(ValueError, match="condition"):
        ConfirmedMode(
            probe=probe, receipt=receipt(probe.id, condition=Cell(levels={"operation": "add"}))
        )
