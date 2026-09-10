"""The restricted smoke cannot supply general episode or pair admission evidence."""

import pytest

from adversary.core.trajectory import Trajectory
from domains.swe_agents.environment.factory_verifier import (
    F2P,
    P2P,
    FactoryFinalVerifier,
    FactoryVerifierUnavailable,
    evaluate_observations,
)
from domains.swe_agents.environment.oracle import SweDualOracle
from domains.swe_agents.environment.spec import SweOracle
from domains.swe_agents.environment.test_results import TestEvidenceError as EvidenceError
from tests.test_factory_verifier import pin
from tests.test_grounded_runner import rig  # noqa: F401
from tests.test_pair_admission import gate_rig  # noqa: F401
from tests.test_tier1_grounding import grounded  # noqa: F401


def test_restricted_factory_oracle_stops_every_attempt_before_inference(rig, monkeypatch):  # noqa: F811
    runner, proposer, reference, gate, environments, task = rig
    verifier = FactoryFinalVerifier(pin())
    runner.builder.final_oracle_factory = lambda instance: verifier

    def forbidden(*args, **kwargs):
        raise AssertionError("restricted verifier must refuse before proposal or evaluation")

    monkeypatch.setattr(proposer, "propose", forbidden)
    monkeypatch.setattr(verifier, "evaluate_sources", forbidden)
    report = runner.run(task, 3)
    assert len(report.attempts) == 3
    assert all(row.status == "unreached" and row.stage == "protection" for row in report.attempts)
    assert all("not a generic protected FinalOracle" in row.reason for row in report.attempts)
    assert all(not row.reports for row in report.attempts)
    assert not environments and reference.calls == gate.calls == 0
    assert len(runner.attempt_log.read_text().splitlines()) == 3


def test_restricted_factory_oracle_cannot_issue_pair_receipts(gate_rig):  # noqa: F811
    gate, draft, instances, environments = gate_rig
    verifier = FactoryFinalVerifier(pin())
    gate.builder.require_protected = lambda instance: verifier.require_protected()
    with pytest.raises(FactoryVerifierUnavailable, match="not a generic protected FinalOracle"):
        gate.check(draft, instances)
    assert not environments
    assert not gate.receipts.exists()


def test_successful_interface_observations_are_not_original_test_evidence():
    observations = dict(f2p_pseudonym="yes", p2p_pseudonym=None, p2p_unknown_fullname="")
    assertions = evaluate_observations(observations)
    assert all(assertions.values())
    trajectory = Trajectory(
        instance_id="restricted-smoke",
        model_id="test-double",
        messages=(),
        final_state={
            "interface_assertions": assertions,
            "interface_success": True,
            "original_test_verdict": None,
            "authenticated_test_evidence": False,
            "observations": observations,
        },
    )
    oracle = SweOracle(
        test_command="pytest", fail_to_pass=F2P, pass_to_pass=P2P, canary="boundary-test"
    )
    with pytest.raises(EvidenceError, match="missing test command exit status"):
        SweDualOracle().verify(trajectory, oracle)
