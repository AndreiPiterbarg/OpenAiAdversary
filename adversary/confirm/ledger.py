"""Versioned mode identity: failing anchors, footprint evidence, then repair evidence."""

from itertools import combinations

from adversary.confirm.receipt import ConfirmedMode
from adversary.core.episode import Episode
from adversary.core.util import sha256_json
from adversary.stats.footprint import FootprintTable, TransferMatrix, chained_components, partitions


class ModeLedger:
    """Never reads a search niche. New pins require fresh confirmation receipts."""

    def __init__(self, target_pin: str) -> None:
        self.target_pin = target_pin
        self.version = 0
        self.entries: dict[str, dict] = {}
        self.history: list[dict] = []
        self.footprints: dict[tuple[str, str], bool | None] = {}
        self.transfer: dict[tuple[str, str], bool | None] = {}

    def admit(self, mode: ConfirmedMode, anchor: Episode, *, target_pin: str) -> str:
        mode = ConfirmedMode.model_validate(mode.model_dump(mode="python"))
        anchor = Episode.model_validate(anchor.model_dump(mode="python"))
        if (
            target_pin != self.target_pin
            or anchor.target_pin != self.target_pin
            or not anchor.measurable
            or not anchor.failed
        ):
            raise ValueError("current-pin measurable failing anchor required")
        if anchor.probe_id != mode.id or anchor.id not in mode.receipt.episode_ids:
            raise ValueError("anchor must belong to the confirmed receipt")
        for existing, entry in self.entries.items():
            if entry["probe_id"] == mode.id:
                self._record(
                    "repeat",
                    {"anchor": existing, "episode": anchor.id, "receipt": mode.receipt.digest},
                )
                return existing
        key = sha256_json([target_pin, anchor.id])
        if key in self.entries:
            return key
        self.entries[key] = {
            "probe_id": mode.id,
            "receipt": mode.receipt.digest,
            "anchor": anchor.id,
            "repairs": [],
        }
        self._record("admit", {"anchor": key})
        return key

    def _record(self, action: str, payload: dict) -> None:
        self.version += 1
        self.history.append({"version": self.version, "action": action, **payload})

    def resolve(self) -> dict:
        relation = {}
        for pair in combinations(sorted(self.entries), 2):
            value = self.transfer.get(pair)
            relation[pair] = self.footprints.get(pair) if value is None else value
        components = partitions(sorted(self.entries), [p for p, same in relation.items() if same])
        return {
            "version": self.version,
            "components": components,
            "chained": chained_components(components, relation),
            "identity_evidence": relation,
        }

    def apply_footprints(self, table: FootprintTable, threshold: float) -> None:
        if table.target_pin != self.target_pin or set(table.values) != set(self.entries):
            raise ValueError("footprints must cover exactly the current-pin anchors")
        if not 0 < threshold <= 1:
            raise ValueError("register a Jaccard threshold in (0,1]")
        self.footprints = {
            tuple(sorted(pair)): None if value is None else value >= threshold
            for pair, value in table.similarities().items()
        }
        self._record(
            "footprints", {"digest": sha256_json(table.model_dump()), "threshold": threshold}
        )

    def apply_transfer(self, matrix: TransferMatrix, threshold: float) -> None:
        if matrix.target_pin != self.target_pin or set(matrix.modes) != set(self.entries):
            raise ValueError("transfer must cover exactly the current-pin anchors")
        self.transfer = {
            tuple(sorted(pair)): value for pair, value in matrix.mutual(threshold).items()
        }
        self._record(
            "transfer", {"digest": sha256_json(matrix.model_dump()), "threshold": threshold}
        )

    def record_repair(self, anchor: str, artifact_digest: str, proof_digest: str) -> None:
        if any(
            len(x) != 64 or any(c not in "0123456789abcdef" for c in x)
            for x in (artifact_digest, proof_digest)
        ):
            raise ValueError("repair artifacts and proof require content digests")
        self.entries[anchor]["repairs"].append({"artifact": artifact_digest, "proof": proof_digest})
        self._record(
            "repair", {"anchor": anchor, "artifact": artifact_digest, "proof": proof_digest}
        )

    def bump(self, target_pin: str) -> "ModeLedger":
        if target_pin == self.target_pin:
            raise ValueError("bump requires a changed target pin")
        new = ModeLedger(target_pin)
        new._record(
            "pin_change",
            {
                "previous_pin": self.target_pin,
                "crosswalk": {anchor: "pending fresh confirmation" for anchor in self.entries},
            },
        )
        return new
