"""Addresses derived only from observed clean calls, including failed clean traces."""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence

from adversary.core.config import FrozenModel
from adversary.core.model import ToolCall
from adversary.core.trajectory import Trajectory
from adversary.core.util import sha256_json


class InjectionPoint(FrozenModel):
    task_pin: str
    target_pin: str
    trace_digest: str
    rank: int
    tool: str
    arguments_digest: str
    occurrence: int

    def matches(self, call: ToolCall, occurrence: int) -> bool:
        return (
            self.tool == call.name
            and self.arguments_digest == sha256_json(call.arguments)
            and self.occurrence == occurrence
        )


def derive_points(
    clean_trace: Trajectory, *, task_pin: str, target_pin: str
) -> tuple[InjectionPoint, ...]:
    trace_digest = sha256_json(clean_trace.model_dump(mode="json"))
    seen: Counter = Counter()
    points = []
    for message in clean_trace.messages:
        for call in message.tool_calls:
            if call.name == "submit":
                continue
            signature = (call.name, sha256_json(call.arguments))
            seen[signature] += 1
            points.append(
                InjectionPoint(
                    task_pin=task_pin,
                    target_pin=target_pin,
                    trace_digest=trace_digest,
                    rank=len(points),
                    tool=call.name,
                    arguments_digest=signature[1],
                    occurrence=seen[signature],
                )
            )
    return tuple(points)


def eligible_kinds(
    point: InjectionPoint, admitted: Mapping[str, Callable[[InjectionPoint], bool]]
) -> tuple[str, ...]:
    """Caller supplies admitted executable operators; this function invents no vocabulary."""
    return tuple(sorted(name for name, eligible in admitted.items() if eligible(point)))


def ranked_points(points: Sequence[InjectionPoint]) -> tuple[InjectionPoint, ...]:
    """Stable observed order, without moving an unmatched address to a different call."""
    return tuple(sorted(points, key=lambda point: (point.rank, point.tool, point.arguments_digest)))
