"""Configuration invariants and stable artifact identities."""

import hashlib
from datetime import UTC, date, datetime
from enum import Enum
from functools import cached_property
from pathlib import PurePosixPath

import pytest
from pydantic import ValidationError

from adversary.core import FrozenModel, StrictModel
from adversary.core.util import (
    canonical_json,
    sha256_bytes,
    sha256_json,
    sha256_text,
    short_id,
    utc_now,
)


@pytest.mark.parametrize("base", [FrozenModel, StrictModel])
def test_unknown_fields_and_inherited_cached_copy(base):
    class Parent(base):
        value: int

        @cached_property
        def doubled(self):
            return 2 * self.value

    class Child(Parent):
        pass

    with pytest.raises(ValidationError):
        Child(value=1, extra=2)
    original = Child(value=3)
    assert original.doubled == 6
    for deep in (False, True):
        copied = original.model_copy(update={"value": 5}, deep=deep)
        assert copied.doubled == 10
        assert original.doubled == 6


def test_assignment_validation_and_frozen_fields():
    class Config(StrictModel):
        count: int

    class Artifact(FrozenModel):
        count: int

    config = Config(count=1)
    config.count = 2
    with pytest.raises(ValidationError):
        config.count = "invalid"
    assert config.count == 2
    with pytest.raises(ValidationError):
        Artifact(count=1).count = 2


def test_canonical_supported_types_and_order():
    class Choice(Enum):
        A = "a"

    class Artifact(FrozenModel):
        value: int

    payload = {
        "set": {3, 1},
        "path": PurePosixPath("a/b"),
        "bytes": b"\x00\xff",
        "date": date(2026, 1, 2),
        "enum": Choice.A,
        "model": Artifact(value=1),
        "time": datetime(2026, 1, 2, tzinfo=UTC),
    }
    assert canonical_json(payload) == (
        '{"bytes":"00ff","date":"2026-01-02","enum":"a","model":{"value":1},'
        '"path":"a/b","set":[1,3],"time":"2026-01-02T00:00:00+00:00"}'
    )
    assert sha256_json(payload) == sha256_json(dict(reversed(list(payload.items()))))
    with pytest.raises(TypeError, match="not canonically serialisable"):
        canonical_json(object())


def test_hashes_identifiers_and_clock():
    expected = hashlib.sha256("café".encode()).hexdigest()
    assert sha256_text("café") == sha256_bytes("café".encode()) == expected
    assert short_id("item", {"x": 1}) == "item_" + sha256_json({"x": 1})[:16]
    first, second = short_id("item"), short_id("item")
    assert first != second and len(first) == len(second) == 21
    assert utc_now().utcoffset().total_seconds() == 0
