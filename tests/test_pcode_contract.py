"""The v2 proposal contract and conservative channel boundary."""

import json

import pytest

from adversary.core.model import CompletionRequest, Message
from adversary.domain.channel import Channel, ReadSet, check_channel
from adversary.execution.backends.scripted import ScriptedModel
from adversary.probe.executor import ProgramExecutor
from adversary.search.context import MinedSeed, SearchContext
from adversary.search.critic import Reason, StaticCritic
from adversary.search.proposer import LLMProposer, ProposalError, parse_draft, render_context
from domains.swe_agents.environment.readset import oracle_read_set
from domains.swe_agents.mining.store import SeedStore

SEED = MinedSeed(
    instance_id="task",
    repo="org/project",
    base_commit="a" * 40,
    miner="ci_drift",
    sha="b" * 40,
    ts=42,
    subject="historical change",
)
CONFIG = {
    "spec": {"task": "fixed task"},
    "oracle": {"answer": 42},
    "resource": "org/project",
    "source_license": "MIT",
}
GEN = """class G(Generator):
    def __next__(self):
        seed = self.next_seed()
        return Instance(id=str(seed), seed=seed, cell=self.cell,
            spec=self.config['spec'], oracle=self.config['oracle'],
            resource=self.config['resource'],
            provenance=Provenance(generator=self.identity, generator_version=self.version,
                seed=seed, source_license=self.config['source_license']))
"""
PERT = """class P(Perturbation):
    channel = Channel.OBSERVATION
    clauses = ('rewrite',)
    def prepare(self, session, spec):
        pass
    def observe(self, step, tool, args, result):
        return result + ' adapted' if 'rewrite' in self.active else result
"""
VER = """class V(Verifier):
    def verify(self, trajectory, oracle):
        return Verdict(passed=False)
"""


def raw_draft():
    return {
        "schema_version": 2,
        "hypothesis": "a historical pattern confuses the target",
        "seed": SEED.model_dump(),
        "channel": "observation",
        "clauses": ["rewrite"],
        "pair": {"control": {"rewrite": "off"}, "treatment": {"rewrite": "on"}},
        "prediction": {"min_effect": 0.1, "alpha": 0.05, "statement": "testable"},
        "generator": {"entrypoint": "G", "source": GEN},
        "perturbation": {"entrypoint": "P", "source": PERT},
        "verifier": {"entrypoint": "V", "source": VER},
    }


def test_v2_parses_after_reasoning_and_retains_three_programs():
    draft = parse_draft(
        '<think>{"noise": {}}</think>```json\n' + json.dumps(raw_draft()) + "\n```", None
    )
    assert draft.seed == SEED and draft.channel == Channel.OBSERVATION
    assert (
        StaticCritic(generator_config=CONFIG, executor=ProgramExecutor()).critique(draft).accepted
    )
    probe = draft.to_probe("")
    assert probe.perturbation == draft.perturbation
    assert probe.seed == SEED.model_dump()
    modified = draft.model_copy(
        update={
            "perturbation": draft.perturbation.model_copy(
                update={"source": PERT + "\n# a new program"}
            )
        }
    ).to_probe("")
    assert modified.id != probe.id


@pytest.mark.parametrize(
    "change",
    [
        {"cell": {"old": "menu"}},
        {"schema_version": 1},
        {"unknown": 1},
        {"clauses": []},
        {"clauses": ["rewrite", "rewrite"]},
        {"pair": {"control": {"rewrite": "off"}, "treatment": {"rewrite": "unknown"}}},
    ],
)
def test_v2_rejects_old_or_ambiguous_shape(change):
    with pytest.raises(ProposalError):
        parse_draft(json.dumps({**raw_draft(), **change}), None)


def test_static_critic_rejects_missing_grounding_mismatched_declaration_and_payload_drift():
    draft = parse_draft(json.dumps(raw_draft()), None)
    assert not StaticCritic().critique(draft).accepted
    bad = draft.model_copy(update={"channel": Channel.TASK_TEXT})
    assert (
        not StaticCritic(generator_config=CONFIG, executor=ProgramExecutor()).critique(bad).accepted
    )
    raw = raw_draft()
    raw["generator"]["source"] = GEN.replace(
        "spec=self.config['spec']", "spec={'invented': 'task'}"
    )
    result = StaticCritic(generator_config=CONFIG, executor=ProgramExecutor()).critique(
        parse_draft(json.dumps(raw), None)
    )
    assert not result.accepted and any("trusted spec" in o.detail for o in result.objections)
    raw = raw_draft()
    # Same ids, different full payloads: the old id-only test missed this.
    raw["generator"]["source"] = GEN.replace(
        "spec=self.config['spec']", "spec={'n': random.random()}"
    )
    result = StaticCritic(generator_config=CONFIG, executor=ProgramExecutor()).critique(
        parse_draft(json.dumps(raw), None)
    )
    assert any(o.reason == Reason.NONDETERMINISM for o in result.objections)


def test_proposer_grounding_and_decoding_reach_model():
    calls: list[CompletionRequest] = []

    def policy(request):
        calls.append(request)
        return Message(role="assistant", content=json.dumps(raw_draft()))

    proposer = LLMProposer(ScriptedModel(policy))
    with pytest.raises(ProposalError, match="mined seed"):
        proposer.propose(SearchContext())
    assert not calls
    context = SearchContext(mined_seed=SEED, operator_register=("op",), transcripts=("failure",))
    assert SEED.model_dump_json() in render_context(context)
    assert context.stripped().mined_seed == SEED and not context.stripped().transcripts
    proposer.propose(context)
    proposer.propose(context)
    assert [c.seed for c in calls] == [0, 1]
    assert all(c.temperature == 1 and c.top_p == 0.95 and c.top_k == 20 for c in calls)
    assert calls[0].chat_template_kwargs == {"enable_thinking": False}
    with pytest.raises(ProposalError, match="changed"):
        proposer.propose(SearchContext(mined_seed=SEED.model_copy(update={"subject": "different"})))


def test_seed_store_binds_task_and_base(tmp_path):
    path = tmp_path / "seeds.jsonl"
    path.write_text(SEED.model_dump_json() + "\n")
    store = SeedStore.from_jsonl(path)
    assert store.matching("task", "a" * 40) == (SEED,)
    assert not store.matching("task", "c" * 40)
    assert not store.matching("other", "a" * 40)
    path.write_text(path.read_text() * 2)
    with pytest.raises(ValueError, match="duplicate"):
        SeedStore.from_jsonl(path)


def test_readset_follows_relative_imports_initializers_conftest_and_manifests(tmp_path):
    files = {
        "tests/test_x.py": "from pkg import api\n",
        "tests/conftest.py": "import helpers\n",
        "helpers.py": "import pkg.util\n",
        "conftest.py": "",
        "src/pkg/__init__.py": "from . import util\n",
        "src/pkg/api.py": "from .util import f\n",
        "src/pkg/util.py": "def f(): pass\n",
        "pyproject.toml": "",
        "uv.lock": "",
        "README.md": "data",
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    result = oracle_read_set(tmp_path, ("tests/test_x.py::test_run",))
    assert set(files) - {"README.md"} <= result.paths
    assert not result.complete
    # A test may read README despite no import edge; static closure cannot authorize this edit.
    check = check_channel(Channel.WORKTREE_UNREAD, ["README.md"], result, confined=True)
    assert not check.accepted and "oracle read set is incomplete" in check.reasons
    (tmp_path / "tests/test_x.py").write_text("open('README.md').read()\n")
    assert not oracle_read_set(tmp_path, ("tests/test_x.py",)).complete


@pytest.mark.parametrize(
    "path", ["../oracle", "/oracle", "a/../oracle", "./oracle", "a//b", "a\\b"]
)
def test_channel_rejects_ambiguous_paths(path):
    assert not check_channel(
        Channel.WORKTREE_UNREAD, [path], ReadSet(complete=True), confined=True
    ).accepted


def test_channel_overlap_confinement_and_witness_requirements():
    readset = ReadSet(paths=frozenset({"tests/a.py"}), complete=True)
    for path in ("tests/a.py", "tests", "tests/a.py/subpath"):
        assert not check_channel(Channel.WORKTREE_UNREAD, [path], readset, confined=True).accepted
    assert check_channel(Channel.WORKTREE_UNREAD, ["docs/notes"], readset, confined=True).accepted
    assert not check_channel(Channel.OBSERVATION, [], readset).accepted
    assert not check_channel(Channel.OBSERVATION, ["other"], readset, confined=True).accepted
    assert check_channel(Channel.OBSERVATION, [], ReadSet(), confined=True).oracle_invariant
    assert not check_channel(Channel.TASK_TEXT, [], readset, confined=True).accepted
    own = check_channel(Channel.TASK_TEXT, [], readset, confined=True, own_witness=True)
    assert own.accepted and not own.oracle_invariant


def test_generator_cannot_mutate_the_critics_trusted_inputs():
    raw = raw_draft()
    raw["generator"]["source"] = GEN.replace(
        "seed = self.next_seed()",
        "seed = self.next_seed()\n        self.config['spec']['task'] = 'forged'",
    )
    critic = StaticCritic(generator_config=CONFIG, executor=ProgramExecutor())
    result = critic.critique(parse_draft(json.dumps(raw), None))
    assert not result.accepted
    assert critic.generator_config["spec"]["task"] == "fixed task"
    assert CONFIG["spec"]["task"] == "fixed task"


def test_non_instance_output_is_rejected_without_escaping_critic():
    raw = raw_draft()
    raw["generator"]["source"] = "class G(Generator):\n    def __next__(self): return object()\n"
    assert (
        not StaticCritic(generator_config=CONFIG, executor=ProgramExecutor())
        .critique(parse_draft(json.dumps(raw), None))
        .accepted
    )


def test_legacy_runner_cannot_silently_drop_the_third_program():
    from adversary.search.falsify import Falsifier
    from adversary.search.loop import SearchConfig, SearchLoop

    model = ScriptedModel()
    probe = parse_draft(json.dumps(raw_draft()), None).to_probe("")
    # Refusal occurs before any legacy space, harness or target access.
    with pytest.raises(RuntimeError, match="third program"):
        Falsifier(None, None)._arm(probe, "treatment", model, 0)
    with pytest.raises(RuntimeError, match="v2 search refused"):
        SearchLoop(None, None, None, None, None).run(
            SearchContext(mined_seed=SEED), model, SearchConfig()
        )
    assert model.calls == 0


def test_mutation_preserves_third_program_context_and_seed():
    from adversary.search.mutator import LLMMutator

    calls = []

    def policy(request):
        calls.append(request)
        return Message(role="assistant", content=json.dumps(raw_draft()))

    parent = parse_draft(json.dumps(raw_draft()), None).to_probe("")
    mutator = LLMMutator(ScriptedModel(policy))
    child = mutator.mutate(parent, SearchContext(mined_seed=SEED))
    assert child.parent_id == parent.id
    assert PERT in calls[0].messages[0].content
    assert calls[0].temperature == 1 and calls[0].chat_template_kwargs == {"enable_thinking": False}
    with pytest.raises(ProposalError, match="changed"):
        mutator.mutate(parent, SearchContext(mined_seed=SEED.model_copy(update={"subject": "new"})))
