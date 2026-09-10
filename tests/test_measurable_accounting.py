"""Missing measurable outcomes must not become zero failure or inflate support."""

from types import SimpleNamespace

import pytest

from adversary.confirm import ConfirmationCriteria, Confirmer
from adversary.core.episode import Episode
from adversary.core.verify import Verdict
from adversary.execution.harness import RunReport
from adversary.execution.store import EpisodeStore
from adversary.probe import MinimalPair
from tests.test_end_to_end import CONTROL, HOT, make_probe
from tests.toy_domain import SPACE, make_domain


def outcome(name, *, realised=True, planted=False, passed=False):
    return Episode(id=name, instance_id=name, cell=HOT, seed=0, model_id='fixture',
                   verifier='fixture', verdict=Verdict(passed=passed),
                   realised=realised, planted=planted)


@pytest.mark.parametrize('episodes', [(), (outcome('unrealised', realised=False),),
                                       (outcome('planted', planted=True),)])
def test_no_measurable_denominator_has_no_rate(episodes):
    report = RunReport(episodes=episodes)
    assert report.failure_rate is None
    assert report.silent_failure_rate is None


def test_actual_zero_and_nonzero_failure_rates_remain_distinct():
    assert RunReport(episodes=(outcome('pass', passed=True),)).failure_rate == 0
    assert RunReport(episodes=(outcome('fail'),)).failure_rate == 1


def confirmation(tmp_path, mode, control):
    harness = SimpleNamespace(
        store=EpisodeStore(tmp_path),
        run=lambda *args, **kwargs: mode if kwargs['arm']=='real_mode' else control,
    )
    confirmer = Confirmer(harness, SPACE, criteria=ConfirmationCriteria(min_items=2))
    probe = make_probe('fixture', MinimalPair(control=CONTROL, treatment=HOT), HOT)
    return confirmer.confirm(probe, make_domain().corpus, None)


def test_unrealised_only_arm_cannot_confirm(tmp_path):
    result = confirmation(tmp_path, RunReport(episodes=(outcome('unknown', realised=False),)),
                          RunReport(episodes=(outcome('control', passed=True),)))
    assert result.mode is None and result.receipt is None
    assert result.reasons == ('both arms require measurable episodes',)


def test_unrealised_rows_cannot_inflate_support(tmp_path):
    mode = RunReport(episodes=(outcome('measured'), outcome('unknown', realised=False)))
    control = RunReport(episodes=(outcome('c1', passed=True), outcome('c2', passed=True)))
    result = confirmation(tmp_path, mode, control)
    assert result.mode is None
    assert result.receipt.n_mode == 1 and result.receipt.n_control == 2
    assert any('1 mode items < 2' in reason for reason in result.reasons)
