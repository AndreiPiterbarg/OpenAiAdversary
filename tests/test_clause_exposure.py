"""Deterministic recorded-trace marginal contribution tests; no model calls."""

from types import SimpleNamespace

from adversary.core.factors import Cell
from domains.swe_agents.scripts import clause_exposure as module


def check(monkeypatch, levels, recorded, *, b_effect=True, limit=4000):
    class Worker:
        def __init__(self, program, clauses, cell, seed, config):
            self.cell = cell

        def prepare(self, session, spec):
            assert session is None

        def observe(self, step, tool, args, raw):
            return raw + ("A" if self.cell["a"] == "on" else "") + (
                "B" if self.cell["b"] == "on" and b_effect else ""
            )

        def close(self):
            pass

    monkeypatch.setattr(module, "IsolatedObservation", Worker)
    def visible(value):
        return value if len(value) <= limit else value[:limit] + module.CLIPPED
    records = [dict(step=0, tool="bash", args={}, raw="raw", output=recorded,
                    visible_raw=visible("raw"), visible_output=visible(recorded))]
    return module.clause_exposure(SimpleNamespace(clauses=("a", "b"), perturbation=None),
                                  Cell(levels=levels), 1, {"observation_limit": limit}, records)


def test_joint_one_clause_missing_is_unrealized(monkeypatch):
    result = check(monkeypatch, {"a": "on", "b": "on"}, "rawA", b_effect=False)
    assert result["status"] == "verified" and result["visible_changed"]
    assert result["clause_visible_contribution"]["a"]["exposed"]
    assert not result["clause_visible_contribution"]["b"]["exposed"]
    assert not result["realized"]


def test_joint_both_clauses_visible_is_realized(monkeypatch):
    result = check(monkeypatch, {"a": "on", "b": "on"}, "rawAB")
    assert result["actual_replay_matches"] and result["realized"]
    assert not result["counterfactual_outcome_claim"]


def test_replay_mismatch_and_clipped_effect_refuse_exposure(monkeypatch):
    result = check(monkeypatch, {"a": "on", "b": "off"}, "different")
    assert result["status"] == "unknown" and not result["realized"]
    clipped = check(monkeypatch, {"a": "on", "b": "on"}, "rawAB", limit=2)
    assert not clipped["visible_changed"] and not clipped["realized"]


def test_control_identity_realized_without_visible_change(monkeypatch):
    result = check(monkeypatch, {"a": "off", "b": "off"}, "raw")
    assert result["realized"] and not result["visible_changed"]
