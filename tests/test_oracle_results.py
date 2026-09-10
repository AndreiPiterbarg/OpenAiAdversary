import pytest

from adversary.core.trajectory import Trajectory
from domains.swe_agents.environment.oracle import SweDualOracle
from domains.swe_agents.environment.spec import SweOracle
from domains.swe_agents.environment.test_results import TestEvidenceError as EvidenceError
from domains.swe_agents.environment.test_results import parse_test_results


def check(output, exit_code=0):
    oracle = SweOracle(
        test_command="pytest -rA",
        fail_to_pass=("tests/test_x.py::test_fix",),
        pass_to_pass=("tests/test_x.py::test_kept",),
        canary="c",
    )
    trajectory = Trajectory(
        instance_id="i",
        model_id="m",
        messages=(),
        final_state={
            "test_results": {"exit": exit_code, "stdout": output},
            "changed_files": [],
            "installed_packages": {},
            "added_packages": [],
        },
    )
    return SweDualOracle().verify(trajectory, oracle)


def test_exact_f2p_and_p2p_are_both_required():
    assert check("PASSED tests/test_x.py::test_fix\nPASSED tests/test_x.py::test_kept").passed
    assert not check(
        "PASSED tests/test_x.py::test_fix\nFAILED tests/test_x.py::test_kept - regression", 1
    ).passed
    with pytest.raises(EvidenceError):
        check("PASSED tests/test_x.py::test_fix")
    with pytest.raises(EvidenceError):
        check("PASSED tests/test_x.py::test_fix_extra\nPASSED tests/test_x.py::test_kept")


@pytest.mark.parametrize("status", ["SKIPPED", "XFAIL", "XPASS", "ERROR"])
def test_incomplete_or_nonpassing_status_is_unreached(status):
    with pytest.raises(EvidenceError):
        check(f"{status} tests/test_x.py::test_fix\nPASSED tests/test_x.py::test_kept", 1)


@pytest.mark.parametrize("exit_code", [2, 3, 4, 5, -9])
def test_interrupted_or_invalid_command_exit_is_unreached(exit_code):
    with pytest.raises(EvidenceError):
        check("PASSED tests/test_x.py::test_fix\nPASSED tests/test_x.py::test_kept", exit_code)


def test_name_substrings_conflicts_and_exit_contradictions_do_not_pass():
    for output in (
        "printed tests/test_x.py::test_fix and tests/test_x.py::test_kept",
        "PASSED tests/test_x.py::test_fix\nFAILED tests/test_x.py::test_fix\nPASSED tests/test_x.py::test_kept",
        "FAILED tests/test_x.py::test_fix\nPASSED tests/test_x.py::test_kept",
    ):
        with pytest.raises(EvidenceError):
            check(output)


def test_verbose_and_short_summary_duplicates_are_consistent():
    evidence = parse_test_results(
        0, "x.py::test_a PASSED [ 50%]\nPASSED x.py::test_a\nPASSED x.py::test_b"
    )
    assert not evidence.conflicts
    assert len(evidence.require(("x.py::test_a", "x.py::test_b"))) == 2
