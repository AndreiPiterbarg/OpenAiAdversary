"""Authenticate recorded launches against narrowly reviewed producer versions.

Historical preparation argv was not saved: preparation is established by the
trusted original result, build log, and exact reviewed controller/helper bytes.
No producer code is imported or executed by this consumer.
"""

import hashlib
import re
from pathlib import Path, PurePosixPath

from domains.swe_agents.environment.gold import digest
from domains.swe_agents.environment.prun_integrity import Receipt, require_regular, strict_json

CONTROLLERS = {
    "gold_verify_pyxis_prun.py": "d754c06a42be2c0c158d175a6b393f62b8979eed120bcef0bd834f07f2433085",
    "gold_verify_pyxis_ram_resume_prun.py": (
        "9451ee63e7b2898bda0dd9a98934a59e2b6a69b2c846cf0bbc9a7f413846e7d8"
    ),
    "gold_verify_pyxis_ram_retry_prun.py": (
        "2c3ff908ac0a1cb9f85d3318a747ec1d0595554619e8e3b222b3d9b4cb3519c1"
    ),
}
RUNNER = "87251b8b2ba06b29b96943d95c53d645087f0c7f61a5191062223a1fa9bf9c8e"
HELPER = "f121981c752b9ec89627cb02b5af0135c322ce39dfd303e6b307fe2344cb4a32"
COMMON = "a6b707627c3a66bcb5a81c48a78887aa6ce3416995c898a83acfdc9bc793b3f9"


class Ancestor:
    """A manifest-authenticated metadata subset; never claims full byte coverage."""

    def __init__(self, base: Path, name: str, anchor: str) -> None:
        if not re.fullmatch("[A-Za-z0-9_-]+", name):
            raise ValueError("unsafe ancestor run")
        self.root = base / name
        require_regular(self.root / "MANIFEST.json")
        if digest(self.root / "MANIFEST.json") != anchor:
            raise ValueError("ancestor manifest digest mismatch")
        self.entries = {}
        for entry in strict_json((self.root / "MANIFEST.json").read_text())["files"]:
            path = entry["path"]
            pure = PurePosixPath(path)
            if (
                pure.is_absolute()
                or ".." in pure.parts
                or path != pure.as_posix()
                or path in self.entries
                or path in {"", ".", "MANIFEST.json"}
                or "\\" in path
            ):
                raise ValueError("unsafe or duplicate ancestor manifest path")
            self.entries[path] = entry

    def matches(self, name: str, path: Path) -> bool:
        entry = self.entries.get(name)
        require_regular(path)
        return (
            entry is not None
            and not path.is_symlink()
            and path.is_file()
            and path.stat().st_size == entry["size"]
            and digest(path) == entry["sha256"]
        )

    def obj(self, name: str) -> dict | list:
        path = self.root / name
        if not self.matches(name, path):
            raise ValueError("ancestor file differs from manifest: " + name)
        return strict_json(path.read_text())


def successful(value: dict) -> bool:
    return type(value.get("exit")) is int and value["exit"] == 0 and value.get("timeout") is False


def validate_backend(receipt: Receipt, row: dict, result: dict) -> None:
    iid = row["instance_id"]
    current = receipt
    visited = {receipt.root.name}
    while True:
        reg = current.obj("registration.json")
        if "parent_run" in reg:
            name, anchor = reg["parent_run"], reg["parent_manifest_sha256"]
        elif "parent.json" in current.entries:
            parent = current.obj("parent.json")
            if iid not in parent["imported_instances"]:
                break
            name, anchor = parent["run"], parent["manifest_sha256"]
        else:
            break
        if name in visited:
            raise ValueError("cyclic receipt ancestry")
        visited.add(name)
        current = Ancestor(receipt.root.parent, name, anchor)
        candidates = current.obj("candidates.json")
        if [r for r in candidates if r["instance_id"] == iid] != [row]:
            raise ValueError("ancestor source candidate changed")
    if not isinstance(current, Ancestor):
        # Direct original receipts use the same explicit trust chain anchor.
        current = Ancestor(
            receipt.root.parent, receipt.root.name, digest(receipt.root / "MANIFEST.json")
        )
    scripts = reg["scripts"]
    controllers = [name for name in CONTROLLERS if name in scripts]
    if len(controllers) != 1:
        raise ValueError("unreviewed execution controller")
    controller = controllers[0]
    named = controller != "gold_verify_pyxis_prun.py"
    required = {
        controller: CONTROLLERS[controller],
        "pyxis_gold_runner.py": RUNNER,
        "gold_verify_prun.py": COMMON,
    }
    if named:
        required["ram_root_prun.py"] = HELPER
    for name, sha in required.items():
        if (
            scripts.get(name) != sha
            or not current.matches(name, current.root / name)
            or digest(current.root / name) != sha
        ):
            raise ValueError("unreviewed or unauthenticated producer script: " + name)
    prefix = "evidence/" + iid + "/"
    originals = [
        receipt.entries.get(prefix + name)
        for name in ("original-result.json", "pre-contract-result.json", "result.json")
    ]
    originals = [p for p in originals if p and current.matches(prefix + "result.json", p)]
    if not originals:
        raise ValueError("original execution result absent from provenance")
    original = strict_json(originals[0].read_text())
    for field in ("phases", "image_sha256", "image_hash_before", "image_hash_after"):
        if result.get(field) != original.get(field):
            raise ValueError("execution evidence changed since original run: " + field)
    required_raw = {
        name
        for name in current.entries
        if name.startswith(prefix)
        and (
            name[len(prefix) :].startswith(("baseline/", "gold/"))
            or name.endswith(("image-hash-before.log", "image-hash-after.log"))
        )
    }
    actual_raw = {
        name
        for name in receipt.entries
        if name.startswith(prefix)
        and (
            name[len(prefix) :].startswith(("baseline/", "gold/"))
            or name.endswith(("image-hash-before.log", "image-hash-after.log"))
        )
    }
    if actual_raw != required_raw:
        raise ValueError("original raw execution evidence coverage differs")
    for name in required_raw:
        if not current.matches(name, receipt.entries[name]):
            raise ValueError("raw evidence differs from original execution: " + name)
    job = reg["job_id"]
    if not re.fullmatch("[0-9]+", job):
        raise ValueError("invalid recorded job ID")
    for moment in ("before", "after"):
        if not successful(result["image_hash_" + moment]):
            raise ValueError("image hashing did not finish")
        expected_hash_line = result["image_sha256"] + "  " + row["image_path"]
        if receipt.read(prefix + "image-hash-" + moment + ".log").splitlines() != [
            expected_hash_line
        ]:
            raise ValueError("recorded image digest or locator differs")
    names = []
    for arm, phase in zip(("baseline", "gold"), result["phases"], strict=True):
        directory = prefix + arm + "/"
        command = receipt.obj(directory + "command.json")
        name = "prun_" + job + "_" + hashlib.sha256(iid.encode()).hexdigest()[:16] + "_" + arm
        dest = (
            "/home/guests/andrei/va/data/tasks/" + current.root.name + "/" + directory.rstrip("/")
        )
        argv = [
            "srun",
            "--jobid=" + job,
            "--exclusive",
            "--exact",
            "--input=none",
            "--nodes=1",
            "--ntasks=1",
            "--cpus-per-task=4",
            "--mem=" + ("24G" if named else "12G"),
            "--cpu-bind=none",
        ]
        argv += [
            "--container-name=" + name if named else "--container-image=" + row["image_path"],
            "--container-writable",
            "--container-remap-root",
            "--no-container-mount-home",
            "--no-container-entrypoint",
            "--container-workdir=/",
            "--container-mounts="
            + dest
            + "/input:/va-prun-input:ro,"
            + dest
            + "/output:/va-prun-output",
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-c",
            (
                "set -e; source /opt/miniconda3/etc/profile.d/conda.sh; conda activate testbed; "
                if row["schema"] == "v1"
                else "set -e; "
            )
            + "exec python /va-prun-input/runner.py "
            + arm,
        ]
        if command["argv"] != argv:
            raise ValueError("phase command differs from reviewed execution policy")
        if digest(receipt.entries[directory + "input/runner.py"]) != RUNNER:
            raise ValueError("unreviewed inside runner")
        if phase["node"] != reg["allocated_nodes"]:
            raise ValueError("phase ran outside recorded allocation")
        if named:
            if (
                command.get("rootfs_name") != name
                or command.get("scratch_parent") != "/mnt/memory/" + current.root.name + "/data"
            ):
                raise ValueError("named rootfs binding differs")
            if not all(successful(phase[key]) for key in ("build", "cleanup")):
                raise ValueError("named rootfs preparation or cleanup failed")
            build = receipt.read(directory + "build.log")
            if (
                "[INFO] Extracting squashfs filesystem..." not in build
                or build.splitlines()[-1] != "tmpfs"
            ):
                raise ValueError("fresh tmpfs extraction not established")
            names.append(name)
    if named and len(set(names)) != 2:
        raise ValueError("baseline and gold reuse a rootfs")
