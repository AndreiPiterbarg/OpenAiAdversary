"""Request/receipt contract checks without model calls or host launches."""

import json
import time

import pytest

from adversary.core.model import Completion, CompletionRequest, Message, Usage
from domains.swe_agents.scripts import interactive_episode as module


def test_host_pin_requires_explicit_distinct_runtime_metadata():
    value = dict(
        task_key="task",
        commit="a" * 40,
        repository="/tmp/repo",
        repository_sha256="b" * 64,
        venv="/tmp/venv",
        venv_sha256="c" * 64,
        system_python="/usr/bin/python3",
        prepared_frozen_tests=True,
        original_container_equivalence=False,
    )
    pin = module.load_host_pin(value)
    assert str(pin.venv) == "/tmp/venv"
    for field, wrong in [
        ("prepared_frozen_tests", False),
        ("original_container_equivalence", True),
    ]:
        with pytest.raises(ValueError, match="distinct host runtime"):
            module.load_host_pin({**value, field: wrong})


def test_target_projects_exact_request_and_records_fixed_sampling(tmp_path, monkeypatch):
    seen = []

    def project(request, url, model, *, deadline):
        assert request.temperature == 0.2 and request.seed == 42
        assert request.reasoning_effort is None and request.max_tokens == 1024
        assert deadline > time.monotonic()
        return request, {"exact": True, "prompt_tokens": 10}

    class Model:
        def __init__(self, **kwargs):
            assert kwargs["timeout_seconds"] > 0

        def complete(self, request):
            seen.append(request)
            return Completion(
                message=Message(role="assistant", content="done"),
                usage=Usage(input_tokens=10, output_tokens=1),
            )

    monkeypatch.setattr(module, "fit_context", project)
    monkeypatch.setattr(module, "DevstralModel", Model)
    model = module.ProjectedTarget(
        "http://localhost/v1", tmp_path / "model", 42, lambda: time.perf_counter() + 10
    )
    result = model.complete(
        CompletionRequest(messages=(Message(role="user", content="fix"),), max_tokens=1024)
    )
    assert result.message.content == "done" and len(seen) == 1
    assert model.calls == model.completed_calls == 1
    assert json.loads((tmp_path / "model/call-0001.projection.json").read_text())["exact"]
    assert json.loads((tmp_path / "current-usage.json").read_text())["output_tokens"] == 1


def test_expired_request_keeps_error_receipt_without_inference(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "fit_context", lambda *a, **k: pytest.fail("must not project"))
    model = module.ProjectedTarget(
        "http://localhost/v1", tmp_path / "model", 1, lambda: time.perf_counter() - 1
    )
    with pytest.raises(TimeoutError):
        model.complete(
            CompletionRequest(messages=(Message(role="user", content="fix"),), max_tokens=1024)
        )
    assert (tmp_path / "model/call-0001.error.json").exists()
    assert model.completed_calls == 0


def test_guidance_legacy_is_byte_identical_and_new_profile_has_no_solution_material():
    from types import SimpleNamespace

    pin = SimpleNamespace(
        test_command="pytest -rA tests/test_public.py",
        gold_patch="SECRET_GOLD",
        issue="SECRET_ISSUE",
    )
    legacy = (
        "Resolve the issue using the existing environment. Preserve the tests. "
        "Run tests to check your work. Network and installing dependencies are disabled. "
        "Final evaluation replays tracked and untracked code changes against fresh "
        "frozen tests; generated caches and declared reports are recorded separately."
    )
    assert module.task_guidance(pin) == legacy
    assert module.task_guidance(pin, "legacy") == legacy
    guidance = module.task_guidance(pin, "environment_guidance_v1")
    for text in (
        pin.test_command,
        "$TMPDIR",
        "set -o pipefail",
        "immutable",
        "new files",
        "bounded line ranges",
    ):
        assert text in guidance
    assert "SECRET_GOLD" not in guidance and "SECRET_ISSUE" not in guidance
    assert "supplementary" not in guidance and "locale" not in guidance
    with pytest.raises(ValueError, match="prompt profile"):
        module.task_guidance(pin, "unknown")


@pytest.mark.parametrize("budget_profile", ["standard", "extended_diagnostic"])
def test_profile_and_guidance_digest_are_recorded_before_runtime(
    tmp_path, monkeypatch, budget_profile
):
    import hashlib
    from types import SimpleNamespace

    pin = SimpleNamespace(key="test", commit="a" * 40, test_command="pytest -q")
    hp = SimpleNamespace(task_key=pin.key, commit=pin.commit)

    def refuse(*args, **kwargs):
        raise module.RuntimeUnavailable("fixture stops before commands")

    monkeypatch.setattr(
        module, "InteractiveRuntime", lambda hp: SimpleNamespace(start_guarded=refuse)
    )
    out = tmp_path / "episode"
    result = module.run_episode(
        pin=pin,
        host_pin=hp,
        prepared_ref="b" * 40,
        base_url="http://127.0.0.1:1/v1",
        perturbation=None,
        output=out,
        episode_id="fixture",
        seed=1,
        host_nproc=128,
        prompt_profile="environment_guidance_v1",
        budget_profile=budget_profile,
        max_steps=module.episode_budget(budget_profile)[0],
        max_seconds=module.episode_budget(budget_profile)[1],
    )
    metadata = json.loads((out / "metadata.json").read_text())
    assert metadata["prompt_profile"] == "environment_guidance_v1"
    assert (
        metadata["prompt_sha256"]
        == hashlib.sha256(module.task_guidance(pin, "environment_guidance_v1").encode()).hexdigest()
    )
    assert metadata["budget_profile"] == budget_profile
    assert (
        metadata["budget"]["max_steps"],
        metadata["budget"]["max_seconds"],
    ) == module.episode_budget(budget_profile)
    assert result["status"] == "unknown"


def test_named_live_budgets_and_explicit_api_override():
    assert module.episode_budget("standard") == (100, 600)
    assert module.episode_budget("extended_diagnostic") == (160, 900)
    for profile, steps, seconds in [("standard", 100, 600), ("extended_diagnostic", 160, 900)]:
        module.validate_episode_budget(profile, steps, seconds, model_override=False)
        with pytest.raises(ValueError, match="differs"):
            module.validate_episode_budget(profile, steps + 1, seconds, model_override=False)
    with pytest.raises(ValueError, match="unsupported"):
        module.validate_episode_budget("unknown", 100, 600, model_override=True)
    module.validate_episode_budget("standard", 20, 600, model_override=True)
