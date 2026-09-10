"""Fail-closed Linux tool guard for a fresh pinned task container.

Landlock confines filesystem access; inherited seccomp denies process and kernel
escape interfaces. This is not a container launcher or a host-wide sandbox. Its
trusted caller supplies private repository/scratch directories and bounded pipes,
and enforces wall time and allocation-level resource limits outside this process.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import os
import platform
import resource
import sys
from pathlib import Path


class GuardUnavailable(RuntimeError):
    """The requested confinement was not installed; do not execute the tool."""


class _Ruleset(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class _PathRule(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


class _Comparison(ctypes.Structure):
    _fields_ = [
        ("arg", ctypes.c_uint),
        ("op", ctypes.c_uint),
        ("datum_a", ctypes.c_uint64),
        ("datum_b", ctypes.c_uint64),
    ]


def _libc() -> ctypes.CDLL:
    if sys.platform != "linux" or platform.machine() not in ("x86_64", "aarch64"):
        raise GuardUnavailable("target guard requires Linux")
    library = ctypes.CDLL(None, use_errno=True)
    library.syscall.restype = ctypes.c_long
    library.prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    library.prctl.restype = ctypes.c_int
    return library


def _no_new_privileges(library: ctypes.CDLL) -> None:
    if library.prctl(38, 1, 0, 0, 0):
        raise GuardUnavailable("PR_SET_NO_NEW_PRIVS failed")


def landlock_abi() -> int:
    """Query support without treating absence as permission to run unconfined."""
    library = _libc()
    abi = library.syscall(444, 0, 0, 1)
    if abi < 3:
        raise GuardUnavailable("Landlock ABI >= 3 is required (including truncate)")
    return int(abi)


def _directory(path: str) -> Path:
    raw = Path(path)
    if not raw.is_absolute() or raw.resolve() != raw or not raw.is_dir():
        raise GuardUnavailable("task directories must be existing canonical absolute paths")
    return raw


def install_filesystem_policy(repo: Path, scratch: Path) -> None:
    library = _libc()
    abi = landlock_abi()
    # ABI 3 supports bits 0..14, including cross-directory references/truncation.
    handled = (1 << 15) - 1
    if abi >= 5:
        handled |= 1 << 15  # IOCTL_DEV, also denied through seccomp below
    attributes = _Ruleset(handled)
    ruleset = library.syscall(444, ctypes.byref(attributes), ctypes.sizeof(attributes), 0)
    if ruleset < 0:
        raise GuardUnavailable("cannot create Landlock ruleset")
    read = (1 << 0) | (1 << 2) | (1 << 3)
    writable = ((1 << 15) - 1) & ~((1 << 6) | (1 << 9) | (1 << 11))
    rules = [(repo, writable), (scratch, writable)]
    rules.extend(
        (Path(p), read)
        for p in ("/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc", "/opt")
        if Path(p).exists()
    )
    rules.extend(((Path("/dev/null"), (1 << 1) | (1 << 2)), (Path("/dev/urandom"), 1 << 2)))
    try:
        for path, access in rules:
            descriptor = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = _PathRule(access, descriptor)
                if library.syscall(445, ruleset, 1, ctypes.byref(rule), 0):
                    raise GuardUnavailable("cannot add Landlock path rule")
            finally:
                os.close(descriptor)
        _no_new_privileges(library)
        if library.syscall(446, ruleset, 0):
            raise GuardUnavailable("cannot restrict filesystem access")
    finally:
        os.close(ruleset)


_DENIED_SYSCALLS = (
    "ptrace",
    "process_vm_readv",
    "process_vm_writev",
    "process_madvise",
    "process_mrelease",
    "kill",
    "tkill",
    "tgkill",
    "rt_sigqueueinfo",
    "rt_tgsigqueueinfo",
    "pidfd_open",
    "pidfd_getfd",
    "pidfd_send_signal",
    "kcmp",
    "setns",
    "unshare",
    "mount",
    "umount",
    "umount2",
    "pivot_root",
    "chroot",
    "move_mount",
    "open_tree",
    "fsopen",
    "fsconfig",
    "fsmount",
    "fspick",
    "mount_setattr",
    "open_by_handle_at",
    "name_to_handle_at",
    "bpf",
    "perf_event_open",
    "io_uring_setup",
    "io_uring_enter",
    "io_uring_register",
    "userfaultfd",
    "keyctl",
    "add_key",
    "request_key",
    "socket",
    "connect",
    "bind",
    "accept",
    "accept4",
    "listen",
    "sendmsg",
    "recvmsg",
    "sendmmsg",
    "recvmmsg",
    "setuid",
    "setgid",
    "setreuid",
    "setregid",
    "setresuid",
    "setresgid",
    "setfsuid",
    "setfsgid",
    "setgroups",
    "capset",
    "setuid32",
    "setgid32",
    "setreuid32",
    "setregid32",
    "setresuid32",
    "setresgid32",
    "setfsuid32",
    "setfsgid32",
    "setgroups32",
    "setrlimit",
    "prlimit64",
    "setsid",
    "setpgid",
    "sched_setaffinity",
    "sched_setscheduler",
    "sched_setparam",
    "sched_setattr",
    "setpriority",
    "ioprio_set",
    # Landlock does not mediate these metadata-changing syscalls on all supported ABIs.
    "chmod",
    "fchmod",
    "fchmodat",
    "fchmodat2",
    "chown",
    "fchown",
    "lchown",
    "fchownat",
    "chown32",
    "fchown32",
    "lchown32",
    "utime",
    "utimes",
    "futimesat",
    "utimensat",
    "setxattr",
    "lsetxattr",
    "fsetxattr",
    "removexattr",
    "lremovexattr",
    "fremovexattr",
    "flock",
    "quotactl",
    "quotactl_fd",
    "acct",
    "swapon",
    "swapoff",
    "reboot",
    "kexec_load",
    "kexec_file_load",
    "init_module",
    "finit_module",
    "delete_module",
    "iopl",
    "ioperm",
    "syslog",
    "_sysctl",
    "sethostname",
    "setdomainname",
    "clock_settime",
    "clock_adjtime",
    "adjtimex",
    "settimeofday",
    "vhangup",
)


def install_syscall_policy() -> None:
    library = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add_array.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.POINTER(_Comparison),
    ]
    library.seccomp_rule_add_array.restype = ctypes.c_int
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_load.restype = ctypes.c_int
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    context = library.seccomp_init(0x7FFF0000)
    if not context:
        raise GuardUnavailable("cannot create seccomp policy")

    def deny(
        name: str, comparison: _Comparison | None = None, *, error: int = errno.EPERM
    ) -> None:
        number = library.seccomp_syscall_resolve_name(name.encode())
        # Recent syscall numbers are shared by the two supported architectures.
        # Unknown names must never silently disable a requested escape restriction.
        recent = {
            "open_tree": 428,
            "move_mount": 429,
            "fsopen": 430,
            "fsconfig": 431,
            "fsmount": 432,
            "fspick": 433,
            "pidfd_open": 434,
            "clone3": 435,
            "pidfd_getfd": 438,
            "process_madvise": 440,
            "mount_setattr": 442,
            "quotactl_fd": 443,
            "process_mrelease": 448,
            "fchmodat2": 452,
        }
        if number == -1:
            number = recent.get(name, -1)
            if number == -1:
                raise GuardUnavailable("libseccomp cannot resolve required syscall: " + name)
        if number < -1:  # Recognized syscall absent on this architecture.
            return
        count = int(comparison is not None)
        pointer = ctypes.byref(comparison) if comparison is not None else None
        if library.seccomp_rule_add_array(
            context, 0x00050000 | error, number, count, pointer
        ):
            raise GuardUnavailable("cannot install seccomp rule: " + name)

    try:
        for name in _DENIED_SYSCALLS:
            deny(name)
        # Private, already-connected local pairs support asyncio's wakeup pipe.
        # Creating/binding/connecting sockets and transferring FDs stay forbidden.
        deny("socketpair", _Comparison(0, 1, 1, 0))  # SCMP_CMP_NE, AF_UNIX
        # Its flags are pointer-based and cannot be inspected by seccomp. ENOSYS
        # lets glibc pthread creation use the filtered legacy clone path below.
        deny("clone3", error=errno.ENOSYS)
        # Only FIONBIO (nonblocking) and FIOCLEX (close-on-exec) are permitted.
        # libseccomp forbids comparing one argument twice in a single rule, so
        # cover the gap between these requests with aligned masked intervals.
        deny("ioctl", _Comparison(1, 2, 0x5421, 0))  # SCMP_CMP_LT, FIONBIO
        deny("ioctl", _Comparison(1, 6, 0x5451, 0))  # SCMP_CMP_GT, FIOCLEX
        first, last = 0x5422, 0x5450
        while first <= last:
            size = first & -first
            while size > last - first + 1:
                size >>= 1
            mask = ((1 << 64) - 1) ^ (size - 1)
            deny("ioctl", _Comparison(1, 7, mask, first))  # SCMP_CMP_MASKED_EQ
            first += size
        # Prevent namespace creation via clone while retaining shell subprocesses.
        for flag in (
            0x00020000,
            0x02000000,
            0x04000000,
            0x08000000,
            0x10000000,
            0x20000000,
            0x40000000,
        ):
            deny("clone", _Comparison(0, 7, flag, flag))  # SCMP_CMP_MASKED_EQ
        # POSIX SETLK/SETLKW support SQLite on repository/scratch files. Write
        # locks require a writable FD, whose acquisition is confined by Landlock.
        for command in (8, 10, 15, 37, 38, 1024, 1026):
            deny("fcntl", _Comparison(1, 4, command, 0))  # SCMP_CMP_EQ
            deny("fcntl64", _Comparison(1, 4, command, 0))
        if library.seccomp_load(context):
            raise GuardUnavailable("kernel refused seccomp policy")
    finally:
        library.seccomp_release(context)


def guarded_exec(
    repo: str, scratch: str, command: list[str], *, cpu_seconds: int = 60
) -> None:
    if type(cpu_seconds) is not int or not 0 < cpu_seconds <= 900:
        raise GuardUnavailable("CPU seconds must be an integer in [1, 900]")
    repository, temporary = _directory(repo), _directory(scratch)
    protected = tuple(
        Path(p)
        for p in (
            "/usr",
            "/lib",
            "/lib64",
            "/bin",
            "/sbin",
            "/etc",
            "/opt",
            "/dev",
            "/proc",
            "/sys",
            "/home",
            "/root",
        )
    )
    if not command or not Path(command[0]).is_absolute():
        raise GuardUnavailable("an absolute executable is required")
    for path in (repository, temporary):
        if path == Path("/") or any(
            path == p or path in p.parents or p in path.parents for p in protected
        ):
            raise GuardUnavailable("writable task paths overlap protected system paths")
    if (
        repository == temporary
        or repository in temporary.parents
        or temporary in repository.parents
    ):
        raise GuardUnavailable("repository and scratch must be disjoint")
    os.chdir(repository)
    # Close inherited descriptors before installing any policy or executing target code.
    _, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    maximum = hard if hard != resource.RLIM_INFINITY else 1_048_576
    os.closerange(3, int(maximum))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    environment = {
        "PATH": str(Path(sys.executable).parent) + ":/usr/local/bin:/usr/bin:/bin",
        "HOME": str(temporary),
        "TMPDIR": str(temporary),
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_ADDOPTS": "-p no:cacheprovider",
        "PYTHONNOUSERSITE": "1",
    }
    _no_new_privileges(_libc())
    install_filesystem_policy(repository, temporary)
    install_syscall_policy()
    os.execve(command[0], command, environment)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--cpu-seconds", type=int, default=60)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        guarded_exec(args.repo, args.scratch, command, cpu_seconds=args.cpu_seconds)
    except Exception as exc:
        print("target guard refused: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        raise SystemExit(125) from exc


if __name__ == "__main__":
    main()
