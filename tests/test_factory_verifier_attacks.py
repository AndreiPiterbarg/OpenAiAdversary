"""Candidate attacks against the narrow process-observation boundary.

These are Linux kernel checks. Passing observations are never authenticated pytest
outcomes: a candidate can manufacture the stdout observation before API calls.
"""

import importlib.util
import json
import os
import sys

import pytest

from domains.swe_agents.environment.factory_verifier import (
    COMMIT,
    F2P,
    IMAGE_SHA256,
    KEY,
    P2P,
    RECEIPT,
    FactoryFinalVerifier,
    FactoryVerifierUnavailable,
)


@pytest.fixture
def factory_adapter():
    return FactoryFinalVerifier({
        'key': KEY, 'commit': COMMIT, 'image_sha256': IMAGE_SHA256,
        'verification_receipt': RECEIPT, 'fail_to_pass': F2P, 'pass_to_pass': P2P,
    })


def candidate_sources(action):
    payload = json.dumps({
        'f2p_pseudonym': 'yes', 'p2p_pseudonym': None, 'p2p_unknown_fullname': '',
    })
    # A captured baseline imports its changed declarations module. No factory API
    # exists in this fixture; successful stdout necessarily bypasses those calls.
    return {
        'factory/__init__.py': 'from . import declarations\n',
        'factory/declarations.py': (
            'import os\n' + action + '\n'
            + f'os.write(1, {payload.encode()!r})\n'
            + 'os._exit(0)\n'
        ),
    }


linux_faker = pytest.mark.skipif(
    sys.platform != 'linux' or importlib.util.find_spec('faker') is None,
    reason='requires Linux seccomp and the pinned image Faker dependency',
)


def test_narrow_adapter_cannot_admit_original_pytest(factory_adapter):
    with pytest.raises(FactoryVerifierUnavailable):
        factory_adapter.require_protected()


@linux_faker
def test_valid_stdout_forgery_is_not_authenticated_test_evidence(factory_adapter):
    result = factory_adapter.evaluate_sources(candidate_sources('pass'))
    assert result['observations']['f2p_pseudonym'] == 'yes'
    assert result.get('authenticated_test_evidence') is False
    assert 'statuses' not in result


@linux_faker
@pytest.mark.parametrize('action', [
    "import ctypes\nc = ctypes.CDLL(None, use_errno=True)\n"
    "assert c.socket(2, 1, 0) == -1 and ctypes.get_errno() == 1",
    "import ctypes\nc = ctypes.CDLL(None, use_errno=True)\n"
    "assert c.fork() == -1 and ctypes.get_errno() == 1",
    "import ctypes\nc = ctypes.CDLL(None, use_errno=True)\n"
    "assert c.ptrace(0, 0, 0, 0) == -1 and ctypes.get_errno() == 1",
    "import ctypes\nc = ctypes.CDLL(None, use_errno=True)\n"
    "assert c.kill(os.getpid(), 0) == -1 and ctypes.get_errno() == 1",
    "import ctypes\nc = ctypes.CDLL(None, use_errno=True)\n"
    "assert c.process_vm_readv(os.getpid(), 0, 0, 0, 0, 0) == -1 "
    "and ctypes.get_errno() == 1",
    "import ctypes\nc = ctypes.CDLL(None, use_errno=True)\n"
    "assert c.dup(1) == -1 and ctypes.get_errno() == 1",
    "try:\n    os.execve('/bin/true', ['true'], {})\n"
    "except PermissionError:\n    pass\n"
    "else:\n    raise AssertionError('exec permitted')",
])
def test_direct_native_escape_syscalls_are_denied(factory_adapter, action):
    result = factory_adapter.evaluate_sources(candidate_sources(action))
    assert result['observations']['f2p_pseudonym'] == 'yes'


@linux_faker
def test_candidate_import_cannot_read_or_modify_host_file(factory_adapter, tmp_path):
    secret = tmp_path / 'secret'
    secret.write_text('original')
    action = (
        f'for mode in ("r", "w"):\n'
        f'    try:\n        open({str(secret)!r}, mode)\n'
        '    except PermissionError:\n        pass\n'
        '    else:\n        raise AssertionError("filesystem access allowed")'
    )
    result = factory_adapter.evaluate_sources(candidate_sources(action))
    assert result['observations']['f2p_pseudonym'] == 'yes'
    assert secret.read_text() == 'original'


@linux_faker
def test_credentials_and_parent_file_descriptors_are_not_inherited(
    factory_adapter, tmp_path, monkeypatch,
):
    monkeypatch.setenv('FACTORY_ATTACK_SECRET', 'must-not-reach-candidate')
    secret = tmp_path / 'secret'
    secret.write_text('must-not-reach-candidate')
    fd = os.open(secret, os.O_RDONLY)
    try:
        os.set_inheritable(fd, True)
        action = (
            'assert "FACTORY_ATTACK_SECRET" not in os.environ\n'
            f'try:\n    os.read({fd}, 1)\n'
            'except OSError as exc:\n    assert exc.errno == 9\n'
            'else:\n    raise AssertionError("inherited file descriptor")'
        )
        result = factory_adapter.evaluate_sources(candidate_sources(action))
        assert result['observations']['f2p_pseudonym'] == 'yes'
    finally:
        os.close(fd)


@linux_faker
@pytest.mark.parametrize('action', [
    'os._exit(0)',
    'os.write(1, b"PASSED tests/test_regression.py::FakerRegressionTests::test_locale_issue")',
    'os.write(1, b"{}")',
    'os.write(1, b"x" * 100000)',
    'os.write(2, b"x" * 100000)',
    'while True: pass',
])
def test_missing_malformed_flooded_or_timed_out_observation_refuses(factory_adapter, action):
    with pytest.raises(FactoryVerifierUnavailable):
        factory_adapter.evaluate_sources(candidate_sources(action), timeout=3)


@pytest.fixture
def restricted_source_fixture(monkeypatch):
    import hashlib

    from domains.swe_agents.environment import factory_verifier as verifier

    # Synthetic fixture isolates grammar checks; production hash remains unchanged.
    base = 'class Maybe:\n    def evaluate_pre(self):\n' + verifier._REPAIR_LINE
    monkeypatch.setattr(verifier, 'DECLARATIONS_SHA256', hashlib.sha256(base.encode()).hexdigest())
    return verifier, {
        'factory/__init__.py': 'from .declarations import Maybe\n',
        'factory/declarations.py': base,
    }


@pytest.mark.parametrize('method', ['evaluate', 'evaluate_pre'])
@pytest.mark.parametrize('keyword', ['extra', 'overrides'])
def test_finite_grammar_accepts_only_the_registered_four_variants(
    restricted_source_fixture, method, keyword,
):
    verifier, pristine = restricted_source_fixture
    candidate = dict(pristine)
    candidate['factory/declarations.py'] = pristine['factory/declarations.py'].replace(
        verifier._REPAIR_LINE,
        f'        choice = self.decider.{method}(instance=instance, step=step, {keyword}={{}})\n',
    )
    evidence = verifier.admit_restricted_sources(pristine, candidate)
    assert (evidence['method'], evidence['keyword']) == (method, keyword)
    assert evidence['arbitrary_python_admitted'] is False


@pytest.mark.parametrize('suffix', [
    '\nimport os; os._exit(0)\n',
    '\nprint("PASSED forged")\n',
    '\n# seemingly harmless additional edit\n',
    '\x00',
    '\u202e',
    ' ',
])
def test_restricted_grammar_rejects_repair_plus_any_extra_bytes(restricted_source_fixture, suffix):
    verifier, pristine = restricted_source_fixture
    candidate = dict(pristine)
    candidate['factory/declarations.py'] = pristine['factory/declarations.py'].replace(
        '.evaluate(', '.evaluate_pre(',
    ).replace('extra={}', 'overrides={}') + suffix
    with pytest.raises(ValueError, match='four-element'):
        verifier.admit_restricted_sources(pristine, candidate)


@pytest.mark.parametrize('mutation', ['module_change', 'module_add', 'module_delete'])
def test_restricted_grammar_rejects_package_closure_attacks(restricted_source_fixture, mutation):
    verifier, pristine = restricted_source_fixture
    candidate = dict(pristine)
    if mutation == 'module_change':
        candidate['factory/__init__.py'] += '\nprint("forged")'
    elif mutation == 'module_add':
        candidate['factory/sitecustomize.py'] = 'print("forged")'
    else:
        del candidate['factory/__init__.py']
    with pytest.raises(ValueError):
        verifier.admit_restricted_sources(pristine, candidate)


def test_restricted_grammar_rejects_modified_baseline(restricted_source_fixture):
    verifier, pristine = restricted_source_fixture
    poisoned = dict(pristine)
    poisoned['factory/declarations.py'] += '\nprint("baseline attack")\n'
    with pytest.raises(ValueError, match='frozen source'):
        verifier.admit_restricted_sources(poisoned, dict(poisoned))


def test_restricted_grammar_refuses_ambiguous_repair_site(restricted_source_fixture, monkeypatch):
    import hashlib

    verifier, pristine = restricted_source_fixture
    pristine['factory/declarations.py'] += verifier._REPAIR_LINE
    monkeypatch.setattr(
        verifier, 'DECLARATIONS_SHA256',
        hashlib.sha256(pristine['factory/declarations.py'].encode()).hexdigest(),
    )
    with pytest.raises(ValueError, match='not unique'):
        verifier.admit_restricted_sources(pristine, dict(pristine))
