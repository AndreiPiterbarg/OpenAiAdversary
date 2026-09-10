"""Pre-registration as a hash chain.

An experiment directory holds ``preregistration.yaml`` (question, hypothesis, kill rules,
analysis plan, and optionally a bound prose document) and ``config.yaml`` (what will be run).
:func:`register` hashes both, records the UTC time and the git HEAD in ``registration.json``,
and refuses if results already exist. Amendments append to ``amendments.jsonl`` with a reason
and never overwrite. Results are sealed with a manifest citing the registration; the verdict
cites the sealed results. :func:`verify` walks the chain and reports drift.

A prose document is bound either whole, by ``document_sha256``, or by a *hash sidecar*: a
file listing named regions of the document with the hash each must have. A hash recorded
inside its own input can never verify, so the sidecar is where region hashes live. The
``[registered]`` region is locked at registration and must stay byte-identical; other regions
(amendments) may be appended later and must match the sidecar's own entries.

This makes tampering detectable, not impossible: commit ``registration.json`` so the git
history anchors the timestamp outside the author's control.
"""

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, model_validator

from adversary.core.config import FrozenModel
from adversary.core.manifest import MANIFEST_NAME, Manifest, build_manifest
from adversary.core.util import sha256_bytes, sha256_text, utc_now

PREREGISTRATION_FILE = "preregistration.yaml"
CONFIG_FILE = "config.yaml"
REGISTRATION_FILE = "registration.json"
AMENDMENTS_FILE = "amendments.jsonl"
RESULTS_DIR = "results"
VERDICT_FILE = "verdict.json"
PROTOCOL_VERSION = "3"
REGISTERED_REGION = "registered"

Comparator = Literal["<", "<=", ">", ">=", "==", "!="]


class Condition(FrozenModel):
    """One comparison of a reported metric against a threshold.

    The threshold is either a pre-declared constant or another reported metric, for rules whose
    reference magnitude is fixed by a calibration measurement rather than by intuition.
    """

    metric: str = Field(description="Key in results/metrics.json")
    op: Comparator = Field(description="Applied as ``measured <op> threshold``")
    threshold: float | None = Field(default=None, description="Constant threshold")
    threshold_metric: str | None = Field(
        default=None, description="Key in results/metrics.json supplying the threshold"
    )

    @model_validator(mode="after")
    def _one_threshold(self) -> "Condition":
        if (self.threshold is None) == (self.threshold_metric is None):
            raise ValueError("exactly one of threshold and threshold_metric is required")
        return self

    def holds(self, measured: float, threshold: float | None = None) -> bool:
        """Evaluate against the constant threshold, or the supplied metric-derived one."""
        bound = self.threshold if threshold is None else threshold
        if bound is None:
            raise ValueError(f"condition on {self.metric!r} needs its threshold metric")
        return {
            "<": measured < bound,
            "<=": measured <= bound,
            ">": measured > bound,
            ">=": measured >= bound,
            "==": measured == bound,
            "!=": measured != bound,
        }[self.op]

    def describe(self) -> str:
        bound = self.threshold_metric if self.threshold_metric else self.threshold
        return f"{self.metric} {self.op} {bound}"


class KillRule(FrozenModel):
    """A pre-declared decision rule.

    The rule *triggers* when every condition in ``all_of`` holds. It is *inconclusive*, and
    cannot trigger, unless every precondition in ``requires`` holds: a null from an instrument
    that has not shown it can detect the effect is not evidence of absence. When it does not
    trigger, the conditions in ``survive_if`` must hold for the outcome to be survival; a
    result between the kill threshold and the pass threshold is inconclusive (Amendment A6).
    """

    name: str
    all_of: tuple[Condition, ...] = Field(
        min_length=1, description="Conjunction; all must hold to trigger"
    )
    requires: tuple[Condition, ...] = Field(
        default=(),
        description="Preconditions that must hold for the rule to be evaluable at all",
    )
    survive_if: tuple[Condition, ...] = Field(
        default=(),
        description=(
            "When the rule does not trigger, these must also hold for the result to count as "
            "survival; otherwise the rule is inconclusive (a band between kill and pass)"
        ),
    )
    consequence: str = Field(description="What it means, in words, if this triggers")


class Preregistration(FrozenModel):
    """The machine-readable part of a pre-registration."""

    title: str
    question: str = Field(description="The research question, one sentence")
    hypothesis: str = Field(description="What we expect, stated so it can be wrong")
    kill_rules: tuple[KillRule, ...] = Field(min_length=1)
    analysis_plan: str = Field(description="Exactly which statistics will be computed, and how")
    document: str | None = Field(
        default=None,
        description="Path, relative to the experiment directory, of the prose pre-registration",
    )
    document_sha256: str | None = Field(
        default=None, description="Whole-file hash the prose document must have at registration"
    )
    document_hashes: str | None = Field(
        default=None,
        description=(
            "Path, relative to the experiment directory, of the hash sidecar naming the "
            "document's regions and their hashes"
        ),
    )
    budget: str = ""
    author: str = ""
    written_on: str = Field(default="", description="ISO date the text was written")

    @model_validator(mode="after")
    def _binding_is_coherent(self) -> "Preregistration":
        if (self.document_sha256 or self.document_hashes) and not self.document:
            raise ValueError("a document hash or sidecar needs a document path")
        return self

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Preregistration":
        with open(path, encoding="utf-8") as handle:
            return cls.model_validate(yaml.safe_load(handle))


class RegionHash(FrozenModel):
    """One sidecar entry: a named region of the document, or a separate file, and its hash.

    The same name may appear more than once; entries form a dated history and the last one
    is current. Earlier entries are kept as the record of what was true before an amendment.
    """

    name: str
    region: str | None = Field(
        default=None, description="Boundary rule, e.g. 'from the line \"## 9\" to end of file'"
    )
    file: str | None = Field(
        default=None, description="Path of a sealed file, relative to the sidecar, hashed whole"
    )
    sha256: str
    date: str = ""
    note: str = ""

    @model_validator(mode="after")
    def _one_target(self) -> "RegionHash":
        if (self.region is None) == (self.file is None):
            raise ValueError("a sidecar entry names exactly one of region and file")
        return self


_START = (
    r"start of file|from the line(?: (?P<start_mode>ending|starting))? "
    r'"(?P<start_text>[^"]*)"'
)
_END = (
    r"to end of file|through the line(?: (?P<end_mode>ending|starting))? "
    r'"(?P<end_text>[^"]*)"'
)
_REGION = re.compile(rf"^(?P<start>{_START})\s+(?P<end>{_END})$")


def parse_sidecar(text: str) -> list[RegionHash]:
    """Parse an INI-like sidecar: ``[name]`` sections of ``key = value`` lines."""
    entries: list[RegionHash] = []
    current: dict[str, str] | None = None
    name: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            if name is not None and current is not None:
                entries.append(RegionHash(name=name, **current))
            name, current = line[1:-1].strip(), {}
            continue
        if current is None:
            continue  # prose preamble before the first section
        if "=" not in line:
            raise ValueError(f"malformed sidecar line: {raw!r}")
        key, value = (part.strip() for part in line.split("=", 1))
        if key in {"region", "file", "sha256", "date", "note"}:
            current[key] = value
    if name is not None and current is not None:
        entries.append(RegionHash(name=name, **current))
    if not entries:
        raise ValueError("sidecar names no regions")
    return entries


def _line_matches(line: str, mode: str | None, text: str) -> bool:
    body = line.rstrip("\r\n")
    if mode == "ending":
        return body.endswith(text)
    if mode == "starting":
        return body.startswith(text)
    return body == text


def extract_region(document: str, rule: str) -> str:
    """Cut the region ``rule`` describes out of ``document``, newlines included."""
    match = _REGION.match(rule.strip())
    if not match:
        raise ValueError(f"unrecognised region rule: {rule!r}")
    lines = document.splitlines(keepends=True)
    start = 0
    if match.group("start") != "start of file":
        start = next(
            (
                i
                for i, line in enumerate(lines)
                if _line_matches(line, match.group("start_mode"), match.group("start_text"))
            ),
            None,
        )
        if start is None:
            raise ValueError(f"region start not found: {rule!r}")
    end = len(lines) - 1
    if match.group("end") != "to end of file":
        end = next(
            (
                i
                for i, line in enumerate(lines)
                if i >= start
                and _line_matches(line, match.group("end_mode"), match.group("end_text"))
            ),
            None,
        )
        if end is None:
            raise ValueError(f"region end not found: {rule!r}")
    return "".join(lines[start : end + 1])


def current_entries(entries: list[RegionHash]) -> dict[str, RegionHash]:
    """The latest entry per name; earlier ones are history."""
    latest: dict[str, RegionHash] = {}
    for entry in entries:
        latest[entry.name] = entry
    return latest


def verify_sidecar(document_path: Path, sidecar_path: Path) -> tuple[list[RegionHash], list[str]]:
    """Check the current entry of every sidecar name; return all entries and problems.

    The ``[registered]`` name may not have a history: every entry under it must carry the
    same hash, because the registered region never changes.
    """
    entries = parse_sidecar(sidecar_path.read_text(encoding="utf-8"))
    document = document_path.read_text(encoding="utf-8")
    problems: list[str] = []
    registered = [e for e in entries if e.name == REGISTERED_REGION]
    if not registered:
        problems.append(f"sidecar has no [{REGISTERED_REGION}] region")
    elif len({e.sha256 for e in registered}) > 1:
        problems.append(f"[{REGISTERED_REGION}] appears with different hashes; it may not change")
    for entry in current_entries(entries).values():
        try:
            if entry.region is not None:
                actual = sha256_text(extract_region(document, entry.region))
                what = "region"
            else:
                target = (sidecar_path.parent / str(entry.file)).resolve()
                if not target.exists():
                    problems.append(f"[{entry.name}] file {entry.file} is missing")
                    continue
                actual = sha256_bytes(target.read_bytes())
                what = "file"
        except ValueError as exc:
            problems.append(f"[{entry.name}]: {exc}")
            continue
        if actual != entry.sha256:
            problems.append(
                f"[{entry.name}] {what} hashes to {actual[:16]}..., "
                f"sidecar says {entry.sha256[:16]}..."
            )
    return entries, problems


class Registration(FrozenModel):
    """The lock written at registration time."""

    preregistration_sha256: str
    config_sha256: str
    document_sha256: str | None = Field(default=None, description="Whole document at registration")
    document_regions: dict[str, str] = Field(
        default_factory=dict, description="Sidecar region name -> sha256 at registration"
    )
    registered_at: datetime
    git_head: str | None
    protocol_version: str = PROTOCOL_VERSION

    @property
    def sha256(self) -> str:
        """Identity of this registration: hash of the pre-registration content."""
        return self.preregistration_sha256


class Amendment(FrozenModel):
    """An appended change to the pre-registration, never an overwrite."""

    previous_sha256: str
    new_sha256: str
    reason: str
    amended_at: datetime


class PreregistrationError(RuntimeError):
    """The protocol was violated."""


def git_head(cwd: Path) -> str | None:
    """Current commit hash, or ``None`` when git is unavailable."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _hash_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _check_document(root: Path, prereg: Preregistration) -> tuple[str | None, dict[str, str]]:
    """Whole-file hash and verified region hashes of the bound document; raises on mismatch."""
    if prereg.document is None:
        return None, {}
    document = (root / prereg.document).resolve()
    if not document.exists():
        raise PreregistrationError(f"bound document {prereg.document} does not exist")
    digest = _hash_file(document)
    if prereg.document_sha256 and digest != prereg.document_sha256:
        raise PreregistrationError(
            "bound document hash mismatch: preregistration says "
            f"{prereg.document_sha256[:16]}..., file is {digest[:16]}..."
        )
    regions: dict[str, str] = {}
    if prereg.document_hashes:
        sidecar = (root / prereg.document_hashes).resolve()
        if not sidecar.exists():
            raise PreregistrationError(f"hash sidecar {prereg.document_hashes} does not exist")
        entries, problems = verify_sidecar(document, sidecar)
        if problems:
            raise PreregistrationError("; ".join(problems))
        regions = {name: e.sha256 for name, e in current_entries(entries).items()}
    return digest, regions


def register(directory: str | Path) -> Registration:
    """Lock the pre-registration and config of ``directory``.

    Raises:
        PreregistrationError: If already registered, if results exist, if files are missing, or
            if a bound prose document does not have the declared hash or sidecar regions.
    """
    root = Path(directory)
    prereg_path, config = root / PREREGISTRATION_FILE, root / CONFIG_FILE
    if not prereg_path.exists() or not config.exists():
        raise PreregistrationError(
            f"{PREREGISTRATION_FILE} and {CONFIG_FILE} must both exist in {root}"
        )
    if (root / REGISTRATION_FILE).exists():
        raise PreregistrationError("already registered; amend, or start a new experiment directory")
    results = root / RESULTS_DIR
    if results.exists() and any(results.iterdir()):
        raise PreregistrationError(
            "results exist before registration; this experiment cannot be pre-registered"
        )
    prereg = Preregistration.from_yaml(prereg_path)
    document_sha256, regions = _check_document(root, prereg)
    registration = Registration(
        preregistration_sha256=_hash_file(prereg_path),
        config_sha256=_hash_file(config),
        document_sha256=document_sha256,
        document_regions=regions,
        registered_at=utc_now(),
        git_head=git_head(root),
    )
    (root / REGISTRATION_FILE).write_text(registration.model_dump_json(indent=2), encoding="utf-8")
    return registration


def load_registration(directory: str | Path) -> Registration:
    """Read the lock."""
    path = Path(directory) / REGISTRATION_FILE
    if not path.exists():
        raise PreregistrationError(f"{path} does not exist; register first")
    return Registration.model_validate_json(path.read_text(encoding="utf-8"))


def load_amendments(directory: str | Path) -> list[Amendment]:
    """Read the amendment chain, oldest first."""
    path = Path(directory) / AMENDMENTS_FILE
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as handle:
        return [Amendment.model_validate_json(line) for line in handle if line.strip()]


def current_preregistration_sha256(directory: str | Path) -> str:
    """The hash the pre-registration file may have now: registration or latest amendment."""
    amendments = load_amendments(directory)
    return amendments[-1].new_sha256 if amendments else load_registration(directory).sha256


def amend(directory: str | Path, reason: str) -> Amendment:
    """Record that ``preregistration.yaml`` changed, with a reason. Refused after sealing."""
    root = Path(directory)
    if not reason.strip():
        raise PreregistrationError("an amendment needs a reason")
    if (root / RESULTS_DIR / MANIFEST_NAME).exists():
        raise PreregistrationError(
            "results are sealed; the pre-registration can no longer be amended"
        )
    previous = current_preregistration_sha256(root)
    new = _hash_file(root / PREREGISTRATION_FILE)
    if new == previous:
        raise PreregistrationError("preregistration.yaml is unchanged; nothing to amend")
    Preregistration.from_yaml(root / PREREGISTRATION_FILE)
    amendment = Amendment(
        previous_sha256=previous, new_sha256=new, reason=reason, amended_at=utc_now()
    )
    with open(root / AMENDMENTS_FILE, "a", encoding="utf-8") as handle:
        handle.write(amendment.model_dump_json() + "\n")
    return amendment


def seal_results(directory: str | Path) -> Manifest:
    """Write ``results/MANIFEST.json`` citing the registration; refuses without a registration."""
    root = Path(directory)
    registration = load_registration(root)
    results = root / RESULTS_DIR
    results.mkdir(exist_ok=True)
    manifest = build_manifest(results, note=f"registration={registration.sha256}")
    manifest.write(results)
    return manifest


def _verify_document(root: Path, prereg: Preregistration, registration: Registration) -> list[str]:
    """Document checks at verify time: the registered region is locked, the rest self-consistent."""
    problems: list[str] = []
    if prereg.document is None:
        return problems
    document = (root / prereg.document).resolve()
    if not document.exists():
        return [f"bound document {prereg.document} is missing"]
    if prereg.document_sha256 and _hash_file(document) != prereg.document_sha256:
        problems.append("bound document changed after registration (whole-file binding)")
    if prereg.document_hashes:
        sidecar = (root / prereg.document_hashes).resolve()
        if not sidecar.exists():
            return [*problems, f"hash sidecar {prereg.document_hashes} is missing"]
        entries, sidecar_problems = verify_sidecar(document, sidecar)
        problems.extend(sidecar_problems)
        current = {name: e.sha256 for name, e in current_entries(entries).items()}
        locked = registration.document_regions.get(REGISTERED_REGION)
        if locked is not None and current.get(REGISTERED_REGION) != locked:
            problems.append(f"the [{REGISTERED_REGION}] region hash changed in the sidecar")
    return problems


def verify(directory: str | Path) -> list[str]:
    """Walk the chain; return problems, empty if intact."""
    root = Path(directory)
    problems: list[str] = []
    try:
        registration = load_registration(root)
    except PreregistrationError as exc:
        return [str(exc)]
    prereg_path, config = root / PREREGISTRATION_FILE, root / CONFIG_FILE

    amendments = load_amendments(root)
    expected = registration.sha256
    for i, a in enumerate(amendments):
        if a.previous_sha256 != expected:
            problems.append(
                f"amendment {i + 1} does not chain from the previous pre-registration hash"
            )
        if a.amended_at < registration.registered_at:
            problems.append(f"amendment {i + 1} predates registration")
        expected = a.new_sha256
    if not prereg_path.exists() or _hash_file(prereg_path) != expected:
        problems.append("preregistration.yaml changed without an amendment")
    if not config.exists() or _hash_file(config) != registration.config_sha256:
        problems.append("config.yaml changed after registration")
    if prereg_path.exists():
        try:
            prereg = Preregistration.from_yaml(prereg_path)
            problems.extend(_verify_document(root, prereg, registration))
        except (PreregistrationError, ValueError) as exc:
            problems.append(str(exc))

    results = root / RESULTS_DIR
    manifest_path = results / MANIFEST_NAME
    if results.exists() and any(p for p in results.iterdir() if p.name != MANIFEST_NAME):
        if not manifest_path.exists():
            problems.append("results exist without a sealed manifest")
        else:
            manifest = Manifest.read(results)
            if manifest.note != f"registration={registration.sha256}":
                problems.append("results manifest does not cite this registration")
            if manifest.produced_at < registration.registered_at:
                problems.append("results manifest predates registration")
            if amendments and manifest.produced_at < amendments[-1].amended_at:
                problems.append("pre-registration was amended after results were sealed")
            if build_manifest(results).digest() != manifest.digest():
                problems.append("results changed after sealing")
    verdict_path = root / VERDICT_FILE
    if verdict_path.exists():
        from adversary.protocol.verdict import ExperimentVerdict

        verdict = ExperimentVerdict.model_validate_json(verdict_path.read_text(encoding="utf-8"))
        if verdict.registration_sha256 != registration.sha256:
            problems.append("verdict does not cite this registration")
        if manifest_path.exists() and verdict.results_digest != Manifest.read(results).digest():
            problems.append("verdict does not cite the sealed results")
    return problems
