import pytest

from domains.swe_agents.environment.factory_mutations import (
    BRANCH,
    GOLD,
    OLD,
    PATH,
    START,
    WRAPPER,
    build_mutations,
)


def sources():
    gold = "class Maybe:\n" + START + BRANCH + WRAPPER + "    def __repr__(self):\n        pass\n"
    base = gold.replace(GOLD, OLD)
    test = "import unittest\nclass Tests:\n    def test_evaluated_without_locale(self):\n        pass\n"
    return {PATH: base}, {PATH: gold}, test, test


def test_mutations_are_deterministic_distinct_and_compile():
    first = build_mutations(*sources())
    assert first == build_mutations(*sources())
    assert len({x.id for x in first}) == len(first) == 9
    assert len({x.sourcefiles[PATH] + str(x.testfiles) for x in first}) == 9
    for mutation in first:
        for path, source in {**mutation.sourcefiles, **mutation.testfiles}.items():
            compile(source, path, "exec")
        assert mutation.why_wrong
        assert mutation.original_test_prediction
    assert sum(x.expected_admission == "admit" for x in first) == 1


def test_gold_drift_refuses():
    base, gold, test, _ = sources()
    gold[PATH] += "\n# other change\n"
    with pytest.raises(ValueError, match="gold source delta"):
        build_mutations(base, gold, test, test)


def test_test_drift_refuses():
    base, gold, test, _ = sources()
    with pytest.raises(ValueError, match="identical frozen tests"):
        build_mutations(base, gold, test, test + "\n")


def test_test_mutants_leave_original_bug():
    base, _, _, _ = sources()
    for mutation in build_mutations(*sources()):
        if mutation.testfiles:
            assert mutation.sourcefiles == base
