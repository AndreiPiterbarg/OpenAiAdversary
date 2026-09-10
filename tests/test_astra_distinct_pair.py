import json
from types import SimpleNamespace

import pytest

from domains.swe_agents.scripts import astra_distinct_pair as pair


def test_pair_cells_are_full_assignment():
    draft = SimpleNamespace(clauses=('a',), perturbation=object(),
                            channel=SimpleNamespace(value='observation'),
                            pair=SimpleNamespace(control=pair.Cell(levels={'a': 'off'}),
                                                 treatment=pair.Cell(levels={'a': 'on'})))
    assert pair.pair_cell(draft, 'control').levels == {'a': 'off'}
    assert pair.pair_cell(draft, 'treatment').levels == {'a': 'on'}
    with pytest.raises(ValueError):
        pair.pair_cell(draft, 'other')


def test_missing_preparation_preserves_attempt_without_model(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('model must not be instantiated')
    monkeypatch.setattr(pair, 'AstraRelay', forbidden)
    out = tmp_path / 'attempt'
    row = pair.execute(tmp_path, tmp_path / 'missing-draft', 'control', out, 'case-1')
    assert row['status'] == 'unknown'
    assert row['diagnostic_passed'] is None
    assert row['planned'] == 1
    assert json.loads((out / 'result.json').read_text()) == row
    with pytest.raises(FileExistsError):
        pair.execute(tmp_path, tmp_path / 'missing-draft', 'control', out, 'case-1')


def test_host_adapter_binds_budget_condition_and_actual_exposure(tmp_path, monkeypatch):
    draft = SimpleNamespace(clauses=('a',), perturbation=object(),
                            channel=SimpleNamespace(value='observation'),
                            pair=SimpleNamespace(control=pair.Cell(levels={'a': 'off'}),
                                                 treatment=pair.Cell(levels={'a': 'on'})))
    monkeypatch.setattr(pair.ProbeDraft, 'model_validate_json', lambda value: draft)
    monkeypatch.setattr(pair, 'validate_preparation', lambda root: (
        SimpleNamespace(key='repo__bug-1'), object(), 'a' * 40))
    for name in ('original-pin.json', 'host-runtime-pin.json', 'prepared-ref.txt',
                 'baseline-untracked.json', 'compatibility-exact.json', 'draft.json'):
        (tmp_path / name).write_text('{}')
    class Observation:
        def __init__(self, *args):
            self.records = [{'visible_trigger': True}]
            self.prepare_spec = {'observation_limit': 16000}
        def close(self):
            pass
    monkeypatch.setattr(pair, 'AuditedObservation', Observation)
    monkeypatch.setattr(pair, 'AstraRelay', lambda *args, **kwargs: object())
    captured = {}
    def episode(**kwargs):
        captured.update(kwargs)
        return {'status': 'completed', 'diagnostic_passed': True,
                'usage': {'input_tokens': 100, 'output_tokens': 20}}
    monkeypatch.setattr(pair, 'run_episode', episode)
    monkeypatch.setattr(pair, 'clause_exposure', lambda *args: {
        'realized': True, 'status': 'verified', 'clause_visible_contribution': {
            'a': {'exposed': True}, 'b': {'exposed': True}}})
    result = pair.execute(tmp_path, tmp_path / 'draft.json', 'treatment',
                          tmp_path / 'out', 'episode')
    assert result['cell'] == {'a': 'on'}
    assert result['realized'] is True
    assert captured['observation_limit'] == 16000
    assert (captured['max_steps'], captured['max_seconds']) == (100, 600)
    assert captured['sampling_policy']['reasoning_effort'] == 'low'
    def failed_exposure(*args):
        raise ValueError('exposure failed')
    monkeypatch.setattr(pair, 'clause_exposure', failed_exposure)
    failed = pair.execute(tmp_path, tmp_path / 'draft.json', 'treatment',
                          tmp_path / 'failed', 'failed')
    assert failed['status'] == 'unknown'
    assert failed['usage'] == {'input_tokens': 100, 'output_tokens': 20}
