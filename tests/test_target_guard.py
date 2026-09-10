"""Linux kernel attack checks for the target shell boundary; no emulated success."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from domains.swe_agents.environment import target_guard

GUARD = Path(target_guard.__file__).resolve()
LINUX = pytest.mark.skipif(sys.platform != "linux", reason="requires Linux Landlock/seccomp")


def invoke(tmp_path, code, *, environment=None, pass_fds=(), cpu_seconds=60):
    repo, scratch = tmp_path / 'repo', tmp_path / 'scratch'
    repo.mkdir(exist_ok=True)
    scratch.mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, '-I', str(GUARD), '--repo', str(repo.resolve()),
         '--scratch', str(scratch.resolve()), '--cpu-seconds', str(cpu_seconds), '--', sys.executable, '-I', '-c', code],
        capture_output=True, timeout=15,
        env=environment, pass_fds=pass_fds,
    )


def test_nonlinux_guard_is_explicit_refusal(monkeypatch):
    monkeypatch.setattr(target_guard.sys, 'platform', 'darwin')
    with pytest.raises(target_guard.GuardUnavailable, match='Linux'):
        target_guard.landlock_abi()


def test_noncanonical_task_directory_refused(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    link = tmp_path / 'alias'
    link.symlink_to(repo, target_is_directory=True)
    with pytest.raises(target_guard.GuardUnavailable, match='canonical'):
        target_guard._directory(str(link))


@LINUX
def test_real_shell_python_repository_scratch_and_child_inheritance(tmp_path):
    code = '''
import os, pathlib, subprocess, sys
pathlib.Path('result.txt').write_text('repository-write')
pathlib.Path(os.environ['TMPDIR'], 'scratch.txt').write_text('scratch-write')
assert pathlib.Path('/etc/os-release').read_text()
child = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-c',
    'cat result.txt; if cat /proc/self/environ >/dev/null 2>&1; then exit 1; fi'], capture_output=True)
assert child.returncode == 0, child.stderr
assert child.stdout == b'repository-write'
print('guarded-child-ok')
'''
    result = invoke(tmp_path, code)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == b'guarded-child-ok\n'
    assert (tmp_path / 'repo/result.txt').read_text() == 'repository-write'
    assert (tmp_path / 'scratch/scratch.txt').read_text() == 'scratch-write'


@LINUX
def test_filesystem_read_write_symlink_and_metadata_escape_denied(tmp_path):
    secret = tmp_path / 'outside.txt'
    secret.write_text('unchanged')
    code = f'''
import os, pathlib
outside = {str(secret)!r}
for name in (outside, '/proc/self/environ', '/proc/self/mem', '/sys/kernel/uevent_seqnum'):
    try: open(name, 'rb')
    except (PermissionError, FileNotFoundError): pass
    else: raise AssertionError('read outside policy: ' + name)
for operation in (lambda: open(outside, 'w'), lambda: os.chmod(outside, 0),
                  lambda: os.truncate(outside, 0), lambda: os.utime(outside, None)):
    try: operation()
    except PermissionError: pass
    else: raise AssertionError('outside mutation allowed')
os.symlink(outside, 'escape')
for mode in ('r', 'w'):
    try: open('escape', mode)
    except PermissionError: pass
    else: raise AssertionError('symlink escaped')
print('filesystem-denied')
'''
    result = invoke(tmp_path, code)
    assert result.returncode == 0, result.stderr.decode()
    assert secret.read_text() == 'unchanged'
    assert result.stdout == b'filesystem-denied\n'


@LINUX
@pytest.mark.parametrize('expression', [
    'c.socket(2, 1, 0)', 'c.socketpair(2, 1, 0, 0)',
    'c.kill(PARENT, 0)', 'c.ptrace(0, 0, 0, 0)',
    'c.process_vm_readv(PARENT, 0, 0, 0, 0, 0)',
    'c.process_vm_writev(PARENT, 0, 0, 0, 0, 0)',
    'c.unshare(0)', 'c.setns(-1, 0)', 'c.setsid()',
    'c.setuid(os.getuid())', 'c.prlimit64(PARENT, 0, 0, 0)',
])
def test_direct_process_network_and_namespace_syscalls_denied(tmp_path, expression):
    code = (
        'import ctypes, os\nc = ctypes.CDLL(None, use_errno=True)\n'
        f'assert {expression.replace("PARENT", str(os.getpid()))} == -1\n'
        'assert ctypes.get_errno() == 1\nprint("syscall-denied")\n'
    )
    result = invoke(tmp_path, code)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == b'syscall-denied\n'


@LINUX
def test_no_credentials_or_inherited_extra_descriptors(tmp_path):
    secret = tmp_path / 'secret'
    secret.write_text('not-in-child')
    descriptor = os.open(secret, os.O_RDONLY)
    try:
        environment = {**os.environ, 'OPENAI_API_KEY': 'fake-test-credential'}
        code = f'''
import os
assert 'OPENAI_API_KEY' not in os.environ
try: os.read({descriptor}, 1)
except OSError as exc: assert exc.errno == 9
else: raise AssertionError('inherited secret descriptor')
print('no-credentials')
'''
        result = invoke(tmp_path, code, environment=environment, pass_fds=(descriptor,))
        assert result.returncode == 0, result.stderr.decode()
        assert result.stdout == b'no-credentials\n'
    finally:
        os.close(descriptor)


@LINUX
def test_policy_cannot_be_removed_by_descendant_exec(tmp_path):
    child = "import os; open('/proc/self/environ').read()"
    code = (
        'import subprocess,sys\n'
        f'r=subprocess.run([sys.executable,"-I","-c",{child!r}],capture_output=True)\n'
        'assert r.returncode != 0\nassert b"PermissionError" in r.stderr\nprint("inherited")'
    )
    result = invoke(tmp_path, code)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == b'inherited\n'


@LINUX
def test_python_script_launcher_and_only_cloexec_ioctl_allowed(tmp_path):
    code = '''
import ctypes, fcntl, os, pathlib, subprocess, sys
pathlib.Path('script.py').write_text("print('script-launch-ok')\\n")
child = subprocess.run([sys.executable, '-I', 'script.py'], capture_output=True)
assert child.returncode == 0, child.stderr
assert child.stdout == b'script-launch-ok\\n'
c = ctypes.CDLL(None, use_errno=True)
with open('script.py') as script:
    fd = script.fileno()
    assert c.ioctl(fd, 0x5451, 0) == 0
    assert fcntl.fcntl(fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC
    for request in (*range(0x5422, 0x5451), 0x5412, 0x541B, 0, 0x5452, 0xFFFFFFFF):
        assert c.ioctl(fd, request, 0) == -1
        assert ctypes.get_errno() == 1
print('launcher-and-ioctl-ok')
'''
    result = invoke(tmp_path, code)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == b'launcher-and-ioctl-ok\n'


@LINUX
def test_private_asyncio_threads_and_sqlite_work_without_external_sockets(tmp_path):
    code = '''
import asyncio, ctypes, errno, socket, sqlite3, threading
c = ctypes.CDLL(None, use_errno=True)
assert c.syscall(435, 0, 0) == -1
assert ctypes.get_errno() == errno.ENOSYS
seen = []
thread = threading.Thread(target=lambda: seen.append('thread-ok'))
thread.start()
thread.join(timeout=5)
assert seen == ['thread-ok']
async def task():
    await asyncio.sleep(0)
    return 'async-ok'
assert asyncio.run(task()) == 'async-ok'
left, right = socket.socketpair(socket.AF_UNIX)
left.send(b'private')
assert right.recv(7) == b'private'
try:
    left.sendmsg([b'forbidden'])
except PermissionError:
    pass
else:
    raise AssertionError('sendmsg allowed')
left.close()
right.close()
for family in (socket.AF_INET, socket.AF_UNIX):
    try: socket.socket(family)
    except PermissionError: pass
    else: raise AssertionError('external socket creation allowed')
with sqlite3.connect('coverage.sqlite') as database:
    database.execute('create table counts (n integer)')
    database.execute('insert into counts values (7)')
with sqlite3.connect('coverage.sqlite') as database:
    assert database.execute('select n from counts').fetchall() == [(7,)]
print('private-runtime-ok')
'''
    result = invoke(tmp_path, code)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == b'private-runtime-ok\n'


@pytest.mark.parametrize('limit', [0, -1, 901, 1.5, True])
def test_invalid_cpu_budget_refused_before_execution(limit):
    with pytest.raises(target_guard.GuardUnavailable, match='CPU seconds'):
        target_guard.guarded_exec('/missing', '/missing', ['/bin/true'], cpu_seconds=limit)


@LINUX
def test_trusted_cpu_budget_is_applied_and_cannot_be_raised(tmp_path):
    result = invoke(tmp_path, '''
import ctypes, platform, resource
limits = (ctypes.c_ulonglong * 2)()
c = ctypes.CDLL(None, use_errno=True)
number = 97 if platform.machine() == 'x86_64' else 163
assert c.syscall(number, resource.RLIMIT_CPU, ctypes.byref(limits)) == 0
assert tuple(limits) == (900, 900)
assert c.setrlimit(resource.RLIMIT_CPU, ctypes.byref(limits)) == -1
assert ctypes.get_errno() == 1
print('trusted-budget')
''', cpu_seconds=900)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == b'trusted-budget\n'


@pytest.mark.parametrize('bound, requested, expected', [(60, 900, 60), (900, 900, 900)])
def test_guarded_session_passes_only_trusted_effective_cpu_budget(bound, requested, expected):
    import shlex

    from domains.swe_agents.environment.guarded_session import GuardedSession

    class Raw:
        def exec(self, command, timeout):
            self.command, self.timeout = shlex.split(command), timeout
            return 0, '', ''

    raw = Raw()
    session = GuardedSession(raw, '/repo', '/scratch', '/private/guard.py', b'guard', command_timeout=bound)
    session.exec('pytest --version', requested)
    assert raw.command[raw.command.index('--cpu-seconds') + 1] == str(expected)
    assert raw.timeout == expected


@LINUX
def test_host_policy_exact_runtime_and_memory_bound(tmp_path):
    if os.getuid() == 0:
        pytest.skip('host policy refuses root where NPROC is ineffective')
    repo, scratch, runtime = (tmp_path / p for p in ('repo', 'scratch', 'runtime'))
    for path in (repo, scratch, runtime):
        path.mkdir()
    (runtime / 'marker').write_text('trusted')
    outside = tmp_path / 'host-secret'
    outside.write_text('not-readable')
    code = f'''
from pathlib import Path
import os
assert Path({str(runtime / 'marker')!r}).read_text() == 'trusted'
for path,mode in [({str(outside)!r},'r'),('/etc/hostname','r'),
                  ({str(runtime / 'marker')!r},'w'),('/proc/self/environ','r')]:
 try: open(path,mode)
 except PermissionError: pass
 else: raise AssertionError((path,mode))
assert 'HOST_SECRET' not in os.environ
try: bytearray(600 * 1024**2)
except MemoryError: pass
else: raise AssertionError('address space cap missing')
print('host-boundary-ok')
'''
    result = subprocess.run(
        [sys.executable, '-I', str(GUARD), '--repo', str(repo.resolve()),
         '--scratch', str(scratch.resolve()), '--host-runtime', str(runtime.resolve()),
         '--host-nproc', '512', '--', sys.executable, '-I', '-c', code],
        capture_output=True, text=True, timeout=15,
        env={**os.environ, 'HOST_SECRET': 'must-not-inherit'},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'host-boundary-ok'


@pytest.mark.parametrize('limit', [0, 4097, True])
def test_host_process_limit_invalid_fails_before_exec(tmp_path, monkeypatch, limit):
    repo, scratch, runtime = (tmp_path / p for p in ('repo', 'scratch', 'runtime'))
    for path in (repo, scratch, runtime):
        path.mkdir()
    monkeypatch.setattr(target_guard.os, 'getuid', lambda: 1031)
    with pytest.raises(target_guard.GuardUnavailable, match='process cap'):
        target_guard.guarded_exec(str(repo.resolve()), str(scratch.resolve()),
                                 ['/bin/true'], host_runtime=str(runtime.resolve()),
                                 host_nproc=limit)
