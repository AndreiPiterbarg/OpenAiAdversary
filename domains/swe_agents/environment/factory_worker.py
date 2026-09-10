"""Stdlib-only confined Factory Boy observation worker; never emits verdicts."""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import json
import os
import resource
import sys
import typing
from typing import Any

LIMIT = 2_000_000


class MemoryLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, sources: dict[str, Any]) -> None:
        self.sources = sources

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname == "factory" or fullname.startswith("factory."):
            if fullname not in self.sources:
                raise ImportError("candidate module missing: " + fullname)
            _, package = self.sources[fullname]
            return importlib.util.spec_from_loader(fullname, self, is_package=package)
        return None

    def create_module(self, spec: Any) -> None:
        return None

    def exec_module(self, module: Any) -> None:
        code, package = self.sources[module.__name__]
        module.__file__ = "<captured:" + module.__name__ + ">"
        exec(code, module.__dict__)


def main() -> None:
    capability_fd = int(sys.argv[1])
    confinement_path = sys.argv[2]
    # These trusted modules come from pristine image/site-packages, before candidate imports.
    for name in ("logging", "inspect", "contextlib", "enum", "unittest", "warnings"):
        importlib.import_module(name)
    from faker import Faker

    Faker(locale="en_US").name()
    Faker(locale="en_US").pybool()
    spec = importlib.util.spec_from_file_location("_trusted_confinement", confinement_path)
    confinement = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(confinement)
    raw = sys.stdin.buffer.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("request exceeds byte bound")
    request = json.loads(raw)
    sources = {}
    for path, source in request["sources"].items():
        package = path.endswith("/__init__.py")
        name = path[:-12].replace("/", ".") if package else path[:-3].replace("/", ".")
        sources[name] = (compile(source, "<captured:" + path + ">", "exec"), package)
    for name in list(sys.modules):
        if name == "factory" or name.startswith("factory."):
            del sys.modules[name]
    sys.meta_path.insert(0, MemoryLoader(sources))
    # Only pipes 0/1/2 and the one-way capability descriptor survive this point.
    os.closerange(3, capability_fd)
    os.closerange(capability_fd + 1, 65536)
    os.environ.clear()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    confinement.confine()
    os.write(capability_fd, b"factory-seccomp-v1\n")
    os.close(capability_fd)
    import factory

    class Author(typing.NamedTuple):
        fullname: str
        pseudonym: str | None = None

    class LocaleFactory(factory.Factory):
        class Meta:
            model = Author

        class Params:
            unknown = factory.Trait(fullname="")

        fullname = factory.Faker("name")

    public = LocaleFactory(unknown=False)
    unknown = LocaleFactory(unknown=True)

    class MaybeFactory(factory.Factory):
        fullname = factory.Faker("name")
        pseudonym = factory.Maybe(
            decider=factory.Faker("pybool"), yes_declaration="yes", no_declaration="no"
        )

        class Meta:
            model = Author

    author = MaybeFactory()
    print(
        json.dumps(
            {
                "f2p_pseudonym": author.pseudonym,
                "p2p_pseudonym": public.pseudonym,
                "p2p_unknown_fullname": unknown.fullname,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
