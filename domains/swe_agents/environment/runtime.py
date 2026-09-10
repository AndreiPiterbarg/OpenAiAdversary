"""The container runtime the environment drives. A protocol, so tests can substitute a fake."""

from typing import Any, Protocol


class RuntimeUnavailable(RuntimeError):
    """No container runtime is configured; builds fail and are recorded as not reached."""


class Session(Protocol):
    """One running container."""

    def exec(self, command: str, timeout: float) -> tuple[int, str, str]:
        """Run a shell command; return (exit code, stdout, stderr)."""

    def read_file(self, path: str) -> str: ...

    def write_file(self, path: str, content: str) -> None: ...

    def snapshot(self) -> dict[str, Any]:
        """Collect state observations; callers must establish their trust boundary separately."""

    def checkpoint(self) -> None: ...

    def stop(self) -> None: ...


class ContainerRuntime(Protocol):
    """Starts sessions from a repository pin."""

    def start(
        self,
        image: str | None,
        url: str,
        commit: str,
        *,
        workdir: str | None = None,
        python_env: str = "image",
    ) -> Session: ...


class NullRuntime:
    """Placeholder until a Docker-backed runtime exists. Every build fails loudly."""

    def start(self, image: str | None, url: str, commit: str) -> Session:
        raise RuntimeUnavailable(
            "no container runtime configured; see domains/swe_agents/README.md"
        )
