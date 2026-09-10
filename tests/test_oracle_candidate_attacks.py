"""Executable candidate attack evidence; diagnostic replay never earns protected admission."""

# ruff: noqa: F811

import shlex
import sys

import pytest

from adversary.core.trajectory import Budget
from domains.swe_agents.environment.environment import SweEnvironment
from domains.swe_agents.environment.protected_oracle import FreshReplayOracle
from domains.swe_agents.environment.runtime import RuntimeUnavailable
from domains.swe_agents.environment.spec import SweTaskSpec
from tests.test_protected_oracle import LocalSession, patch_for, replay  # noqa: F401


def test_import_can_rewrite_protected_test_then_forge_diagnostic_success(replay):
    # The patch changes only an allowed candidate module. Its later import has the
    # same filesystem identity as the verifier and rewrites a protected file.
    trusted_test = (
        "from pathlib import Path\n"
        "import api\n"
        "Path('intended-assertion-reached').write_text('yes')\n"
        "assert api.answer == 1\n"
    )
    test_patch = patch_for(replay, "tests/test_api.py", trusted_test)
    script = "import api, runpy; runpy.run_path('tests/test_api.py')"
    command = shlex.quote(sys.executable) + " -c " + shlex.quote(script)
    pin = replay.pin.model_copy(update={"test_patch": test_patch, "test_command": command})
    oracle = replay.oracle.model_copy(update={"test_command": command})
    diagnostic = FreshReplayOracle(replay.runtime, pin, oracle)
    replacement = "print('PASSED tests/test_api.py::test_answer')\n"
    candidate = (
        "from pathlib import Path\n"
        "answer = 0\n"
        f"Path('tests/test_api.py').write_text({replacement!r})\n"
    )
    patch = patch_for(replay, "api.py", candidate)
    assert "diff --git a/tests/" not in patch

    # Control: the intended assertion executes and fails without the attack.
    control = diagnostic.evaluate_patch("")
    assert control["test_results"]["exit"] == 1
    assert (replay.runtime.sessions[0].root / "intended-assertion-reached").is_file()

    state = diagnostic.evaluate_patch(patch)
    fresh = replay.runtime.sessions[1]
    assert state["test_results"]["exit"] == 0
    assert state["test_results"]["stdout"] == "PASSED tests/test_api.py::test_answer\n"
    assert (fresh.root / "tests/test_api.py").read_text() == replacement
    assert not (fresh.root / "intended-assertion-reached").exists()
    assert "answer = 0" in (fresh.root / "api.py").read_text()
    assert state["oracle_replay"]["changed_paths"] == ["api.py"]
    assert state["oracle_replay"]["kind"] == "fresh_replay_unisolated"
    assert fresh.closed
    assert (replay.runtime.base / "tests/test_api.py").read_text() == "assert True\n"

    # Even after this plausible success, normal environment admission must refuse
    # before model access, export, or another diagnostic session is started.
    calls = []

    class NoInference:
        def complete(self, *args, **kwargs):
            calls.append("model")
            raise AssertionError("protected admission must precede inference")

    def exporter(_):
        calls.append("export")
        return patch

    diagnostic.export_patch = exporter
    environment = SweEnvironment(
        "fixture",
        SweTaskSpec(pin=pin, canary="fixture"),
        oracle,
        LocalSession(replay.runtime.base),
        final_oracle=diagnostic,
        require_protected_oracle=True,
    )
    with pytest.raises(RuntimeUnavailable, match="not a protected oracle"):
        environment.run(NoInference(), Budget(max_steps=1))
    assert calls == []
    assert len(replay.runtime.sessions) == 2
