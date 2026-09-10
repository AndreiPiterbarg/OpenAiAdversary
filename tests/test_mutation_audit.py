"""Declared mutation controls execute fresh; missing evidence cannot become valid."""

import sys

import pytest

from domains.swe_agents.environment.audit import AuditReport
from domains.swe_agents.environment.mutation import MutationCase, run_mutation_audit
from tests.test_protected_oracle import patch_for, replay  # noqa: F401

NODE = "tests/test_api.py::test_answer"
COMMAND = (
    f"""{sys.executable} -B -c 'import api,sys; ok=api.answer==0; """
    f'''print("{NODE} "+("PASSED" if ok else "FAILED")); sys.exit(0 if ok else 1)' '''
)


def cases(task):
    return (
        MutationCase(id="kill", patch=patch_for(task, "api.py", "answer = 1\n")),
        MutationCase(id="survivor", patch=patch_for(task, "api.py", "answer = 0 # unchanged\n")),
    )


def test_fresh_baseline_kill_and_survivor(replay):  # noqa: F811
    report = run_mutation_audit(replay.runtime.start, COMMAND, (NODE,), cases(replay))
    assert report.complete and report.score == 0.5 and report.survivors == 1
    assert [row.outcome for row in report.mutants] == ["killed", "survived"]
    assert len(replay.runtime.sessions) == 3 and all(s.closed for s in replay.runtime.sessions)
    assert len({str(s.root) for s in replay.runtime.sessions}) == 3
    assert (replay.runtime.base / "api.py").read_text() == "answer = 0\n"


def test_failed_baseline_retains_all_cases_without_running_them(replay):  # noqa: F811
    command = COMMAND.replace("api.answer==0", "api.answer==99")
    report = run_mutation_audit(replay.runtime.start, command, (NODE,), cases(replay))
    assert not report.complete and report.score is None and report.survivors is None
    assert len(report.mutants) == 2 and all(r.outcome == "unresolved" for r in report.mutants)
    assert len(replay.runtime.sessions) == 1


def test_bad_patch_and_import_error_are_unknown_not_killed(replay):  # noqa: F811
    mutants = (
        MutationCase(id="bad-patch", patch="invalid"),
        MutationCase(id="invalid-import", patch=patch_for(replay, "api.py", "broken syntax!\n")),
        cases(replay)[0],
    )
    report = run_mutation_audit(replay.runtime.start, COMMAND, (NODE,), mutants)
    assert [r.outcome for r in report.mutants] == ["unresolved", "unresolved", "killed"]
    assert not report.complete and report.score is None
    assert all(s.closed for s in replay.runtime.sessions)


def test_session_reuse_and_teardown_failure_do_not_pass(replay):  # noqa: F811
    session = replay.runtime.start()
    report = run_mutation_audit(lambda: session, COMMAND, (NODE,), cases(replay))
    assert all(r.outcome == "unresolved" for r in report.mutants)
    assert report.score is None

    def start():
        session = replay.runtime.start()

        def stop():
            raise RuntimeError("cannot clean up")

        session.stop = stop
        return session

    report = run_mutation_audit(start, COMMAND, (NODE,), cases(replay))
    assert report.baseline.stage == "stop" and report.score is None


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_invalid_budget_fails_before_allocating(replay, timeout):  # noqa: F811
    with pytest.raises(ValueError):
        run_mutation_audit(replay.runtime.start, COMMAND, (NODE,), cases(replay), timeout=timeout)
    assert replay.runtime.sessions == []


def test_empty_or_duplicate_schedule_cannot_succeed(replay):  # noqa: F811
    case = cases(replay)[0]
    for mutants in ((), (case, case)):
        with pytest.raises(ValueError):
            run_mutation_audit(replay.runtime.start, COMMAND, (NODE,), mutants)
    assert not replay.runtime.sessions


def test_missing_mutation_evidence_is_not_a_valid_audit():
    base = dict(git_stripped=True, contaminated=False)
    assert not AuditReport(**base).valid
    assert not AuditReport(**base, mutation_score=1, surviving_trivial_mutants=0).valid
    passing = AuditReport(
        **base, mutation_score=1, surviving_trivial_mutants=0, tested_trivial_mutants=1
    )
    assert passing.valid
    for update in (
        {"mutation_score": float("nan")},
        {"tested_trivial_mutants": True},
        {"surviving_trivial_mutants": -1},
        {"mutation_score": 0.5},
    ):
        assert not passing.model_copy(update=update).valid


def test_unrelated_collection_error_cannot_count_as_a_kill(replay):  # noqa: F811
    command = COMMAND.replace(
        'sys.exit(0 if ok else 1)',
        'print("ERROR tests/test_other.py::test_collection") if not ok else None; sys.exit(0 if ok else 1)',
    )
    report = run_mutation_audit(replay.runtime.start, command, (NODE,), cases(replay))
    assert report.baseline.outcome == 'baseline_passed'
    assert report.mutants[0].outcome == 'unresolved'
    assert report.score is None
