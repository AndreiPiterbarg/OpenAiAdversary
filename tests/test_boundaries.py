"""The product claim as tests: the core knows nothing of the domain; the layers stay apart."""

import ast
import dataclasses
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "adversary"
PY_FILES = sorted(CORE.rglob("*.py"))

# Vocabulary that belongs to the software-engineering plugin, not to the core.
DOMAIN_WORDS = re.compile(
    r"\b(repositor(y|ies)|docker|containers?|containerised|hazards?|github|pytest|swe"
    r"|merged pr|pull request)\b",
    re.IGNORECASE,
)


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("path", PY_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_core_never_imports_a_plugin(path: Path):
    assert not any(m == "domains" or m.startswith("domains.") for m in imports_of(path))


@pytest.mark.parametrize("path", PY_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_core_speaks_no_domain_vocabulary(path: Path):
    hits = sorted({m.group(0).lower() for m in DOMAIN_WORDS.finditer(path.read_text())})
    assert not hits, f"{path.relative_to(ROOT)} mentions {hits}; that belongs in domains/"


def test_stats_touch_no_model_or_environment():
    forbidden = (
        "adversary.core.model",
        "adversary.execution",
        "adversary.domain",
        "adversary.search",
    )
    for path in (CORE / "stats").rglob("*.py"):
        assert not any(m.startswith(forbidden) for m in imports_of(path)), (
            f"{path} imports a model path"
        )


def test_protocol_depends_only_on_core():
    for path in (CORE / "protocol").rglob("*.py"):
        internal = {m for m in imports_of(path) if m.startswith("adversary.")}
        assert all(m.startswith(("adversary.core", "adversary.protocol")) for m in internal), path


def test_package_import_graph_is_acyclic():
    """Edges between top-level adversary packages must form a DAG."""
    edges: dict[str, set[str]] = {}
    for path in PY_FILES:
        parts = path.relative_to(CORE).parts
        if len(parts) < 2:
            continue
        source = parts[0]
        for module in imports_of(path):
            if module.startswith("adversary.") and module.count(".") >= 1:
                target = module.split(".")[1]
                if target != source:
                    edges.setdefault(source, set()).add(target)
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(node: str, trail: list[str]) -> None:
        if node in done:
            return
        assert node not in visiting, f"import cycle: {' -> '.join([*trail, node])}"
        visiting.add(node)
        for nxt in edges.get(node, ()):
            visit(nxt, [*trail, node])
        visiting.discard(node)
        done.add(node)

    for node in list(edges):
        visit(node, [])


def test_domain_has_exactly_three_component_slots():
    from adversary.domain.contract import Domain

    names = {f.name for f in dataclasses.fields(Domain)}
    assert names == {"name", "environment", "reference", "corpus"}
    assert hasattr(Domain, "__slots__")
    from tests.toy_domain import make_domain

    domain = make_domain()
    with pytest.raises((AttributeError, TypeError)):
        domain.fourth_thing = object()  # type: ignore[attr-defined]


def test_plugins_only_depend_on_core_and_themselves():
    for path in (ROOT / "domains").rglob("*.py"):
        for module in imports_of(path):
            assert not module.startswith(("experiments", "tests")), f"{path} imports {module}"
