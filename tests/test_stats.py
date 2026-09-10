import random

import numpy as np
import pytest

from adversary.core.episode import Episode
from adversary.core.factors import Cell
from adversary.core.verify import Verdict
from adversary.stats.calibration import (
    central_estimate,
    detectability,
    equivalent_below,
    forced_rate_for_excess,
    reference_magnitude,
)
from adversary.stats.cost import compute_hours, per_compute_hour
from adversary.stats.equivalence import mcnemar_test, paired_bootstrap, tost_paired
from adversary.stats.excess import Baseline, estimate_excess, excess_over_additive, hot_cells
from adversary.stats.honesty import honesty_report, honesty_shift
from adversary.stats.importance import Importance, PrevalenceEstimate, rank
from adversary.stats.interaction_order import interaction_order_curve
from adversary.stats.multiplicity import AlphaSpending, EProcess, benjamini_hochberg
from adversary.stats.rates import compare_rates, measurable, wilson_interval
from adversary.stats.regions import (
    CellCounts,
    cluster_regions,
    homogeneity,
    lrt_common_excess,
    one_region,
)


def synthetic_episodes(n_per_cell: int = 40, seed: int = 0) -> list[Episode]:
    """Three binary factors; failure planted on a & b & c with small main effects."""
    rng = random.Random(seed)
    episodes = []
    for a in "01":
        for b in "01":
            for c in "01":
                rate = 0.9 if (a, b, c) == ("1", "1", "1") else 0.1 * (a == "1") + 0.05 * (b == "1")
                for i in range(n_per_cell):
                    failed = rng.random() < rate
                    episodes.append(
                        Episode(
                            id=f"e{a}{b}{c}{i}",
                            instance_id=f"i{a}{b}{c}{i}",
                            cell=Cell(levels={"a": a, "b": b, "c": c}),
                            seed=i,
                            model_id="m",
                            verdict=Verdict(passed=not failed),
                            claimed_success=True,
                            verifier="v@1",
                        )
                    )
    return episodes


HOT = Cell(levels={"a": "1", "b": "1", "c": "1"})


def test_excess_detects_planted_interaction_on_every_scale():
    eps = synthetic_episodes()
    hot = excess_over_additive(eps, HOT, bootstrap=100)
    cold = excess_over_additive(eps, Cell(levels={"a": "0", "c": "0"}), bootstrap=100)
    assert hot.baseline is Baseline.LOGISTIC and hot.excess > 0.05 and hot.ci_low > 0
    assert hot.one_sided_upper >= hot.excess and hot.one_sided_upper <= hot.ci_high + 1e-12
    assert hot.odds_ratio is not None and hot.odds_ratio > 1
    assert abs(cold.excess) < 0.15
    additive = excess_over_additive(eps, HOT, baseline=Baseline.ADDITIVE, bootstrap=0)
    independent = excess_over_additive(eps, HOT, baseline=Baseline.INDEPENDENT, bootstrap=0)
    # A planted probability-scale interaction is partly absorbed by main effects on the logit
    # scale, so the pre-registered logistic baseline is the most conservative of the three.
    assert additive.excess > 0.3 and additive.excess > independent.excess > hot.excess
    ranked = hot_cells(eps, [HOT, cold.cell], min_n=10, bootstrap=20)
    assert ranked[0].cell == HOT
    assert hot.clusters == len(eps)  # no resource set: every episode is its own cluster


def test_estimate_excess_shares_fits_and_matches_single_cell():
    eps = synthetic_episodes(n_per_cell=20)
    cells = [HOT, Cell(levels={"a": "0", "b": "0"}), Cell(levels={"b": "1", "c": "1"})]
    batch = estimate_excess(eps, cells, bootstrap=50, seed=3)
    for cell, est in zip(cells, batch, strict=True):
        single = excess_over_additive(eps, cell, bootstrap=50, seed=3)
        assert est.excess == pytest.approx(single.excess) and est.n == single.n
        assert est.ci_low == pytest.approx(single.ci_low) and est.ci_high == pytest.approx(
            single.ci_high
        )


def test_excess_uses_only_measurable_episodes_and_clusters_on_resource():
    eps = synthetic_episodes(n_per_cell=20)
    clustered = [e.model_copy(update={"resource": f"r{i % 5}"}) for i, e in enumerate(eps)]
    est = excess_over_additive(clustered, HOT, bootstrap=50)
    assert est.clusters == 5
    base = excess_over_additive(eps, HOT, bootstrap=0)
    extras = [
        eps[0].model_copy(update={"id": "planted", "planted": True}),
        eps[0].model_copy(update={"id": "unrealised", "realised": False}),
    ]
    assert excess_over_additive(eps + extras, HOT, bootstrap=0).n == base.n
    assert len(measurable(eps + extras)) == len(eps)
    assert all(np.isnan(v) for v in (excess_over_additive([], HOT, bootstrap=0).excess,))


def test_interaction_order_curve_attributes_planted_third_order():
    curve = interaction_order_curve(synthetic_episodes(), max_order=3, fail_threshold=0.5, min_n=5)
    assert curve.orders == (1, 2, 3)
    assert curve.failing_configurations == 1
    assert curve.cumulative_fraction[-1] == pytest.approx(1.0) and curve.unexplained == 0


def test_region_tests():
    same = [
        CellCounts(cell=Cell(levels={"a": "0"}), n=100, failures=50),
        CellCounts(cell=Cell(levels={"a": "1"}), n=100, failures=52),
    ]
    different = [
        CellCounts(cell=Cell(levels={"a": "0"}), n=100, failures=10),
        CellCounts(cell=Cell(levels={"a": "1"}), n=100, failures=80),
    ]
    assert homogeneity(same).homogeneous and not homogeneity(different).homogeneous
    assert len(cluster_regions(same)) == 1 and len(cluster_regions(different)) == 2
    common = [
        CellCounts(cell=Cell(levels={"a": "0"}), n=200, failures=80, predicted=0.1),
        CellCounts(cell=Cell(levels={"a": "1"}), n=200, failures=120, predicted=0.3),
    ]
    test = lrt_common_excess(common)
    assert test.method == "lrt" and test.homogeneous and abs(test.common_excess - 0.3) < 0.05
    split = [
        CellCounts(cell=Cell(levels={"a": "0"}), n=200, failures=20, predicted=0.1),
        CellCounts(cell=Cell(levels={"a": "1"}), n=200, failures=160, predicted=0.1),
    ]
    assert (
        not lrt_common_excess(split).homogeneous
        and one_region(common[:1], common[1:]).method == "lrt"
    )


def test_equivalence_tests():
    rng = np.random.default_rng(0)
    before = rng.random(3000) < 0.7
    same = tost_paired(before.astype(float), before.astype(float), margin=0.02)
    assert same.equivalent and same.mean_difference == 0.0
    assert not tost_paired(before.astype(float), before.astype(float) - 0.1, margin=0.02).equivalent
    after = before.copy()
    flip = rng.choice(3000, 300, replace=False)
    after[flip] = ~after[flip]
    mc = mcnemar_test(before, after)
    assert mc.before_only + mc.after_only == 300
    boot = paired_bootstrap(before.astype(float), before.astype(float), resamples=200)
    assert boot.ci_low <= 0.0 <= boot.ci_high
    clustered = tost_paired(
        before.astype(float), before.astype(float), clusters=[str(i % 30) for i in range(3000)]
    )
    assert clustered.clustered and clustered.n == 30


def test_rates_multiplicity_and_cost():
    low, high = wilson_interval(0, 10)
    assert low == 0.0 and high < 0.35
    cmp = compare_rates(5, 100, 60, 100)
    assert cmp.effect == pytest.approx(0.55) and cmp.p_value < 1e-6
    assert compare_rates(50, 100, 52, 100).p_value > 0.5
    assert benjamini_hochberg([0.001, 0.01, 0.03, 0.2, 0.5], q=0.05) == [
        True,
        True,
        True,
        False,
        False,
    ]
    assert benjamini_hochberg([]) == []
    assert abs(sum(AlphaSpending(alpha=0.05).level(k) for k in range(1, 20000)) - 0.05) < 1e-3
    assert EProcess(alpha=0.05).update(10).update(3).rejects
    eps = [e.model_copy(update={"build_seconds": 60.0}) for e in synthetic_episodes(n_per_cell=2)]
    assert compute_hours(eps) == pytest.approx(len(eps) * 60 / 3600)
    assert per_compute_hour(3, eps) == pytest.approx(3 / (len(eps) * 60 / 3600))


def test_honesty_gate_cannot_pass_in_silence():
    eps = synthetic_episodes(n_per_cell=10)
    report = honesty_report(eps)
    assert report.determinable and report.claimed_success_rate == 1.0
    assert report.silent_failure_rate == pytest.approx(1 - report.honest_rate)
    assert honesty_shift(
        report, report.model_copy(update={"honest_rate": report.honest_rate - 0.1})
    ).moved
    assert not honesty_shift(report, report).moved
    silent = honesty_report([e.model_copy(update={"claimed_success": None}) for e in eps])
    assert not silent.determinable
    shift = honesty_shift(report, silent)
    assert shift.moved and not shift.determinable


def test_importance_ranks_measured_prevalence_first():
    measured = Importance(
        region=HOT,
        severity=40,
        prevalence=PrevalenceEstimate(value=0.3, source="customer_traffic"),
        silence=0.9,
        systematicity=0.9,
    )
    argued = Importance(
        region=Cell(levels={"b": "1"}),
        severity=40,
        prevalence=PrevalenceEstimate(value=0.3, source="argument"),
        silence=0.9,
        systematicity=0.9,
    )
    assert rank([argued, measured])[0] is measured


def test_calibration_arithmetic():
    assert forced_rate_for_excess(0.4, 0.03) == pytest.approx(0.05)
    with pytest.raises(ValueError):
        forced_rate_for_excess(0.99, 0.03)
    delta = reference_magnitude(3.0, [0.9, 1.4, 1.1, 2.0, 1.2], resamples=200)
    assert delta.delta_points == pytest.approx(1.2) and delta.ci_low <= 1.2 <= delta.ci_high
    power = detectability([True] * 26 + [False] * 4)
    assert power.meets and power.power.rate == pytest.approx(26 / 30)
    assert not detectability([True] * 20 + [False] * 10).meets and not detectability([]).meets
    centre = central_estimate(
        [0.5, 1.0, 1.5, 4.0, 6.0, 0.7, 1.1], statistic="median", resamples=500
    )
    assert centre.one_sided_lower <= centre.point <= centre.one_sided_upper
    assert equivalent_below(0.8, 1.2).equivalent and not equivalent_below(1.3, 1.2).equivalent
    assert not equivalent_below(float("nan"), 1.2).equivalent
