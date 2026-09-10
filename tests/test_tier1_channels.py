"""Tier 1 surface declarations and conservative oracle dependency contracts."""

import pytest

from adversary.core.factors import Cell
from adversary.domain.channel import Channel, ReadSet, check_channel
from adversary.domain.perturbation import Perturbation
from adversary.execution.json_worker import JsonWorker
from domains.swe_agents.environment.readset import oracle_read_set


def test_transitive_src_imports_initializers_and_conftest_chain(tmp_path):
    files = {
        "tests/unit/test_main.py": "from pkg import api\n",
        "tests/__init__.py": "import test_support\n",
        "tests/conftest.py": "import fixtures\n",
        "conftest.py": "import root_fixture\n",
        "fixtures.py": "from pkg import fixture_helper\n",
        "root_fixture.py": "",
        "test_support.py": "",
        "src/pkg/__init__.py": "from . import initialization\n",
        "src/pkg/api.py": "from .nested import implementation\n",
        "src/pkg/initialization.py": "",
        "src/pkg/fixture_helper.py": "",
        "src/pkg/nested/__init__.py": "",
        "src/pkg/nested/implementation.py": "",
        "pyproject.toml": "",
        "uv.lock": "",
    }
    for name, contents in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
    read_set = oracle_read_set(tmp_path, ("tests/unit/test_main.py::test_main",))
    assert read_set.paths == frozenset(files)
    assert not read_set.complete
    assert not check_channel(
        Channel.WORKTREE_UNREAD, ("unrelated.txt",), read_set, confined=True
    ).accepted


def test_missing_and_linked_explicit_test_files_stay_protected(tmp_path):
    (tmp_path / "actual.py").write_text("pass\n")
    (tmp_path / "linked.py").symlink_to(tmp_path / "actual.py")
    read_set = oracle_read_set(tmp_path, ("missing.py::test_x",), ("linked.py::test_y",))
    assert {"missing.py", "linked.py"} <= read_set.paths
    assert not read_set.complete
    assert any("unresolved test file" in reason for reason in read_set.reasons)
    assert any("symlink" in reason for reason in read_set.reasons)


@pytest.mark.parametrize("channel", tuple(Channel))
def test_every_surface_requires_runtime_confinement(channel):
    result = check_channel(channel, (), ReadSet(complete=True), own_witness=True)
    assert not result.accepted
    assert not result.oracle_invariant


def test_task_text_own_witness_does_not_claim_inherited_oracle_invariance():
    result = check_channel(Channel.TASK_TEXT, (), ReadSet(), confined=True, own_witness=True)
    assert result.accepted
    assert result.witness_class == "own"
    assert not result.oracle_invariant


@pytest.mark.parametrize("clauses", ["x", ["x"], (["x"],), ("x", "x"), (" ",)])
def test_malformed_clause_declarations_rejected(clauses):
    class Intervention(Perturbation):
        channel = Channel.OBSERVATION

        def prepare(self, session, spec):
            pass

        def observe(self, step, tool, args, result):
            return result

    Intervention.clauses = clauses
    with pytest.raises(ValueError, match="clauses must"):
        Intervention(Cell(levels={"x": "on"}))


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), -float("inf"), 0, -1])
def test_worker_timeout_must_be_finite_positive(timeout):
    with pytest.raises(ValueError, match="finite and positive"):
        JsonWorker("adversary.probe.observation_worker", timeout)
