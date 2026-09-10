import pytest

from adversary.confirm.criteria import ConfirmationCriteria
from adversary.confirm.receipt import ConfirmationReceipt, ConfirmedMode
from adversary.core.factors import Grounding
from tests.test_probe import make_probe


def receipt(probe_id: str, **overrides) -> ConfirmationReceipt:
    fields = dict(
        probe_id=probe_id,
        condition=make_probe().cell,
        grounding={f: Grounding.CONFIRMABLE for f in make_probe().cell.factors},
        grade=1,
        corpus_fingerprint="corpus",
        sources=("a", "b"),
        n_mode=300,
        mode_success=0.3,
        n_control=300,
        control_success=0.9,
        p_value=0.0001,
        episode_ids=("ep_1", "ep_2"),
        store_digest="d",
        criteria=ConfirmationCriteria(),
    )
    fields.update(overrides)
    return ConfirmationReceipt.issue(**fields)


def test_receipt_digest_detects_tampering():
    r = receipt("probe_x")
    assert r.verify() and r.meets() == []
    assert not r.model_copy(update={"mode_success": 0.1}).verify()


def test_confirmed_mode_requires_a_valid_receipt():
    probe = make_probe()
    mode = ConfirmedMode(probe=probe, receipt=receipt(probe.id))
    assert mode.id == probe.id and mode.grade == 1 and not mode.receipt.discovery_free
    for bad in (
        receipt("someone_else"),
        receipt(probe.id).model_copy(update={"n_mode": 5000}),
        receipt(probe.id, n_mode=50),
        receipt(probe.id, sources=("a",)),
        receipt(probe.id, control_success=0.6),
        receipt(probe.id, grounding={"operation": Grounding.UNGROUNDED}),
        receipt(probe.id, grounding={"other": Grounding.CONFIRMABLE}),
        receipt(probe.id, grounding={"operation": Grounding.ATTESTABLE}),  # grade must be 2
        receipt(probe.id, grade=2),  # grade must be 1 for a confirmable region
    ):
        with pytest.raises(ValueError):
            ConfirmedMode(probe=probe, receipt=bad)


def test_grades_follow_grounding_and_criteria_cap_them():
    probe = make_probe()
    grade2 = receipt(
        probe.id, grounding={f: Grounding.ATTESTABLE for f in probe.cell.factors}, grade=2
    )
    assert ConfirmedMode(probe=probe, receipt=grade2).grade == 2
    capped = receipt(
        probe.id,
        grounding={f: Grounding.ATTESTABLE for f in probe.cell.factors},
        grade=2,
        criteria=ConfirmationCriteria(max_grade=1),
    )
    with pytest.raises(ValueError):
        ConfirmedMode(probe=probe, receipt=capped)
    conditions = receipt(
        probe.id, grounding={f: Grounding.CONDITION for f in probe.cell.factors}, grade=1
    )
    assert conditions.discovery_free and ConfirmedMode(probe=probe, receipt=conditions).grade == 1
