"""Supplementary deterministic semantic challenges for Factory Boy task 1067.

Run separately from the frozen benchmark tests. These checks add semantic coverage;
passing them is not proof that an arbitrary candidate cannot tamper with pytest.
Only trusted negative mutants or separately admitted candidate code may run here.
"""

from typing import Any

import factory
import pytest


@pytest.mark.parametrize("decision", [False, True])
def test_maybe_preserves_decider_defaults(decision: bool) -> None:
    observed = []

    class DefaultDecider(factory.declarations.BaseDeclaration):
        def evaluate(self, instance: Any, step: Any, extra: dict[str, Any]) -> bool:
            observed.append(dict(extra))
            return extra["decision"]

    selector = factory.Maybe(
        DefaultDecider(decision=decision, marker="preserved-default"),
        yes_declaration="selected-yes",
        no_declaration="selected-no",
    )
    assert selector.evaluate_pre(instance=None, step=None, overrides={}) == (
        "selected-yes" if decision else "selected-no"
    )
    assert observed == [{"decision": decision, "marker": "preserved-default"}]


@pytest.mark.parametrize("decision", [False, True])
@pytest.mark.parametrize("locale", [None, "fr_FR", "de_DE"])
def test_faker_decider_preserves_locale_and_branch(
    monkeypatch: pytest.MonkeyPatch, decision: bool, locale: str | None,
) -> None:
    observed = []

    class Provider:
        def format(self, provider: str, **kwargs: Any) -> bool:
            observed.append((provider, kwargs))
            return decision

    locales = []

    def get_faker(cls: type, selected_locale: str | None = None) -> Provider:
        locales.append(selected_locale)
        return Provider()

    # Replace only the random provider boundary. Factory's defaults merging,
    # Faker.evaluate, Maybe selection, and Factory construction remain real.
    monkeypatch.setattr(factory.Faker, "_get_faker", classmethod(get_faker))

    class ExampleFactory(factory.Factory):
        class Meta:
            model = dict

        value = factory.Maybe(
            factory.Faker("pybool", locale=locale),
            yes_declaration="selected-yes",
            no_declaration="selected-no",
        )

    assert ExampleFactory()["value"] == ("selected-yes" if decision else "selected-no")
    assert locales == [locale]
    assert observed == [("pybool", {})]


@pytest.mark.parametrize("outer", [False, True])
@pytest.mark.parametrize("inner", [False, True])
def test_nested_maybe_evaluates_only_selected_branch(outer: bool, inner: bool) -> None:
    calls = []

    def value(name: str) -> str:
        calls.append(name)
        return name

    nested = factory.Maybe(
        factory.LazyFunction(lambda: inner),
        yes_declaration=factory.LazyFunction(lambda: value("nested-yes")),
        no_declaration=factory.LazyFunction(lambda: value("nested-no")),
    )
    selector = factory.Maybe(
        factory.LazyFunction(lambda: outer),
        yes_declaration=nested,
        no_declaration=factory.LazyFunction(lambda: value("outer-no")),
    )
    expected = ("nested-yes" if inner else "nested-no") if outer else "outer-no"
    assert selector.evaluate_pre(instance=None, step=None, overrides={}) == expected
    assert calls == [expected]


@pytest.mark.parametrize("decision", [False, True])
def test_selected_branch_gets_overrides_without_overriding_decider(decision: bool) -> None:
    observed = []

    class DefaultDecider(factory.declarations.BaseDeclaration):
        def evaluate(self, instance: Any, step: Any, extra: dict[str, Any]) -> bool:
            observed.append(("decider", dict(extra)))
            return extra["decision"]

    class Branch(factory.declarations.BaseDeclaration):
        def evaluate(self, instance: Any, step: Any, extra: dict[str, Any]) -> str:
            observed.append((extra["branch"], dict(extra)))
            return extra["marker"]

    selector = factory.Maybe(
        DefaultDecider(decision=decision, marker="decider-default"),
        yes_declaration=Branch(branch="yes", marker="branch-default"),
        no_declaration=Branch(branch="no", marker="branch-default"),
    )
    assert selector.evaluate_pre(
        instance=None, step=None, overrides={"marker": "call-time-override"},
    ) == "call-time-override"
    assert observed == [
        ("decider", {"decision": decision, "marker": "decider-default"}),
        ("yes" if decision else "no", {
            "branch": "yes" if decision else "no", "marker": "call-time-override",
        }),
    ]
