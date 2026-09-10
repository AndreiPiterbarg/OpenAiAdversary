"""Bounded binary deltas for untracked regular files in a code-only replay artifact."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import shlex
from typing import Any

from adversary.domain.channel import relative_path
from domains.swe_agents.environment.runtime import RuntimeUnavailable, Session

MAX_DELTA_BYTES = 2 * 1024 * 1024
MAX_DELTA_FILES = 1024


def safe_path(path: str) -> str:
    value = relative_path(path)
    if ".git" in value.split("/"):
        raise ValueError("Git internal paths are not artifact files")
    return value


def same_fingerprint(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if left is None or right is None:
        return left is right
    return (left["sha256"], left["size"]) == (right["sha256"], right["size"]) and (
        "mode" not in left or "mode" not in right or left["mode"] == right["mode"]
    )


def omission_reason(path: str, new: bool, reports: tuple[str, ...]) -> str | None:
    if path in reports or (
        "htmlcov/" in reports
        and re.fullmatch(r"htmlcov/(?:[A-Za-z0-9_-]+\.(?:html|css|js|png|json)|\.gitignore)", path)
    ):
        return "frozen_declared_generated_report"
    parts = path.split("/")
    if new and (
        parts[0] in {"tests", "test"}
        or parts[-1] == "conftest.py"
        or (parts[-1].startswith("test_") and parts[-1].endswith(".py"))
        or parts[-1].endswith("_test.py")
    ):
        return "new_candidate_test_excluded_from_frozen_code_only_replay"
    if new and any(
        part in {".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__"}
        for part in parts[:-1]
    ):
        return "new_candidate_cache_excluded_from_code_only_replay"
    return None


def artifact_digest(artifact: dict[str, Any]) -> str:
    payload = {key: value for key, value in artifact.items() if key != "artifact_sha256"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_artifact(artifact: dict[str, Any]) -> None:
    if artifact.get("kind") != "bounded_code_artifact_v1":
        raise ValueError("unsupported code artifact")
    if artifact.get("artifact_sha256") != artifact_digest(artifact):
        raise ValueError("artifact digest differs")
    if type(artifact.get("tracked_patch")) is not str:
        raise ValueError("tracked patch must be text")
    if artifact.get("patch", artifact["tracked_patch"]) != artifact["tracked_patch"]:
        raise ValueError("artifact patch aliases differ")
    baseline, current = artifact.get("baseline_untracked"), artifact.get("current_untracked")
    if type(baseline) is not dict or type(current) is not dict:
        raise ValueError("artifact file manifests required")
    for manifest in (baseline, current):
        for path, fingerprint in manifest.items():
            safe_path(path)
            if type(fingerprint) is not dict:
                raise ValueError("invalid manifest fingerprint")
            if (
                type(fingerprint.get("size")) is not int
                or fingerprint["size"] < 0
                or not re.fullmatch(r"[0-9a-f]{64}", str(fingerprint.get("sha256")))
            ):
                raise ValueError("invalid manifest fingerprint")
    changed = {
        path
        for path in baseline.keys() | current.keys()
        if not same_fingerprint(baseline.get(path), current.get(path))
    }
    deltas = artifact.get("untracked_deltas")
    if type(deltas) is not list or len(deltas) > MAX_DELTA_FILES:
        raise ValueError("artifact file count exceeds bound")
    reports = tuple(artifact.get("generated_report_paths", ()))
    if not set(reports) <= {"pytest.xml", ".coverage", "coverage.xml", "htmlcov/"}:
        raise ValueError("unsupported declared report policy")
    seen, total = set(), 0
    for item in deltas:
        path = safe_path(item["path"])
        if path in seen:
            raise ValueError("duplicate artifact path")
        seen.add(path)
        before, after = item["before"], item["after"]
        if before != baseline.get(path) or after != current.get(path):
            raise ValueError("file delta differs from captured manifests")
        if before is None and after is None:
            raise ValueError("empty file delta")
        reason = omission_reason(path, before is None, reports)
        if item.get("omission") != reason:
            raise ValueError("artifact omission policy differs")
        for fingerprint in (before, after):
            if fingerprint is None:
                continue
            if (
                type(fingerprint.get("size")) is not int
                or fingerprint["size"] < 0
                or not re.fullmatch(r"[0-9a-f]{64}", str(fingerprint.get("sha256")))
                or type(fingerprint.get("mode", 0o644)) is not int
                or not 0 <= fingerprint.get("mode", 0o644) <= 0o777
            ):
                raise ValueError("invalid artifact fingerprint")
        if after is not None and reason is None:
            try:
                content = base64.b64decode(item["data_b64"], validate=True)
            except (KeyError, ValueError, binascii.Error) as exc:
                raise ValueError("invalid artifact binary data") from exc
            total += len(content)
            if (
                len(content) != after["size"]
                or hashlib.sha256(content).hexdigest() != after["sha256"]
            ):
                raise ValueError("artifact content fingerprint differs")
        elif "data_b64" in item:
            raise ValueError("omitted or deleted file must not carry replay bytes")
    if seen != changed:
        raise ValueError("artifact delta coverage differs from captured manifests")
    if total > MAX_DELTA_BYTES:
        raise ValueError("artifact data exceeds byte bound")


_READ_CONTENTS = """import base64,hashlib,json,os,pathlib,stat,sys
expected=json.load(open(sys.argv[1])); result={}; total=0
for name,fp in expected.items():
 p=pathlib.Path(name)
 if p.is_absolute() or '..' in p.parts or '.git' in p.parts: raise ValueError('unsafe path')
 if any(q.is_symlink() for q in (p,*p.parents)): raise ValueError('linked path')
 fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as stream:
  info=os.fstat(stream.fileno())
  if not stat.S_ISREG(info.st_mode): raise ValueError('nonregular artifact')
  content=stream.read(2097153)
  total+=len(content)
  if total>2097152: raise ValueError('artifact bytes exceed bound')
  if len(content)!=fp['size'] or hashlib.sha256(content).hexdigest()!=fp['sha256']:
   raise ValueError('artifact changed during capture')
  after=os.fstat(stream.fileno())
  if (info.st_size,info.st_mtime_ns,info.st_mode)!=(after.st_size,after.st_mtime_ns,after.st_mode):
   raise ValueError('artifact changed during capture')
  if 'mode' in fp and stat.S_IMODE(after.st_mode)!=fp['mode']:
   raise ValueError('artifact mode changed during capture')
  result[name]=base64.b64encode(content).decode('ascii')
print(json.dumps(result))
"""


def _run_payload_script(session: Session, script: str, payload: Any) -> tuple[int, str, str]:
    """Chunk JSON through a temporary file, avoiding OS per-argument size limits."""
    code, path, err = session.exec("mktemp", 30)
    path = path.strip()
    if code or not path.startswith("/") or "\n" in path or "\x00" in path:
        raise RuntimeUnavailable("cannot prepare artifact payload: " + err[-500:])
    quoted = shlex.quote(path)
    data = json.dumps(payload).encode()
    try:
        for offset in range(0, len(data), 32768):
            encoded = base64.b64encode(data[offset : offset + 32768]).decode()
            code, _, err = session.exec(
                "printf %s " + shlex.quote(encoded) + " | base64 -d >> " + quoted, 30
            )
            if code:
                raise RuntimeUnavailable("artifact payload transport failed: " + err[-500:])
        return session.exec("python -I -B -c " + shlex.quote(script) + " " + quoted, 120)
    finally:
        session.exec("rm -- " + quoted, 30)


def read_delta_contents(session: Session, expected: dict[str, dict[str, Any]]) -> dict[str, str]:
    if not expected:
        return {}
    if (
        len(expected) > MAX_DELTA_FILES
        or sum(x["size"] for x in expected.values()) > MAX_DELTA_BYTES
    ):
        raise ValueError("artifact data exceeds capture bound")
    code, out, err = _run_payload_script(session, _READ_CONTENTS, expected)
    if code:
        raise RuntimeUnavailable("artifact capture failed: " + err[-1000:])
    value = json.loads(out)
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError("artifact content coverage differs")
    return value


_APPLY_DELTAS = """import base64,hashlib,json,os,pathlib,stat,sys,tempfile
items=json.load(open(sys.argv[1]))
def parents(p):
 for q in (p,*p.parents):
  if q.is_symlink(): raise ValueError('linked replay path')
  if q!=p and q.exists() and not q.is_dir(): raise ValueError('non-directory parent')
# Validate ALL prior files before writing ANY candidate byte.
for item in items:
 p=pathlib.Path(item['path']); parents(p); before=item['before']
 if p.is_absolute() or '..' in p.parts or '.git' in p.parts: raise ValueError('unsafe replay path')
 if before is None:
  if os.path.lexists(p): raise ValueError('new artifact collides with fresh file')
 else:
  fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
  with os.fdopen(fd,'rb') as stream:
   info=os.fstat(stream.fileno())
   if not stat.S_ISREG(info.st_mode): raise ValueError('nonregular replay file')
   h=hashlib.sha256(); size=0
   for block in iter(lambda:stream.read(1048576),b''):
    size+=len(block)
    if size>33554432: raise ValueError('baseline file exceeds bound')
    h.update(block)
  if size!=before['size'] or h.hexdigest()!=before['sha256']:
   raise ValueError('fresh baseline differs')
  if 'mode' in before and stat.S_IMODE(info.st_mode)!=before['mode']:
   raise ValueError('fresh mode differs')
for item in items:
 p=pathlib.Path(item['path']); after=item['after']
 if after is None: p.unlink(); continue
 p.parent.mkdir(parents=True,exist_ok=True); parents(p)
 fd,tmp=tempfile.mkstemp(prefix='.prun-artifact-',dir=str(p.parent))
 try:
  with os.fdopen(fd,'wb') as stream: stream.write(base64.b64decode(item['data_b64'],validate=True))
  os.chmod(tmp,after.get('mode',420)); os.replace(tmp,p)
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
print(json.dumps({'applied':len(items)}))
"""


def apply_untracked_deltas(session: Session, artifact: dict[str, Any]) -> None:
    """One pre-imported trusted process validates then writes bytes; no candidate code executes."""
    validate_artifact(artifact)
    items = [item for item in artifact["untracked_deltas"] if item["omission"] is None]
    if not items:
        return
    code, out, err = _run_payload_script(session, _APPLY_DELTAS, items)
    if code:
        raise RuntimeUnavailable("artifact replay failed: " + err[-1000:])
    if json.loads(out) != {"applied": len(items)}:
        raise RuntimeUnavailable("artifact replay acknowledgement differs")
