"""Deterministic near-miss controls; rejection is distinct from semantic detection."""

from __future__ import annotations

from dataclasses import dataclass

PATH = "factory/declarations.py"
TEST_PATH = "tests/test_regression.py"
OLD = "        choice = self.decider.evaluate(instance=instance, step=step, extra={})\n"
GOLD = "        choice = self.decider.evaluate_pre(instance=instance, step=step, overrides={})\n"
START = "    def evaluate_pre(self, instance, step, overrides):\n" + GOLD
BRANCH = "        target = self.yes if choice else self.no\n"
WRAPPER = """        return self._unwrap_evaluate_pre(
            target,
            instance=instance,
            step=step,
            overrides=overrides,
        )
"""


@dataclass(frozen=True)
class Mutation:
    id: str
    sourcefiles: dict[str, str]
    testfiles: dict[str, str]
    why_wrong: str
    original_test_prediction: str
    expected_admission: str = "reject"


def _once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("mutation anchor must occur exactly once")
    return source.replace(old, new, 1)


def build_mutations(
    baseline_sources: dict[str, str],
    gold_sources: dict[str, str],
    baseline_test: str,
    gold_test: str,
) -> list[Mutation]:
    """Return only replacement files; caller applies each to fresh verified baseline.

    Original and supplementary test outcomes must be measured separately. Predictions
    below explain coverage concerns and are never execution evidence.
    """
    if baseline_test != gold_test:
        raise ValueError("baseline and gold must use identical frozen tests")
    if set(baseline_sources) != set(gold_sources):
        raise ValueError("baseline and gold source closures differ")
    base, gold = baseline_sources[PATH], gold_sources[PATH]
    if _once(base, OLD, GOLD) != gold:
        raise ValueError("unexpected gold source delta")
    if any(baseline_sources[k] != gold_sources[k] for k in baseline_sources if k != PATH):
        raise ValueError("unexpected gold changes outside repair file")
    head, tail = gold.split(START, 1)
    body, end = tail.split("    def __repr__(self):", 1)

    def method_edit(old: str, new: str) -> str:
        return head + START + _once(body, old, new) + "    def __repr__(self):" + end

    fixtures = [
        Mutation(
            "wrong_keyword",
            {PATH: _once(gold, GOLD, GOLD.replace("overrides=", "extra="))},
            {},
            "Calls evaluate_pre with its unsupported extra keyword.",
            "expected failure",
            "admit",
        ),
        Mutation(
            "delete_choice",
            {PATH: _once(gold, GOLD, "")},
            {},
            "Reads choice without assigning it.",
            "expected failure",
        ),
        Mutation(
            "invert_condition",
            {PATH: method_edit(BRANCH, BRANCH.replace("if choice", "if not choice"))},
            {},
            "Selects the opposite branch for every decider.",
            "may survive membership-only F2P",
        ),
        Mutation(
            "constant_choice",
            {PATH: _once(gold, GOLD, "        choice = True\n")},
            {},
            "Ignores decider and always chooses the yes branch.",
            "may survive frozen tests",
        ),
        Mutation(
            "constant_yes",
            {PATH: method_edit(BRANCH, "        target = self.yes\n")},
            {},
            "Evaluates decider but ignores false results.",
            "may survive frozen tests",
        ),
        Mutation(
            "hardcoded_locale",
            {PATH: _once(gold, GOLD, OLD.replace("extra={}", 'extra={"locale": None}'))},
            {},
            "Bypasses declaration context preparation and overrides explicit locale/defaults.",
            "may survive frozen tests",
        ),
        Mutation(
            "missing_branch_wrapper",
            {PATH: method_edit(WRAPPER, "        return target\n")},
            {},
            "Returns nested declaration objects without evaluating the selected branch.",
            "may survive frozen tests",
        ),
    ]
    test_header = "    def test_evaluated_without_locale(self):\n"
    if baseline_test.count(test_header) != 1:
        raise ValueError("frozen regression method missing or ambiguous")
    before, method = baseline_test.split(test_header)
    # The pinned regression is the last method; refuse source drift rather than deleting others.
    if "\n    def " in method or "\nclass " in method:
        raise ValueError("unexpected methods after regression")
    weakened = before + test_header + "        self.assertTrue(True)\n"
    skipped = _once(
        baseline_test,
        test_header,
        '    @unittest.skip("mutation control: bypass regression")\n' + test_header,
    )
    fixtures.extend(
        [
            Mutation(
                "weaken_test",
                {PATH: base},
                {TEST_PATH: weakened},
                "Leaves the source bug and replaces the regression with a vacuous assertion.",
                "modified test may pass; frozen test should fail",
            ),
            Mutation(
                "skip_test",
                {PATH: base},
                {TEST_PATH: skipped},
                "Leaves the source bug and skips its regression.",
                "exit zero is possible but skipped expected test must refuse",
            ),
        ]
    )
    return fixtures
