"""Known hand-authored program semantics; Linux execution tested separately."""

import sys

import pytest

from adversary.core.factors import Cell
from adversary.core.trajectory import Budget
from domains.swe_agents.scripts.factory_contrast import (
    CLAUSE,
    NEEDLE,
    NOTE,
    PROGRAM,
    LoggedFactoryContrast,
    preregistration,
)


def program(level="on"):
    # This fixture executes our reviewed source only; production uses isolated worker.
    item = PROGRAM.load()(Cell(levels={CLAUSE: level}), 1)
    item.prepare(None, {})
    return item


def test_first_shell_opportunity_only():
    item = program()
    assert item.observe(0, "read_file", {}, NEEDLE) == NEEDLE
    assert item.observe(1, "shell", {}, "unrelated") == "unrelated"
    assert item.observe(2, "shell", {}, NEEDLE) == NEEDLE + NOTE
    assert item.observe(3, "shell", {}, NEEDLE) == NEEDLE
    assert item.observe(4, "submit", {}, NEEDLE) == NEEDLE


def test_control_identity():
    item = program("off")
    assert item.observe(0, "shell", {}, NEEDLE) == NEEDLE
    assert item.observe(1, "shell", {}, NEEDLE) == NEEDLE


class KnownSourceWorker:
    def __init__(self, source, clauses, cell, seed, config):
        self.item = source.load()(cell, seed)

    def prepare(self, session, spec):
        self.item.prepare(session, spec)

    def observe(self, *args):
        return self.item.observe(*args)

    def close(self):
        pass


def test_audit_records_actual_clipped_visibility():
    wrapper = LoggedFactoryContrast(treatment=True, observation_factory=KnownSourceWorker)
    wrapper.prepare(None, {"observation_limit": 5})
    wrapper.observe(1, "shell", {"command": "cat factory/declarations.py"}, NEEDLE)
    record = wrapper.records[0]
    assert record["changed"] and not record["visible_trigger"]
    assert record["raw_sha256"] != record["output_sha256"]
    assert record["visible_raw_sha256"] == record["visible_output_sha256"]


def test_preregistered_pairs_preserve_task_and_budget():
    plan = preregistration(Budget(max_steps=8, max_tokens=3000))
    assert [x["arm"] for x in plan["runs"]] == ["treatment", "control", "control", "treatment"]
    assert [x["pair"] for x in plan["runs"]] == [1, 1, 2, 2]
    assert plan["program_sha256"] == PROGRAM.digest
    assert plan["budget"]["max_tokens"] == 3000
    assert not PROGRAM.check()


@pytest.mark.skipif(sys.platform != "linux", reason="requires Linux seccomp")
def test_real_isolated_observation():
    wrapper = LoggedFactoryContrast(treatment=True)
    try:
        wrapper.prepare(None, {"observation_limit": 10000})
        assert wrapper.observe(1, "shell", {"command": "cat file"}, NEEDLE) == NEEDLE + NOTE
        assert wrapper.records[0]["visible_trigger"]
    finally:
        wrapper.close()
