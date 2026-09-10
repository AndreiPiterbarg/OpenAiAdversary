"""Semantic gate and forgery regressions; doubles do not attest live protection."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from domains.swe_agents.environment.factory_postcheck import (
    CHALLENGE_IDS,
    FactoryPostCheck,
    combine_factory_results,
    prepare_task_post_check,
)
from domains.swe_agents.environment.factory_verifier import F2P, P2P
from domains.swe_agents.environment.runtime import RuntimeUnavailable
from domains.swe_agents.environment.test_results import TestEvidenceError as EvidenceError

PATH = ".prun-factory-postcheck-abc/test_factory_semantics.py"
SOURCE = (
    Path(__file__).parents[1] / "domains/swe_agents/scripts/factory_challenges.py"
).read_text()


def records(nodes, *, failed=(), exit_code=None):
    statuses = "\n".join(("FAILED " if node in failed else "PASSED ") + node for node in nodes)
    return (int(bool(failed)) if exit_code is None else exit_code), statuses, ""


def frozen():
    return records(F2P + P2P)


def extra_nodes():
    return tuple(PATH + "::" + node for node in CHALLENGE_IDS)


def test_frozen_pass_cannot_override_a_supplementary_failure():
    extra = extra_nodes()
    result = combine_factory_results(
        frozen(), records(extra, failed=(extra[0],)), challenge_path=PATH
    )
    assert result["post_checks"]["frozen_passed"]
    assert not result["post_checks"]["supplementary_passed"]
    assert result["diagnostic_passed"] is False


@pytest.mark.parametrize(
    "mutant, failed_id",
    [
        ("constant_choice", "test_maybe_preserves_decider_defaults[False]"),
        ("constant_yes", "test_maybe_preserves_decider_defaults[False]"),
        ("hardcoded_locale", "test_faker_decider_preserves_locale_and_branch[fr_FR-True]"),
        ("missing_branch_wrapper", "test_nested_maybe_evaluates_only_selected_branch[True-True]"),
    ],
)
def test_original_survivor_semantic_failure_never_counts_passed(mutant, failed_id):
    result = combine_factory_results(
        frozen(),
        records(extra_nodes(), failed=(PATH + "::" + failed_id,)),
        challenge_path=PATH,
    )
    assert result["diagnostic_passed"] is False, mutant
    assert result["protected_status"] == "unknown"


@pytest.mark.parametrize("damage", ["missing", "skipped", "contradictory", "collection_error"])
def test_incomplete_or_corrupted_supplementary_results_refused(damage):
    code, out, err = records(extra_nodes())
    if damage == "missing":
        out = "\n".join(out.splitlines()[:-1])
    elif damage == "skipped":
        out = out.replace("PASSED", "SKIPPED", 1)
    elif damage == "contradictory":
        out += "\nFAILED " + extra_nodes()[0]
    else:
        code = 2
    with pytest.raises(EvidenceError):
        combine_factory_results(frozen(), (code, out, err), challenge_path=PATH)


def test_forged_all_pass_stdout_can_never_grant_protected_pass():
    # Arbitrary code can os.write matching pytest records and exit(0). Even a
    # perfect forged transcript is only a diagnostic observation here.
    result = combine_factory_results(frozen(), records(extra_nodes()), challenge_path=PATH)
    assert result["diagnostic_passed"] is True
    assert result["protected_status"] == "unknown"
    assert result["protected_clean_pass"] is None
    assert result["post_checks"]["authenticated_test_evidence"] is False
    with pytest.raises(RuntimeUnavailable, match="unauthenticated"):
        FactoryPostCheck(PATH).require_protected()


def test_nonzero_exit_with_pass_records_never_counts_passed():
    result = combine_factory_results(
        frozen(), records(extra_nodes(), exit_code=1), challenge_path=PATH
    )
    assert not result["diagnostic_passed"]


class Session:
    def __init__(self):
        self.files = {PATH: SOURCE}
        self.commands = []
        self.result = records(extra_nodes())
        self.tamper = False

    def read_file(self, path):
        return self.files[path]

    def write_file(self, path, value):
        self.files[path] = value

    def exec(self, command, timeout):
        self.commands.append(command)
        if command.startswith("mktemp"):
            return 0, "./.prun-factory-postcheck-abc\n", ""
        if self.tamper:
            self.files[PATH] = "assert True"
        return self.result


def test_postcheck_automatically_runs_and_records_raw_supplementary_evidence():
    session = Session()
    saved = []
    result = FactoryPostCheck(PATH, saved.append).evaluate(session, frozen())
    assert len(session.commands) == 1 and "--rootdir=." in session.commands[0]
    assert saved[0]["phase"] == "supplementary_tests"
    assert saved[0]["stdout"] == session.result[1]
    assert result["diagnostic_passed"]


@pytest.mark.parametrize("when", ["before", "during"])
def test_detected_challenge_tampering_refuses_scoring(when):
    session = Session()
    if when == "before":
        session.files[PATH] = "assert True"
    else:
        session.tamper = True
    with pytest.raises(RuntimeUnavailable, match="source changed"):
        FactoryPostCheck(PATH).evaluate(session, frozen())


def test_other_task_does_not_receive_factory_checks():
    session = Session()
    assert prepare_task_post_check(SimpleNamespace(key="other-task"), session) is None
    assert not session.commands


def test_registered_factory_task_prepares_pinned_source_before_candidate_execution(monkeypatch):
    import domains.swe_agents.environment.factory_postcheck as module

    session = Session()
    pin = SimpleNamespace(
        key=module.KEY,
        test_command=module.TEST_COMMAND,
        test_patch="frozen",
        model_dump=lambda **kw: {},
    )
    monkeypatch.setattr(module, "FactoryFinalVerifier", lambda pin: None)
    monkeypatch.setattr(module, "TEST_PATCH_SHA256", module._sha("frozen"))
    postcheck = prepare_task_post_check(pin, session)
    assert postcheck.challenge_path == PATH
    assert session.files[PATH] == SOURCE
    assert session.commands == ["mktemp -d ./.prun-factory-postcheck-XXXXXXXX"]


def test_invalid_challenge_path_refused_before_any_execution():
    with pytest.raises(ValueError, match="challenge path"):
        FactoryPostCheck("../candidate.py")


@pytest.mark.parametrize("phase", ["frozen", "supplementary"])
def test_complete_pass_output_with_timeout_is_unknown(phase):
    first = records(F2P + P2P, exit_code=124 if phase == "frozen" else 0)
    second = records(extra_nodes(), exit_code=124 if phase == "supplementary" else 0)
    with pytest.raises(RuntimeUnavailable, match="timed out"):
        combine_factory_results(first, second, challenge_path=PATH)
