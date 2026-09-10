"""Small, dependency-free helpers: clocks, canonical hashing and identifiers."""

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import PurePath
from typing import Any


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def _json_default(value: Any) -> Any:
    """Make the values this codebase hashes JSON-serialisable, deterministically."""
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, set | frozenset):
        return sorted(value, key=repr)
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"{type(value).__name__} is not canonically serialisable")


def canonical_json(payload: Any) -> str:
    """Serialise ``payload`` deterministically so equal values hash equally.

    Sorted keys, no whitespace, and a default handler for pydantic models, enums, dates,
    paths and sets so callers never have to pre-process what they hash.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default
    )


def sha256_text(text: str) -> str:
    """Hex SHA-256 of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_json(payload: Any) -> str:
    """Hex SHA-256 of the canonical JSON form of ``payload``."""
    return sha256_text(canonical_json(payload))


def short_id(prefix: str, payload: Any | None = None) -> str:
    """Build a readable identifier.

    Args:
        prefix: Short type tag, e.g. ``"ep"`` or ``"probe"``.
        payload: If given, the id is content-addressed (first 16 hex chars of the payload's
            canonical hash), so the same content always yields the same id. Otherwise a
            random id is produced.

    Returns:
        ``"<prefix>_<16 hex chars>"``.
    """
    digest = sha256_json(payload) if payload is not None else uuid.uuid4().hex
    return f"{prefix}_{digest[:16]}"
