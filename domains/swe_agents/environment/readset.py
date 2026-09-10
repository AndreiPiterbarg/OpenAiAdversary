"""Conservative static oracle dependencies for Python tasks.

Imports are a lower bound, not proof of every read: plugins, data files, native extensions,
and subprocesses can observe additional paths. V1 must therefore refuse worktree invariance
until a runtime enforces a closed read boundary. Observation-only interventions remain usable.
"""

import ast
from pathlib import Path

from adversary.domain.channel import ReadSet, relative_path

MANIFESTS = frozenset(
    {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "pytest.ini",
        "tox.ini",
        "Pipfile",
        "Pipfile.lock",
        "poetry.lock",
        "uv.lock",
        "pdm.lock",
        "environment.yml",
        "environment.yaml",
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
    }
)


def oracle_read_set(
    root: str | Path,
    fail_to_pass: tuple[str, ...],
    pass_to_pass: tuple[str, ...] = (),
    protected_paths: tuple[str, ...] = (),
) -> ReadSet:
    """Follow local imports, package initialisers, fixtures, manifests and lockfiles.

    Node ids must use file paths, optionally followed by ``::`` selectors. Unresolved ids,
    parsing errors and links are retained as refusal reasons, never silently skipped.
    """
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("read-set root must be a directory")
    files: dict[str, Path] = {}
    reasons = {"static imports cannot certify data, plugin, native or subprocess reads"}
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if ".git" in path.relative_to(root).parts:
            continue
        if path.is_symlink():
            reasons.add(f"symlink requires runtime resolution: {rel}")
        elif path.is_file():
            files[rel] = path
    selected: set[str] = set()
    pending: list[str] = []

    def add(rel: str) -> None:
        if rel in files and rel not in selected:
            selected.add(rel)
            if rel.endswith(".py"):
                pending.append(rel)

    def resolve_module(module: str) -> None:
        parts = module.split(".")
        if not module or any(not p.isidentifier() for p in parts):
            return
        for prefix in ("", "src/"):
            for i in range(1, len(parts) + 1):
                stem = prefix + "/".join(parts[:i])
                add(stem + "/__init__.py")
            stem = prefix + "/".join(parts)
            add(stem + ".py")

    for rel in files:
        name = Path(rel).name
        if (
            name in MANIFESTS
            or name.endswith(".lock")
            or name.startswith("requirements")
            and name.endswith((".txt", ".in"))
        ):
            add(rel)
    for raw in protected_paths:
        rel = relative_path(raw.rstrip("/"))
        if rel not in files:
            selected.add(rel)
        else:
            add(rel)
        for candidate in files:
            if candidate == rel or candidate.startswith(rel + "/"):
                add(candidate)
    if not fail_to_pass:
        reasons.add("empty fail_to_pass suite")
    for node in (*fail_to_pass, *pass_to_pass):
        try:
            rel = relative_path(node.split("::", 1)[0])
        except ValueError:
            reasons.add(f"unresolved test id: {node}")
            continue
        if rel not in files or not rel.endswith(".py"):
            reasons.add(f"unresolved test file: {node}")
        add(rel)
        # An explicitly named oracle input stays protected even when missing or linked.
        # Completeness is still refused; do not erase the known dependency itself.
        selected.add(rel)
        for parent in Path(rel).parents:
            add((parent / "conftest.py").as_posix())
            add((parent / "__init__.py").as_posix())
    while pending:
        rel = pending.pop()
        try:
            tree = ast.parse(files[rel].read_bytes(), filename=rel)
        except (SyntaxError, UnicodeError, OSError) as exc:
            reasons.add(f"cannot parse {rel}: {type(exc).__name__}")
            continue
        package = Path(rel).parent.parts
        if package and package[0] == "src":
            package = package[1:]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    resolve_module(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    if node.level > len(package):
                        reasons.add(f"unresolved relative import in {rel}")
                        continue
                    base = ".".join(package[: len(package) - node.level + 1])
                    module = ".".join(x for x in (base, node.module) if x)
                else:
                    module = node.module or ""
                resolve_module(module)
                for alias in node.names:
                    resolve_module(".".join(x for x in (module, alias.name) if x))
    return ReadSet(paths=frozenset(selected), complete=False, reasons=tuple(sorted(reasons)))
