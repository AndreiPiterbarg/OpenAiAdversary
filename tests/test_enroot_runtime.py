"""Lifecycle and audit checks independent of a working cluster namespace."""

import sys

import pytest

from domains.swe_agents.environment.enroot import EnrootRuntime, EnrootSession
from domains.swe_agents.environment.runtime import RuntimeUnavailable


def test_namespace_denial_prevents_extraction_and_cleans_scratch(tmp_path, monkeypatch):
    image = tmp_path / 'image.sqsh'
    image.write_bytes(b'immutable')
    calls = []

    def denied(self, argv, timeout, *, check=False):
        calls.append(argv)
        raise RuntimeUnavailable('namespace denied')

    monkeypatch.setattr(EnrootSession, '_command', denied)
    scratch = tmp_path / 'scratch'
    with pytest.raises(RuntimeUnavailable, match='namespace denied'):
        EnrootRuntime(scratch).start(str(image), 'https://example.invalid/task', 'a' * 40)
    assert calls == [['enroot-nsenter', '--user', '--mount', '/bin/true']]
    assert list(scratch.iterdir()) == []
    assert image.read_bytes() == b'immutable'


def test_runtime_timeout_cleanup_and_credential_exclusion(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-not-a-key')
    session = EnrootSession(tmp_path, '/task', 'enroot')
    assert 'OPENAI_API_KEY' not in session.env
    try:
        with pytest.raises(RuntimeUnavailable, match='timed out'):
            session._command([sys.executable, '-c', 'import time; time.sleep(10)'], .05)
        assert session._command([sys.executable, '-c', "print('ok')"], 5)[1] == 'ok\n'
    finally:
        session.stop()
    session.stop()
    assert not tmp_path.exists()
    with pytest.raises(RuntimeError, match='closed'):
        session.exec('true', 1)


def test_snapshot_compares_content_not_index(tmp_path, monkeypatch):
    session = EnrootSession(tmp_path, '/task', 'enroot')
    session._baseline = {'edited': 'old', 'deleted': 'old', 'same': 'same'}
    session._packages = {'existing': '1'}
    monkeypatch.setattr(session, '_files', lambda: {'edited': 'new', 'added': 'new', 'same': 'same'})
    monkeypatch.setattr(session, '_installed', lambda: {'existing': '2', 'new-package': '1'})
    snapshot = session.snapshot()
    assert snapshot['changed_files'] == ['added', 'deleted', 'edited']
    assert snapshot['installed_packages']['existing'] == '2'
    assert snapshot['added_packages'] == ['new-package']
    session.stop()


def test_environment_cleanup_stops_session_even_if_observer_close_fails():
    from adversary.core.factors import Cell
    from domains.swe_agents.environment.environment import SweEnvironment
    from tests.test_domain_swe import FakeSession, LateObservation, make_spec

    class Observer(LateObservation):
        def close(self):
            raise RuntimeError('close failed')

    class Session(FakeSession):
        stopped = False

        def stop(self):
            self.stopped = True

    spec, oracle = make_spec()
    session = Session()
    env = SweEnvironment('i', spec, oracle, session, Observer(Cell(levels={'late': 'on'})))
    with pytest.raises(RuntimeError, match='close failed'):
        env.close()
    assert session.stopped


def test_total_token_budget_refuses_before_any_model_call():
    from adversary.core.trajectory import Budget
    from domains.swe_agents.environment.environment import SweEnvironment
    from tests.test_domain_swe import FakeSession, make_spec

    class NeverCalled:
        def complete(self, request):
            raise AssertionError('must not spend tokens')

    spec, oracle = make_spec()
    env = SweEnvironment('i', spec, oracle, FakeSession())
    with pytest.raises(RuntimeUnavailable, match='pre-call input accounting'):
        env.run(NeverCalled(), Budget(max_tokens=100))
