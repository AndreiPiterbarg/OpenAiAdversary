"""Construction checks must precede allocation and must retain the third program."""

import pytest

from adversary.core.factors import Cell
from adversary.core.instance import Instance, Provenance
from domains.swe_agents.environment.builder import SweEnvironmentBuilder
from domains.swe_agents.environment.generator import TaskPool
from tests.test_domain_swe import FakeSession, make_spec
from tests.test_observation import program


class Runtime:
    def __init__(self):
        self.calls = []

    def start(self, image, url, commit):
        self.calls.append((image, url, commit))
        return FakeSession()


def setup():
    spec, oracle = make_spec()
    instance = Instance(
        id="i",
        cell=Cell(levels={}),
        seed=13,
        spec=spec,
        oracle=oracle,
        provenance=Provenance(generator="test", generator_version="1", seed=13),
    )
    runtime = Runtime()
    builder = SweEnvironmentBuilder(runtime=runtime, pool=TaskPool(pins=(spec.pin,)))
    return instance, runtime, builder


def test_no_implicit_pool_or_retired_envelope():
    with pytest.raises(ValueError, match="explicit runtime"):
        SweEnvironmentBuilder()
    with pytest.raises(ValueError, match="retired"):
        SweEnvironmentBuilder(envelope="full")


def test_explicit_build_has_no_factor_space_file_dependency():
    instance, runtime, builder = setup()
    env = builder.build(instance)
    assert env.spec == instance.spec
    assert len(runtime.calls) == 1
    env.close()
    with pytest.raises(ValueError, match="generator factory"):
        builder.generator(Cell(levels={}), 1)


def test_changed_pin_and_oracle_are_rejected_before_allocation():
    instance, runtime, builder = setup()
    for change in (
        {
            "spec": instance.spec.model_copy(
                update={"pin": instance.spec.pin.model_copy(update={"commit": "f" * 40})}
            )
        },
        {"oracle": instance.oracle.model_copy(update={"test_command": "true"})},
        {"oracle": instance.oracle.model_copy(update={"pass_to_pass": ("invented",)})},
    ):
        with pytest.raises(ValueError, match="trusted pool pin"):
            builder.build(instance.model_copy(update=change))
    assert runtime.calls == []


def test_seed_config_and_clauses_bind_to_a_fresh_observer_per_episode():
    instance, runtime, builder = setup()
    source = program("return result + self.config['suffix']")
    spec = instance.spec.model_copy(
        update={
            "perturbation": source,
            "perturbation_clauses": ("rewrite",),
            "clause_cell": Cell(levels={"rewrite": "on"}),
        }
    )
    instance = instance.model_copy(update={"spec": spec, "perturbation_config": {"suffix": "x"}})
    first, second = builder.build(instance), builder.build(instance)
    assert first.perturbation is not second.perturbation
    assert first.perturbation.program == source
    assert first.perturbation.seed == 13
    assert first.perturbation.config == {"suffix": "x"}
    first.close()
    second.close()


def test_unbound_intervention_data_refused_before_allocation():
    instance, runtime, builder = setup()
    with pytest.raises(ValueError, match="requires a perturbation"):
        builder.build(instance.model_copy(update={"perturbation_config": {"suffix": "x"}}))
    assert not runtime.calls


def test_gold_patch_text_alone_cannot_certify_solvability():
    from domains.swe_agents.reference.solver import SweReference

    instance, runtime, builder = setup()
    instance = instance.model_copy(
        update={"oracle": instance.oracle.model_copy(update={"gold_patch": "unexecuted patch"})}
    )
    certificate = SweReference(builder).certify(instance)
    assert not certificate.clean_passed
    assert "not evidence" in certificate.evidence
    assert not runtime.calls


@pytest.mark.parametrize("fail_apply", [False, True])
def test_verified_test_patch_prepares_baseline_and_cleanup(tmp_path, fail_apply):
    from domains.swe_agents.environment.gold import digest

    instance, _, _ = setup()
    image = tmp_path / "image.sqsh"
    image.write_bytes(b"image")
    pin = instance.spec.pin.model_copy(
        update={
            "image": str(image),
            "image_sha256": digest(image),
            "test_patch": "test diff",
            "workdir": "/testbed",
            "python_env": "conda_testbed",
        }
    )
    instance = instance.model_copy(update={"spec": instance.spec.model_copy(update={"pin": pin})})

    class PreparedSession(FakeSession):
        stopped = False
        checkpointed = False
        writes = []

        def exec(self, command, timeout):
            self.commands.append(command)
            if command.startswith("mktemp"):
                return 0, "/tmp/pcode-test-abcdefgh.patch\n", ""
            if fail_apply and command.startswith("git apply"):
                return 1, "", "cannot apply"
            return 0, "", ""

        def write_file(self, path, content):
            self.writes.append((path, content))

        def checkpoint(self):
            self.checkpointed = True

        def stop(self):
            self.stopped = True

    session = PreparedSession()

    class Runtime:
        def start(self, image, url, commit, **options):
            assert options == {"workdir": "/testbed", "python_env": "conda_testbed"}
            return session

    builder = SweEnvironmentBuilder(runtime=Runtime(), pool=TaskPool(pins=(pin,)))
    if fail_apply:
        with pytest.raises(ValueError, match="test patch setup failed"):
            builder.build(instance)
        assert session.stopped and not session.checkpointed
    else:
        environment = builder.build(instance)
        assert session.checkpointed
        assert session.writes[-1][1] == "test diff"
        environment.close()
        assert session.stopped


def test_builder_rejects_image_modified_after_pool_load(tmp_path):
    instance, runtime, _ = setup()
    image = tmp_path / "image.sqsh"
    image.write_bytes(b"modified")
    pin = instance.spec.pin.model_copy(update={"image": str(image), "image_sha256": "0" * 64})
    instance = instance.model_copy(update={"spec": instance.spec.model_copy(update={"pin": pin})})
    builder = SweEnvironmentBuilder(runtime=runtime, pool=TaskPool(pins=(pin,)))
    with pytest.raises(ValueError, match="image differs"):
        builder.build(instance)
    assert not runtime.calls
