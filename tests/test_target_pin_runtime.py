"""Identity stamps must match observed configuration before any work starts."""

import pytest

from adversary.core.model import PinField, TargetPin
from adversary.execution import EpisodeStore, Harness
from adversary.execution.backends.scripted import ScriptedModel
from tests.toy_domain import make_domain


def pin(**fields):
    unavailable = PinField(status='unpinned', reason='not exposed')
    values = dict.fromkeys(
        ('checkpoint', 'scaffold', 'tool_set', 'decoding_policy', 'quantisation', 'serving_kernel'),
        unavailable,
    )
    values.update(fields)
    return TargetPin(model='scripted', **values)


def test_checkpoint_mismatch_refuses_before_builder_or_model(tmp_path, monkeypatch):
    builder = make_domain().environment
    monkeypatch.setattr(builder, 'verifier', lambda: pytest.fail('verification started'))
    model = ScriptedModel(version='actual')
    harness = Harness(builder, EpisodeStore(tmp_path), target_pin=pin(
        checkpoint=PinField(status='pinned', value='other')
    ))
    with pytest.raises(ValueError, match='checkpoint'):
        harness.run([], model)
    assert model.calls == 0


@pytest.mark.parametrize('field', ['scaffold', 'tool_set', 'decoding_policy', 'quantisation', 'serving_kernel'])
def test_missing_or_different_runtime_binding_refuses(tmp_path, monkeypatch, field):
    builder = make_domain().environment
    model = ScriptedModel()
    harness = Harness(builder, EpisodeStore(tmp_path), target_pin=pin(
        **{field: PinField(status='pinned', value={'observed': 'expected'})}
    ))
    with pytest.raises(ValueError, match=field):
        harness.run([], model)
    monkeypatch.setattr(builder, 'pin_bindings', lambda model, budget: {field: {'observed': 'wrong'}})
    with pytest.raises(ValueError, match=field):
        harness.run([], model)
    assert model.calls == 0


def test_matching_observed_bindings_and_explicit_unknowns_allowed(tmp_path, monkeypatch):
    builder = make_domain().environment
    model = ScriptedModel(version='revision')
    monkeypatch.setattr(builder, 'pin_bindings', lambda model, budget: {'tool_set': ['actual']})
    harness = Harness(builder, EpisodeStore(tmp_path), target_pin=pin(
        checkpoint=PinField(status='pinned', value='revision'),
        tool_set=PinField(status='pinned', value=['actual']),
    ))
    assert harness.run([], model).n == 0


def test_boolean_cannot_equal_integer_in_pinned_decoding(tmp_path, monkeypatch):
    builder = make_domain().environment
    monkeypatch.setattr(builder, 'pin_bindings', lambda model, budget: {'decoding_policy': {'seed': True}})
    harness = Harness(builder, EpisodeStore(tmp_path), target_pin=pin(
        decoding_policy=PinField(status='pinned', value={'seed': 1})
    ))
    with pytest.raises(ValueError, match='decoding_policy'):
        harness.run([], ScriptedModel())
