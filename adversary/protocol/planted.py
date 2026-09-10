"""The planted-mode protocol: measuring our own false-negative rate (Amendment A8).

A Planter independent of the search writes a sealed :class:`PlantManifest`; its hash is
appended to the pre-registration sidecar before the run. A plant is a cell-keyed rate
increment applied by the harness outside the environment, never as text in a prompt, and every
plant carries a canary string that must not appear in any prompt or transcript. Scoring is
*relative recall*: the system's recall over the recall of an oracle that knows the cell, with
found, merged and missed counted separately and reported by interaction order.
"""

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Literal

from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.core.factors import Cell
from adversary.core.planted import PlantedMode
from adversary.core.trajectory import Trajectory
from adversary.core.util import sha256_bytes, short_id


class Plant(FrozenModel):
    """One planted interaction as declared in the manifest."""

    id: str
    cell: Cell = Field(description="Region in which the increment applies")
    increment_points: float = Field(gt=0, description="Probability-scale increment, points")
    silent: bool = Field(description="Whether the forced failure also claims success")
    cross_family: bool = Field(default=False, description="Whether the cell spans both families")
    canary: str = Field(description="Marker that must never appear in a prompt or transcript")

    @property
    def order(self) -> int:
        return self.cell.order


class PlantManifest(FrozenModel):
    """The sealed list of plants for one run."""

    experiment: str
    plants: tuple[Plant, ...] = Field(min_length=1)
    seeds: tuple[int, ...] = Field(
        min_length=1, description="Validation seeds the plants replicate across"
    )

    @staticmethod
    def make_plant(
        cell: Cell, increment_points: float, silent: bool, cross_family: bool = False
    ) -> Plant:
        """Build a plant with a content-derived id and a random canary."""
        canary = short_id("canary")
        return Plant(
            id=short_id("plant", [cell.atoms, increment_points, silent, canary]),
            cell=cell,
            increment_points=increment_points,
            silent=silent,
            cross_family=cross_family,
            canary=canary,
        )

    def seal(self, path: str | Path) -> str:
        """Write the manifest and return its sha256, for the sidecar's file entry."""
        target = Path(path)
        target.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return sha256_bytes(target.read_bytes())

    def modes(self, natural_rates: dict[Cell, float]) -> tuple[PlantedMode, ...]:
        """Turn plants into harness :class:`PlantedMode` objects given each cell's natural rate.

        The forced-failure probability that raises a cell's rate by ``increment_points`` is
        ``increment / (1 - natural)``; see ``stats.calibration.forced_rate_for_excess``.
        """
        modes = []
        for plant in self.plants:
            natural = natural_rates[plant.cell]
            forced = (plant.increment_points / 100.0) / (1.0 - natural)
            modes.append(
                PlantedMode(id=plant.id, cell=plant.cell, failure_rate=forced, silent=plant.silent)
            )
        return tuple(modes)


def leaked_canaries(
    plants: Sequence[Plant], trajectories: Iterable[Trajectory]
) -> list[tuple[str, str]]:
    """``(plant id, trajectory instance id)`` for every canary found in a prompt or transcript."""
    leaks = []
    for trajectory in trajectories:
        text = "\n".join(m.content for m in trajectory.messages)
        for plant in plants:
            if plant.canary in text:
                leaks.append((plant.id, trajectory.instance_id))
    return leaks


Outcome = Literal["found", "merged", "missed"]


class RecallReport(FrozenModel):
    """Which planted modes the pipeline surfaced, and how."""

    planted: int
    found: tuple[str, ...] = Field(description="Plants covered exactly by a found region")
    merged: tuple[str, ...] = Field(
        description="Plants only covered by a found region that is broader than the plant"
    )
    missed: tuple[str, ...]

    @property
    def recall(self) -> float:
        """Found plus merged over planted."""
        return (len(self.found) + len(self.merged)) / self.planted if self.planted else float("nan")

    @property
    def strict_recall(self) -> float:
        """Found alone over planted."""
        return len(self.found) / self.planted if self.planted else float("nan")


def recall(found_regions: Iterable[Cell], plants: Sequence[Plant | PlantedMode]) -> RecallReport:
    """Score found regions against plants.

    A plant is *found* if some region equals or refines its cell (the region covers the plant),
    *merged* if some region is a strict sub-cell of the plant's cell (the region is broader and
    only contains the plant), and *missed* otherwise.
    """
    regions = list(found_regions)
    found, merged, missed = [], [], []
    for plant in plants:
        if any(r.covers(plant.cell) for r in regions):
            found.append(plant.id)
        elif any(plant.cell.covers(r) for r in regions):
            merged.append(plant.id)
        else:
            missed.append(plant.id)
    return RecallReport(
        planted=len(plants), found=tuple(found), merged=tuple(merged), missed=tuple(missed)
    )


class RelativeRecall(FrozenModel):
    """System recall over oracle recall, per interaction order."""

    by_order: dict[int, float] = Field(description="order -> system recall / oracle recall")
    system: dict[int, float]
    oracle: dict[int, float]

    def meets(self, threshold: float, orders: Sequence[int]) -> bool:
        return all(self.by_order.get(o, 0.0) >= threshold for o in orders)


def relative_recall(
    system: RecallReport, oracle: RecallReport, plants: Sequence[Plant]
) -> RelativeRecall:
    """Per-order relative recall; an order the oracle cannot recover at all has no ratio."""
    by_id = {p.id: p.order for p in plants}
    orders = sorted(set(by_id.values()))

    def rate(report: RecallReport, order: int) -> float:
        ids = [i for i, o in by_id.items() if o == order]
        hit = sum(1 for i in ids if i in report.found or i in report.merged)
        return hit / len(ids) if ids else float("nan")

    system_rates = {o: rate(system, o) for o in orders}
    oracle_rates = {o: rate(oracle, o) for o in orders}
    ratio = {
        o: (system_rates[o] / oracle_rates[o]) if oracle_rates[o] > 0 else float("nan")
        for o in orders
    }
    return RelativeRecall(by_order=ratio, system=system_rates, oracle=oracle_rates)
