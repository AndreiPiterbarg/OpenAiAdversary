import pytest

from adversary.core.factors import Cell, Factor, FactorSpace, Grounding


def space() -> FactorSpace:
    return FactorSpace(
        name="s",
        factors=(
            Factor(name="lang", levels=("py", "rs"), family="a"),
            Factor(name="build", levels=("uv", "cargo"), family="a"),
            Factor(
                name="haz",
                levels=("none", "flake", "wrong"),
                family="b",
                grounding=Grounding.ATTESTABLE,
            ),
            Factor(name="contam", levels=("absent", "present"), family="a", pinned="absent"),
            Factor(name="drift", levels=("no", "yes"), family="b", grounding=Grounding.UNGROUNDED),
            Factor(
                name="budget",
                levels=("default", "tight"),
                family="b",
                grounding=Grounding.CONDITION,
            ),
        ),
        exclusions=(
            Cell(levels={"lang": "py", "build": "cargo"}),
            Cell(levels={"lang": "rs", "build": "uv"}),
        ),
    )


def test_cell_semantics():
    full = Cell(levels={"lang": "py", "build": "uv", "haz": "flake"})
    part = Cell(levels={"lang": "py", "haz": "flake"})
    assert full.covers(part) and not part.covers(full)
    assert part.order == 2 and full.project(["lang"]) == Cell(levels={"lang": "py"})
    assert hash(part) == hash(Cell(levels={"haz": "flake", "lang": "py"}))
    assert part.atoms == (("haz", "flake"), ("lang", "py"))
    with pytest.raises(ValueError):
        part.merge(Cell(levels={"lang": "rs"}))
    assert part.label() == "haz=flake,lang=py"


def test_space_validation():
    with pytest.raises(ValueError):
        Factor(name="x", levels=("a",))
    with pytest.raises(ValueError):
        Factor(name="x", levels=("a", "b"), pinned="c")
    with pytest.raises(ValueError):
        FactorSpace(
            name="dup",
            factors=(Factor(name="x", levels=("a", "b")), Factor(name="x", levels=("a", "b"))),
        )
    with pytest.raises(ValueError):
        FactorSpace(
            name="bad",
            factors=(Factor(name="x", levels=("a", "b")),),
            exclusions=(Cell(levels={"y": "a", "x": "a"}),),
        )


def test_feasibility_is_pinned_aware():
    s = FactorSpace(
        name="p",
        factors=(
            Factor(name="a", levels=("0", "1")),
            Factor(name="p", levels=("u", "v"), pinned="u"),
        ),
        exclusions=(Cell(levels={"a": "1", "p": "u"}),),
    )
    assert s.is_feasible(Cell(levels={"a": "0"}))
    assert not s.is_feasible(
        Cell(levels={"a": "1"})
    )  # completes the exclusion with the pinned level
    assert not s.is_feasible(Cell(levels={"p": "v"}))  # contradicts the pinned level
    assert list(s.combinations(1)) == [Cell(levels={"a": "0"})]
    c = s.classify(1)
    assert (c.total, c.excluded_by_declaration, len(c.implied_infeasible), c.feasible) == (
        2,
        1,
        0,
        1,
    )


def test_combinations_respect_exclusions_and_pins():
    s = space()
    assert s.size == 2 * 2 * 3 * 2 * 2
    pairs = list(s.combinations(2))
    assert Cell(levels={"lang": "py", "build": "cargo"}) not in pairs
    assert all("contam" not in c for c in pairs)
    assert s.complete(Cell(levels={"lang": "py"}))["contam"] == "absent"
    assert s.pinned_cell == Cell(levels={"contam": "absent"})
    assert s.families == ("a", "b")
    c = s.classify(2)
    assert c.total == c.excluded_by_declaration + len(c.implied_infeasible) + c.feasible
    assert c.excluded_by_declaration == 2 and not c.implied_infeasible


def test_implied_infeasibility_is_exact_through_chains():
    s = FactorSpace(
        name="implied",
        factors=(
            Factor(name="lang", levels=("py", "rs")),
            Factor(name="build", levels=("uv", "cargo")),
            Factor(name="runner", levels=("pytest", "cargo_test")),
            Factor(name="x", levels=("a", "b", "c")),
        ),
        exclusions=(
            Cell(levels={"lang": "py", "build": "cargo"}),
            Cell(levels={"lang": "rs", "build": "uv"}),
            Cell(levels={"lang": "py", "runner": "cargo_test"}),
            Cell(levels={"lang": "rs", "runner": "pytest"}),
            Cell(levels={"build": "uv", "x": "c"}),
        ),
    )
    ghost = Cell(levels={"build": "cargo", "runner": "pytest"})  # one step: no language admits both
    chain = Cell(
        levels={"runner": "pytest", "x": "c"}
    )  # two steps: pytest -> py -> uv, uv excludes x=c
    for cell in (ghost, chain):
        assert s.is_feasible(cell) and not s.is_realisable(cell)
        assert cell not in list(s.combinations(2))
    implied = set(s.implied_infeasible(2))
    assert {ghost, chain, Cell(levels={"build": "uv", "runner": "cargo_test"})} <= implied
    # every realisable pair really extends to a full feasible configuration
    for cell in s.combinations(2):
        assert any(row.covers(cell) for row in _all_rows(s))


def _all_rows(s: FactorSpace) -> list[Cell]:
    from itertools import product

    rows = []
    for levels in product(*(f.levels for f in s.varied)):
        row = Cell(levels=dict(zip((f.name for f in s.varied), levels, strict=True)))
        if s.is_feasible(row):
            rows.append(row)
    return rows


def test_grounding_and_grade():
    s = space()
    assert s.grounding_of(Cell(levels={"lang": "py", "unknown": "z"})) == {
        "lang": Grounding.CONFIRMABLE,
        "unknown": Grounding.UNGROUNDED,
    }
    assert s.grade(Cell(levels={"lang": "py", "budget": "tight"})) == 1
    assert s.grade(Cell(levels={"lang": "py", "haz": "flake"})) == 2
    assert s.grade(Cell(levels={"lang": "py", "drift": "yes"})) is None
    assert s.claimable(Cell(levels={"haz": "wrong"})) and not s.claimable(
        Cell(levels={"drift": "yes"})
    )
    assert not s.contains(Cell(levels={"lang": "go"})) and s.contains(Cell(levels={"lang": "py"}))


def test_fingerprint_and_yaml_roundtrip(tmp_path):
    s = space()
    path = tmp_path / "space.yaml"
    s.to_yaml(path)
    again = FactorSpace.from_yaml(path)
    assert again == s and again.fingerprint() == s.fingerprint()
    bumped = s.model_copy(update={"version": "2"})
    assert bumped.fingerprint() != s.fingerprint()
    regraded = s.model_copy(
        update={
            "factors": (
                *s.factors[:2],
                s.factors[2].model_copy(update={"grounding": Grounding.CONFIRMABLE}),
                *s.factors[3:],
            )
        }
    )
    assert regraded.fingerprint() != s.fingerprint()
