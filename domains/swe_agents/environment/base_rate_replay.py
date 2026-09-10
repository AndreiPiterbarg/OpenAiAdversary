"""Guarded fresh frozen-test diagnostics, explicitly not protected final verdicts."""

from __future__ import annotations

import configparser
import hashlib
import json
import re
import shlex
import tomllib
from collections.abc import Callable
from typing import Any

from adversary.domain.channel import relative_path
from domains.swe_agents.environment.artifact_delta import (
    apply_untracked_deltas,
    artifact_digest,
    omission_reason,
    read_delta_contents,
    same_fingerprint,
    validate_artifact,
)
from domains.swe_agents.environment.factory_postcheck import prepare_task_post_check
from domains.swe_agents.environment.guarded_session import install_guard
from domains.swe_agents.environment.protected_oracle import (
    CandidatePatchRejected,
    FreshReplayOracle,
)
from domains.swe_agents.environment.prun_contract import parse_pytest_summary
from domains.swe_agents.environment.runtime import ContainerRuntime, RuntimeUnavailable, Session
from domains.swe_agents.environment.spec import SweOracle, TaskPin
from domains.swe_agents.environment.test_results import TestEvidence, TestStatus


def _checked(session: Session, command: str, timeout: float = 60) -> str:
    code, out, err = session.exec(command, timeout)
    if code:
        raise RuntimeUnavailable("diagnostic replay command failed: " + err[-1000:])
    return out


_UNTRACKED_CAPTURE = """import hashlib,json,os,pathlib,stat,subprocess
# Git omits FIFOs/sockets; detect them independently without ever opening them.
visited=0
for parent,dirs,names in os.walk('.',followlinks=False):
 dirs[:]=[name for name in dirs if name!='.git']
 for name in names:
  visited+=1
  if visited>100000: raise ValueError('repository traversal exceeds bound')
  mode=os.lstat(os.path.join(parent,name)).st_mode
  if not (stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
   raise ValueError('nonregular repository file')
raw=subprocess.check_output(['git','ls-files','--others','-z'])
paths=[os.fsdecode(p) for p in raw.split(b'\\0') if p]
if len(paths)>10000: raise ValueError('untracked file count exceeds bound')
result={}; total=0
for name in paths:
 p=pathlib.Path(name)
 if p.is_absolute() or '..' in p.parts: raise ValueError('unsafe untracked path')
 if any(q.is_symlink() for q in (p,*p.parents)): raise ValueError('linked untracked path')
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as handle:
  before=os.fstat(handle.fileno())
  if not stat.S_ISREG(before.st_mode): raise ValueError('nonregular untracked path')
  total+=before.st_size
  if before.st_size>33554432 or total>268435456: raise ValueError('untracked bytes exceed bound')
  digest=hashlib.sha256(); size=0
  for chunk in iter(lambda:handle.read(1048576),b''):
   size+=len(chunk)
   if size>33554432: raise ValueError('growing untracked file')
   digest.update(chunk)
  after=os.fstat(handle.fileno())
  if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
   raise ValueError('untracked file changed while fingerprinting')
 result[name]={'sha256':digest.hexdigest(),'size':size,'mode':stat.S_IMODE(before.st_mode)}
print(json.dumps(result,sort_keys=True))
"""


def capture_untracked(session: Session) -> dict[str, dict[str, Any]]:
    """Fingerprint ignored and ordinary untracked regular files, with explicit read bounds."""
    value = json.loads(_checked(session, "python -I -B -c " + shlex.quote(_UNTRACKED_CAPTURE), 120))
    if type(value) is not dict:
        raise RuntimeUnavailable("invalid untracked fingerprint map")
    for path, entry in value.items():
        relative_path(path)
        if (
            type(entry) is not dict
            or set(entry) != {"sha256", "size", "mode"}
            or type(entry["size"]) is not int
            or entry["size"] < 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(entry["sha256"]))
        ):
            raise RuntimeUnavailable("invalid untracked fingerprint entry")
    return value


def declared_report_paths(frozen_config: dict[str, str]) -> tuple[str, ...]:
    """Recognize a narrow set of report outputs from captured pre-model pytest addopts."""
    options = []
    # Follow pytest's precedence; only the first applicable config contributes options.
    for name in ("pytest.ini", ".pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg"):
        if name not in frozen_config:
            continue
        if name == "pyproject.toml":
            section = (
                tomllib.loads(frozen_config[name])
                .get("tool", {})
                .get("pytest", {})
                .get("ini_options")
            )
            if section is None:
                continue
            value = section.get("addopts", "")
            options = value if isinstance(value, list) else shlex.split(value)
        else:
            parser = configparser.ConfigParser(interpolation=None)
            parser.read_string(frozen_config[name])
            section = "tool:pytest" if name == "setup.cfg" else "pytest"
            if not parser.has_section(section):
                continue
            options = shlex.split(parser.get(section, "addopts", fallback=""))
        break
    reports = set()
    for index, option in enumerate(options):
        if option in {"--junitxml", "--junit-xml"}:
            value = options[index + 1] if index + 1 < len(options) else ""
            if value.removeprefix("./") == "pytest.xml":
                reports.add("pytest.xml")
        elif option in {
            "--junitxml=pytest.xml",
            "--junit-xml=pytest.xml",
            "--junitxml=./pytest.xml",
            "--junit-xml=./pytest.xml",
        }:
            reports.add("pytest.xml")
        if option == "--cov" or option.startswith("--cov="):
            reports.add(".coverage")
        report = (
            options[index + 1]
            if option == "--cov-report" and index + 1 < len(options)
            else (
                option.removeprefix("--cov-report=") if option.startswith("--cov-report=") else ""
            )
        )
        if report in {"xml", "xml:coverage.xml"}:
            reports.add("coverage.xml")
        if report in {"html", "html:htmlcov"}:
            reports.add("htmlcov/")
    return tuple(sorted(reports))


def capture_candidate_artifact(
    source_session: Session,
    prepared_ref: str,
    *,
    baseline_untracked: dict[str, dict[str, Any]] | None = None,
    generated_report_paths: tuple[str, ...] = (),
    record_evidence: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Capture complete bounded code deltas; save bytes before admission validation."""
    if not re.fullmatch(r"[0-9a-f]{40}", prepared_ref):
        raise ValueError("prepared baseline must be an immutable full Git commit")
    patch = _checked(
        source_session,
        "git -c core.quotePath=false diff --no-ext-diff --no-textconv --binary "
        + prepared_ref
        + " --",
    )
    baseline = baseline_untracked or {}
    artifact = {
        "kind": "bounded_code_artifact_v1",
        "phase": "artifact_export",
        "prepared_ref": prepared_ref,
        "tracked_patch": patch,
        "patch": patch,
        "baseline_untracked": baseline,
        "generated_report_paths": list(generated_report_paths),
        "untracked_deltas": [],
    }
    try:
        current = capture_untracked(source_session)
        artifact["current_untracked"] = current
        required = {}
        for path in sorted(baseline.keys() | current.keys()):
            before, after = baseline.get(path), current.get(path)
            if same_fingerprint(before, after):
                continue
            omission = omission_reason(path, before is None, generated_report_paths)
            artifact["untracked_deltas"].append(
                {"path": path, "before": before, "after": after, "omission": omission}
            )
            if omission is None and after is not None:
                required[path] = after
        contents = read_delta_contents(source_session, required)
        for item in artifact["untracked_deltas"]:
            if item["path"] in contents:
                item["data_b64"] = contents[item["path"]]
        artifact["omitted_generated_reports"] = {
            item["path"]: {
                "before": item["before"],
                "after": item["after"],
                "reason": item["omission"],
            }
            for item in artifact["untracked_deltas"]
            if item["omission"] is not None
        }
    except Exception as exc:
        artifact["capture_error"] = type(exc).__name__ + ": " + str(exc)
        if record_evidence is not None:
            record_evidence(artifact)
        raise
    artifact["artifact_sha256"] = artifact_digest(artifact)
    if record_evidence is not None:
        record_evidence(artifact)
    validate_artifact(artifact)
    return artifact


def export_prepared_patch(
    source_session: Session,
    prepared_ref: str,
    *,
    baseline_untracked: dict[str, dict[str, Any]] | None = None,
    generated_report_paths: tuple[str, ...] = (),
    record_evidence: Callable[[dict[str, Any]], None] | None = None,
) -> str:
    """Legacy text-only caller: never silently discard new binary-capable file deltas."""
    artifact = capture_candidate_artifact(
        source_session,
        prepared_ref,
        baseline_untracked=baseline_untracked,
        generated_report_paths=generated_report_paths,
        record_evidence=record_evidence,
    )
    if any(item["omission"] is None for item in artifact["untracked_deltas"]):
        raise CandidatePatchRejected(
            "untracked files changed; caller must use complete artifact replay"
        )
    return artifact["tracked_patch"]


class BaseRateReplay:
    """Diagnostic code artifact replay; never imports target tests or package snapshots."""

    def __init__(
        self,
        runtime: ContainerRuntime,
        pin: TaskPin,
        *,
        prepared_ref: str,
        verify_image: Callable[[str, str], None],
        record_evidence: Callable[[dict[str, Any]], None] | None = None,
        test_timeout: float = 900,
        baseline_untracked: dict[str, dict[str, Any]] | None = None,
        generated_report_paths: tuple[str, ...] = (),
    ) -> None:
        if not re.fullmatch(r"[0-9a-f]{40}", prepared_ref):
            raise ValueError("prepared baseline must be an immutable full Git commit")
        if type(test_timeout) not in (int, float) or not 0 < test_timeout <= 900:
            raise ValueError("invalid test timeout")
        oracle = SweOracle(
            test_command=pin.test_command,
            fail_to_pass=pin.fail_to_pass,
            pass_to_pass=pin.pass_to_pass,
            protected_paths=pin.protected_paths,
            canary="diagnostic-base-rate",
        )
        # Reuse the reviewed transport's pin binding and protected-path policy only.
        self.transport = FreshReplayOracle(runtime, pin, oracle)
        self.runtime, self.pin, self.prepared_ref = runtime, pin, prepared_ref
        self.verify_image, self.record_evidence = verify_image, record_evidence
        self.test_timeout = test_timeout
        self.baseline_untracked = json.loads(json.dumps(baseline_untracked or {}))
        self.generated_report_paths = tuple(generated_report_paths)
        self.evidence_records: list[dict[str, Any]] = []

    def require_protected(self) -> None:
        raise RuntimeUnavailable(
            "diagnostic_frozen_test_replay: candidate and pytest share an interpreter; "
            "protected status is unknown"
        )

    def evaluate(self, source_session: Session) -> dict[str, Any]:
        artifact = capture_candidate_artifact(
            source_session,
            self.prepared_ref,
            baseline_untracked=self.baseline_untracked,
            generated_report_paths=self.generated_report_paths,
            record_evidence=self.record_evidence,
        )
        return self.evaluate_artifact(artifact, source_session=source_session)

    def evaluate_artifact(
        self,
        artifact: dict[str, Any],
        *,
        source_session: Session | None = None,
        release_source: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        try:
            self._validate_bound_artifact(artifact)
            for item in artifact["untracked_deltas"]:
                if item["omission"] is None and self.transport._protected(item["path"]):
                    raise ValueError("artifact changes protected input: " + item["path"])
        except ValueError as exc:
            raise CandidatePatchRejected(str(exc)) from exc
        return self.evaluate_patch(
            artifact["tracked_patch"],
            source_session=source_session,
            untracked_artifact=artifact,
            release_source=release_source,
        )

    def _validate_bound_artifact(self, artifact: dict[str, Any]) -> None:
        validate_artifact(artifact)
        if (
            artifact.get("prepared_ref") != self.prepared_ref
            or artifact.get("baseline_untracked") != self.baseline_untracked
            or tuple(artifact.get("generated_report_paths", ())) != self.generated_report_paths
        ):
            raise ValueError("artifact baseline or omission policy differs from trusted capture")
        for item in artifact["untracked_deltas"]:
            if item["omission"] is None and self.transport._protected(item["path"]):
                raise ValueError("artifact changes protected input: " + item["path"])

    def _validate_patch_transport(
        self, patch: str, untracked_artifact: dict[str, Any] | None = None
    ) -> bytes:
        if untracked_artifact is not None:
            try:
                self._validate_bound_artifact(untracked_artifact)
                if untracked_artifact["tracked_patch"] != patch:
                    raise ValueError("tracked patch differs from artifact")
            except ValueError as exc:
                raise CandidatePatchRejected(str(exc)) from exc
        if type(patch) is not str or "\x00" in patch:
            raise CandidatePatchRejected("candidate patch must be NUL-free text")
        try:
            encoded = patch.encode()
        except UnicodeError as exc:
            raise CandidatePatchRejected("candidate patch must be valid UTF-8") from exc
        if len(encoded) > self.transport.max_patch_bytes:
            raise CandidatePatchRejected("candidate patch exceeds byte bound")
        if re.search(r"^(?:rename|copy) (?:from|to) ", patch, re.MULTILINE):
            raise CandidatePatchRejected("candidate rename/copy transport is unsupported")
        for mode in re.findall(
            r"^(?:old mode|new mode|new file mode|deleted file mode) (\S+)$",
            patch,
            re.MULTILINE,
        ):
            if mode not in ("100644", "100755"):
                raise CandidatePatchRejected("candidate patch contains unsupported file mode")
        return encoded

    def evaluate_patch(
        self,
        patch: str,
        *,
        source_session: Session | None = None,
        untracked_artifact: dict[str, Any] | None = None,
        release_source: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        encoded = self._validate_patch_transport(patch, untracked_artifact)
        self.verify_image(self.pin.image, self.pin.image_sha256)
        # The caller persists the complete bound artifact and waits for source release.
        # Fresh allocation remains non-overlapping even if Slurm epilogue is still pending.
        if release_source is not None:
            if source_session is None:
                raise ValueError("source release requires the source identity")
            release_source()
        session = self.runtime.start(
            self.pin.image,
            self.pin.url,
            self.pin.commit,
            workdir=self.pin.workdir,
            python_env=self.pin.python_env,
        )
        if session is source_session:
            raise RuntimeUnavailable("diagnostic replay requires a distinct fresh session")
        try:
            path = _checked(session, "mktemp /tmp/prun-replay-XXXXXXXX").strip()
            if not re.fullmatch(r"/tmp/prun-replay-[A-Za-z0-9]+", path):
                raise RuntimeUnavailable("invalid replay temporary path")
            quoted = shlex.quote(path)
            if self.pin.test_patch:
                session.write_file(path, self.pin.test_patch)
                _checked(session, "git apply --check -- " + quoted)
                _checked(session, "git apply -- " + quoted)
            session.checkpoint()
            post_check = prepare_task_post_check(
                self.pin, session, record_evidence=self.record_evidence
            )
            # Install and preflight before any candidate edits; never let candidate replace guard.
            repo = _checked(session, "pwd -P").strip()
            guarded = install_guard(session, repo, command_timeout=self.test_timeout)
            # Transport the patch into guard-readable scratch before any candidate
            # bytes arrive. Git filters/hooks may execute repository code even for
            # `git apply --check`, so every later Git invocation must be confined.
            _checked(session, "rm -- " + quoted)
            if patch:
                path = guarded.scratch + "/candidate.patch"
                quoted = shlex.quote(path)
                session.write_file(path, patch)
            if untracked_artifact is not None:
                # One trusted process applies all data BEFORE any tracked candidate edits.
                apply_untracked_deltas(session, untracked_artifact)
            touched = []
            if patch:
                code, out, _ = guarded.exec("git apply --numstat -z -- " + quoted, 60)
                if code:
                    raise CandidatePatchRejected("candidate is not a valid patch")
                for record in out.split("\x00"):
                    if not record:
                        continue
                    fields = record.split("\t", 2)
                    if len(fields) != 3:
                        raise CandidatePatchRejected("ambiguous patch paths")
                    try:
                        name = relative_path(fields[2])
                    except ValueError as exc:
                        raise CandidatePatchRejected("unsafe patch path") from exc
                    if self.transport._protected(name):
                        raise CandidatePatchRejected("candidate changes protected input: " + name)
                    touched.append(name)
                if not touched:
                    raise CandidatePatchRejected("nonempty patch has no changes")
                self.transport._regular_paths(guarded, touched)
                code, _, _ = guarded.exec("git apply --check -- " + quoted, 60)
                if code:
                    raise CandidatePatchRejected("candidate patch does not apply")
                _checked(guarded, "git apply -- " + quoted)
                self.transport._regular_paths(guarded, touched)
                _checked(guarded, "rm -- " + quoted)
            # Every candidate-importing invocation uses inherited Landlock/seccomp guard.
            code, out, err = guarded.exec(self.pin.test_command, self.test_timeout)
            evidence = {
                "phase": "frozen_tests",
                "command": self.pin.test_command,
                "exit": code,
                "stdout": out,
                "stderr": err,
                "candidate_sha256": hashlib.sha256(encoded).hexdigest(),
                "kind": "diagnostic_frozen_test_replay",
                "protected_status": "unknown",
            }
            self.evidence_records.append(evidence)
            if self.record_evidence is not None:
                self.record_evidence(dict(evidence))
            if code == 124:
                raise RuntimeUnavailable("frozen test command timed out")
            self.verify_image(self.pin.image, self.pin.image_sha256)
            expected = self.pin.fail_to_pass + self.pin.pass_to_pass
            parsed = parse_pytest_summary(out, expected)
            outcomes = TestEvidence(
                exit_code=code,
                statuses={
                    node: TestStatus(status)
                    for node, status in parsed.items()
                    if status is not None
                },
            ).require(expected)
            post_result = (
                post_check.evaluate(guarded, (code, out, err), timeout=self.test_timeout)
                if post_check is not None
                else {}
            )
            return {
                **post_result,
                "diagnostic_passed": post_result.get(
                    "diagnostic_passed",
                    code == 0 and all(value is TestStatus.PASSED for value in outcomes.values()),
                ),
                "test_results": {"exit": code, "stdout": out, "stderr": err},
                "diagnostic_replay": {
                    "kind": "diagnostic_frozen_test_replay",
                    "protected_status": "unknown",
                    "task_key": self.pin.key,
                    "prepared_ref": self.prepared_ref,
                    "candidate_sha256": hashlib.sha256(encoded).hexdigest(),
                    "changed_files": sorted(set(touched)),
                    "untracked_artifact": untracked_artifact,
                    "artifact_scope": "tracked and untracked code deltas; omissions explicit",
                    "statuses": outcomes,
                    "image_sha256": self.pin.image_sha256,
                    "guard_attestation": guarded.attestation,
                    "limitations": [
                        "candidate can tamper with same-process pytest evidence",
                        "target environment/package changes are not replayed",
                    ],
                },
            }
        finally:
            session.stop()
