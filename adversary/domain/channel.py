"""Declared intervention surfaces and a conservative oracle isolation gate."""

from collections.abc import Iterable
from enum import StrEnum
from pathlib import PurePosixPath

from pydantic import Field

from adversary.core.config import FrozenModel


class Channel(StrEnum):
    """Where a perturbation may act; these name surfaces, never actions."""

    OBSERVATION = "observation"
    WORKTREE_UNREAD = "worktree_unread"
    HARNESS_CONFIG = "harness_config"
    TASK_TEXT = "task_text"

    @property
    def witness_class(self) -> str:
        return "own" if self is Channel.TASK_TEXT else "inherited"


def relative_path(path: str) -> str:
    """Require canonical relative POSIX paths; ambiguous spellings fail closed."""
    parts = PurePosixPath(path)
    if (
        not path
        or path != parts.as_posix()
        or parts.is_absolute()
        or any(p in (".", "..") for p in parts.parts)
        or "\\" in path
        or "\x00" in path
        or path == "."
    ):
        raise ValueError(f"non-canonical relative path: {path!r}")
    return path


class ChannelCheck(FrozenModel):
    """A mechanical check, separate from build and witness evidence."""

    accepted: bool
    reasons: tuple[str, ...] = ()
    touched: tuple[str, ...] = ()
    witness_class: str
    oracle_invariant: bool = False


class ReadSet(FrozenModel):
    """Protected paths and explicit limits on their completeness."""

    paths: frozenset[str] = Field(default_factory=frozenset)
    complete: bool = False
    reasons: tuple[str, ...] = ()


def check_channel(
    channel: Channel,
    touched: Iterable[str],
    read_set: ReadSet,
    *,
    confined: bool = False,
    own_witness: bool = False,
) -> ChannelCheck:
    """Check trusted observed writes, never the program's self-reported diff.

    ``confined`` attests that runtime capabilities enforce the declared surface. A path
    disjointness test alone cannot constrain future writes or external side effects.
    """
    reasons: list[str] = []
    try:
        paths = tuple(sorted({relative_path(p) for p in touched}))
        protected = tuple(relative_path(p) for p in read_set.paths)
    except ValueError as exc:
        return ChannelCheck(
            accepted=False, reasons=(str(exc),), witness_class=channel.witness_class
        )
    if not confined:
        reasons.append("runtime did not attest confinement to the declared channel")
    if channel is Channel.WORKTREE_UNREAD:
        if not read_set.complete:
            reasons.append("oracle read set is incomplete")
        if any(
            p == r or p.startswith(r + "/") or r.startswith(p + "/")
            for p in paths
            for r in protected
        ):
            reasons.append("intervention overlaps the oracle read set")
    elif paths:
        reasons.append("non-state channel changed persistent state")
    if channel is Channel.TASK_TEXT and not own_witness:
        reasons.append("task_text requires its own successful witness")
    return ChannelCheck(
        accepted=not reasons,
        reasons=tuple(reasons),
        touched=paths,
        witness_class=channel.witness_class,
        oracle_invariant=not reasons and channel is not Channel.TASK_TEXT,
    )
