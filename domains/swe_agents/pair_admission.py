"""Executable observation admission, conditional on a trusted protected SWE oracle.

Receipt anchors are supplied by the harness operator, never by a proposed instance.
This orchestrator does not turn an unprotected replay into protected evidence.
"""

import re
import shlex
from pathlib import Path

from adversary.core.factors import Cell
from adversary.core.instance import Instance
from adversary.core.trajectory import Trajectory
from adversary.core.util import canonical_json, sha256_json
from adversary.domain.channel import Channel
from adversary.probe.observation import IsolatedObservation
from adversary.search.draft import ProbeDraft
from domains.swe_agents.environment.builder import SweEnvironmentBuilder
from domains.swe_agents.environment.oracle import SweDualOracle
from domains.swe_agents.environment.prun_receipts import load_prun_receipt
from domains.swe_agents.environment.spec import SweTaskSpec
from domains.swe_agents.runner import PairAdmission, PairEvidence, _paired_payload, pair_binding


class ObservationPairAdmission(PairAdmission):
    """Build two fresh gold arms and require identical complete passing verdicts.

    Only observation programs with an all-off control are executable here. Their kernel
    worker receives no session or verifier inputs. A prepare-only gate establishes the
    surface. It does not establish activation or a recovery witness for a target trajectory.
    The protected evaluator must independently establish its capability; the bundled
    unprotected replay refuses before either arm is built.
    """

    def __init__(self, builder: SweEnvironmentBuilder, *, task_receipts: Path,
                 trusted_manifest_sha256: str, corpus: str, receipts: Path) -> None:
        self.builder = builder
        self.task_receipts = Path(task_receipts)
        self.anchor = trusted_manifest_sha256
        self.corpus = corpus
        self.receipts = Path(receipts)

    def _persist(self, payload: dict) -> str:
        address = sha256_json(payload)
        self.receipts.mkdir(parents=True, exist_ok=True)
        path = self.receipts / (address + ".json")
        text = canonical_json(payload)
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(text)
        except FileExistsError:
            if path.read_text() != text:
                raise ValueError("admission receipt address collision or corruption") from None
        return address

    def check(self, draft: ProbeDraft, instances: tuple[Instance, Instance]) -> PairEvidence:
        draft = ProbeDraft.model_validate(draft.model_dump())
        if draft.channel is not Channel.OBSERVATION:
            raise ValueError("only observation admission is implemented")
        if len(instances) != 2 or _paired_payload(instances[0]) != _paired_payload(instances[1]):
            raise ValueError("admission requires a matched pair")
        if any(level != "off" for level in draft.pair.control.levels.values()):
            raise ValueError("gold invariance requires an all-off clean control")
        frozen = pair_binding(draft, instances)
        # Reload and verify actual receipt contents on every check. A pin's bare hash
        # cannot establish that the task was executed by the trusted producer.
        pins, _ = load_prun_receipt(self.task_receipts, self.anchor, self.corpus)
        for instance, cell in zip(
            instances, (draft.pair.control, draft.pair.treatment), strict=True
        ):
            spec = SweTaskSpec.model_validate(instance.spec)
            if (draft.seed is None or draft.seed.instance_id != spec.pin.key
                    or draft.seed.base_commit != spec.pin.commit
                    or draft.seed.repo != spec.pin.repo):
                raise ValueError("draft seed differs from authenticated task")
            if (spec.pin not in pins or spec.perturbation != draft.perturbation
                    or spec.perturbation_clauses != draft.clauses
                    or instance.cell != cell or spec.clause_cell != cell):
                raise ValueError("arm differs from authenticated task or declared program")
            unbound = spec.model_copy(update={
                "perturbation": None, "perturbation_clauses": (), "clause_cell": Cell(levels={}),
            })
            rebound = self.builder.materialize(
                draft, instance.model_copy(update={"spec": unbound})
            )
            if rebound.model_dump(mode="json") != instance.model_dump(mode="json"):
                raise ValueError("arm differs from trusted materialization")
            self.builder.require_protected(instance)
        sessions, rows = [], []
        for instance in instances:
            with self.builder.build(instance) as environment:
                session = environment.session
                if any(session is previous for previous in sessions):
                    raise ValueError("admission runtime reused an arm session")
                sessions.append(session)
                observer = environment.perturbation
                if not isinstance(observer, IsolatedObservation):
                    raise ValueError("admission requires the kernel observation worker")
                observer.prepare(None, environment.spec.model_dump(exclude={"pin"}))
                oracle = environment.final_oracle
                if oracle is None:
                    raise ValueError("admission requires a protected evaluator")
                oracle.require_protected()
                patch = environment.oracle.gold_patch
                if not patch:
                    raise ValueError("gold admission requires a nonempty trusted patch")
                code, path, _ = session.exec("mktemp /tmp/pcode-gold-XXXXXXXX", 30)
                path = path.strip()
                if code or not re.fullmatch(r"/tmp/pcode-gold-[A-Za-z0-9]+", path):
                    raise ValueError("gold patch transport failed")
                session.write_file(path, patch)
                for command in ("git apply --check -- ", "git apply -- ", "rm -- "):
                    code, _, error = session.exec(command + shlex.quote(path), 60)
                    if code:
                        raise ValueError("gold build failed: " + error[-1000:])
                state = oracle.evaluate(session)
                trajectory = Trajectory(instance_id=instance.id, model_id="trusted-gold",
                                        messages=(), final_state=state)
                verdict = SweDualOracle().verify(trajectory, environment.oracle)
                if not verdict.passed:
                    raise ValueError("gold arm did not pass every verdict channel")
                rows.append({"instance": instance.model_dump(mode="json"),
                             "state": state, "verdict": verdict.model_dump(mode="json")})
        if rows[0]["verdict"] != rows[1]["verdict"]:
            raise ValueError("gold verdicts differ across the full pair")
        if pair_binding(draft, instances) != frozen:
            raise ValueError("admission inputs mutated during evaluation")
        common = {"binding": frozen, "task_manifest": self.anchor, "corpus": self.corpus}
        channel = self._persist({**common, "kind": "observation-channel-build",
                                 "draft": draft.model_dump(mode="json"),
                                 "scope": "kernel-confined prepare in two fresh built arms"})
        gold = self._persist({**common, "kind": "gold-invariance", "arms": rows})
        return PairEvidence(binding=frozen, channel_receipt=channel, gold_invariance_receipt=gold)
