"""Linux syscall confinement for isolated workers; no unconfined fallback."""

import ctypes
import errno
import importlib
import sys

PRELOAD = (
    "math",
    "re",
    "json",
    "random",
    "string",
    "textwrap",
    "collections",
    "itertools",
    "functools",
    "operator",
    "bisect",
    "heapq",
    "statistics",
    "datetime",
    "hashlib",
    "copy",
    "decimal",
    "fractions",
)


def confine() -> None:
    """Install an irreversible seccomp allowlist in a single-threaded worker."""
    if sys.platform != "linux":
        raise RuntimeError("observation confinement requires Linux seccomp")
    for name in PRELOAD:
        importlib.import_module(name)
    library = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    library.seccomp_attr_set.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint32]
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    context = library.seccomp_init(0x00050000 | errno.EPERM)
    if not context:
        raise RuntimeError("seccomp initialization failed")
    # No exec, clone, kill, ptrace, open, socket, mount, chmod, unlink, or file-descriptor
    # acquisition. Only inherited pipe descriptors are available when source starts.
    allowed = (
        "read",
        "write",
        "close",
        "fstat",
        "lseek",
        "brk",
        "mmap",
        "mprotect",
        "munmap",
        "mremap",
        "madvise",
        "futex",
        "clock_gettime",
        "clock_nanosleep",
        "nanosleep",
        "gettimeofday",
        "getrandom",
        "getpid",
        "gettid",
        "getuid",
        "geteuid",
        "getgid",
        "getegid",
        "rt_sigaction",
        "rt_sigprocmask",
        "rt_sigreturn",
        "sigaltstack",
        "exit",
        "exit_group",
        "sched_yield",
    )
    try:
        if library.seccomp_attr_set(context, 4, 1):  # SCMP_FLTATR_CTL_TSYNC
            raise RuntimeError("cannot synchronize syscall confinement across threads")
        for name in allowed:
            number = library.seccomp_syscall_resolve_name(name.encode())
            if number < 0 or library.seccomp_rule_add(context, 0x7FFF0000, number, 0):
                raise RuntimeError(f"cannot install seccomp rule: {name}")
        if library.seccomp_load(context):
            raise RuntimeError("kernel refused observation confinement")
    finally:
        library.seccomp_release(context)
