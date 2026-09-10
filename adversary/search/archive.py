"""The quality-diversity archive: one elite per behaviour niche.

The deliverable is a map, so the search keeps the best probe in each niche and rewards filling
an empty niche over raising an occupied one's score. Niches come from a
:class:`BehaviourDescriptor`. Choosing descriptors by hand is hardcoding smuggled back in
(open question 1 in the spec), so the descriptor is an interface with a hand-chosen baseline
and a failure-signature alternative whose axes are quantised from what was measured.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence

import numpy as np
from pydantic import Field

from adversary.core.config import FrozenModel
from adversary.probe.probe import Probe
from adversary.search.context import EliteSummary

Niche = tuple[str, ...]


class BehaviourDescriptor(ABC):
    """Maps a probe to a discrete niche."""

    name: str = "descriptor"

    @abstractmethod
    def describe(self, probe: Probe) -> Niche:
        """The niche coordinates of ``probe``."""


def measured_signature(probe: Probe) -> list[float]:
    """Default failure signature: numbers the harness measured, never prose.

    Control rate, treatment rate, effect and evidence of the latest falsification, plus the
    silence share when known. Richer signatures (per-channel failure patterns, trajectory
    features) are the R5 research question and plug in through the same callable.
    """
    if not probe.kills:
        return [0.0, 0.0, 0.0, 0.0, 0.0]
    m = probe.kills[-1].measured
    silence = probe.evidence.silence if probe.evidence.silence is not None else 0.0
    return [
        m.control_failures / m.control_n,
        m.treatment_failures / m.treatment_n,
        m.effect,
        -float(np.log10(max(m.p_value, 1e-12))),
        silence,
    ]


class FailureSignatureDescriptor(BehaviourDescriptor):
    """Axes derived from what was measured: quantise failure signatures with a VQ codebook.

    The codebook (plain k-means) keeps the number of niches countable so the archive's
    coverage stays stateable. Must be :meth:`fit` on signatures of probes seen so far.
    """

    name = "failure_signature"

    def __init__(
        self,
        signature: Callable[[Probe], Sequence[float]] = measured_signature,
        codebook_size: int = 16,
        seed: int = 0,
    ) -> None:
        self.signature = signature
        self.codebook_size = codebook_size
        self.seed = seed
        self.codebook: np.ndarray | None = None

    def fit(self, probes: Sequence[Probe], iterations: int = 50) -> None:
        """Lloyd's k-means over the signatures of ``probes``."""
        points = np.array([self.signature(p) for p in probes], dtype=float)
        if len(points) < self.codebook_size:
            raise ValueError(
                f"need at least {self.codebook_size} probes to fit a codebook of that size"
            )
        rng = np.random.default_rng(self.seed)
        codebook = points[rng.choice(len(points), self.codebook_size, replace=False)]
        for _ in range(iterations):
            labels = np.argmin(((points[:, None, :] - codebook[None, :, :]) ** 2).sum(-1), axis=1)
            new = np.array(
                [
                    points[labels == k].mean(0) if np.any(labels == k) else codebook[k]
                    for k in range(self.codebook_size)
                ]
            )
            if np.allclose(new, codebook):
                break
            codebook = new
        self.codebook = codebook

    def describe(self, probe: Probe) -> Niche:
        if self.codebook is None:
            raise RuntimeError("descriptor is not fitted; call fit() on the probes seen so far")
        point = np.asarray(self.signature(probe), dtype=float)
        code = int(np.argmin(((self.codebook - point) ** 2).sum(-1)))
        return (f"code={code}",)


class Elite(FrozenModel):
    """The best probe found in one niche."""

    probe_id: str
    hypothesis: str
    niche: Niche
    score: float = Field(description="Excess over additive, or the measured pair effect as a proxy")


class Placement(FrozenModel):
    """What happened when a probe was offered to the archive."""

    niche: Niche
    inserted: bool
    filled_empty: bool = Field(description="True if the niche was empty; the rewarded outcome")
    displaced: str | None = Field(default=None, description="Probe id replaced, if any")


class Archive:
    """One elite per niche."""

    def __init__(self, descriptor: BehaviourDescriptor) -> None:
        self.descriptor = descriptor
        self._elites: dict[Niche, Elite] = {}
        self._probes: dict[str, Probe] = {}

    def offer(self, probe: Probe, score: float) -> Placement:
        """Insert into an empty niche unconditionally; replace an occupant only if better."""
        niche = self.descriptor.describe(probe)
        incumbent = self._elites.get(niche)
        if incumbent is None:
            self._elites[niche] = Elite(
                probe_id=probe.id, hypothesis=probe.hypothesis, niche=niche, score=score
            )
            self._probes[probe.id] = probe
            return Placement(niche=niche, inserted=True, filled_empty=True)
        if score > incumbent.score:
            self._elites[niche] = Elite(
                probe_id=probe.id, hypothesis=probe.hypothesis, niche=niche, score=score
            )
            self._probes.pop(incumbent.probe_id, None)
            self._probes[probe.id] = probe
            return Placement(
                niche=niche, inserted=True, filled_empty=False, displaced=incumbent.probe_id
            )
        return Placement(niche=niche, inserted=False, filled_empty=False)

    def elites(self) -> list[Elite]:
        """Current occupants, best first."""
        return sorted(self._elites.values(), key=lambda e: -e.score)

    def probe(self, probe_id: str) -> Probe:
        """The stored probe for an elite."""
        return self._probes[probe_id]

    def summary(self) -> tuple[EliteSummary, ...]:
        """For the search context."""
        return tuple(
            EliteSummary(probe_id=e.probe_id, hypothesis=e.hypothesis, niche=e.niche, score=e.score)
            for e in self.elites()
        )

    def __len__(self) -> int:
        return len(self._elites)


class EpochManifest(FrozenModel):
    """Frozen instance-law inputs; the cap does not certify all future outputs of a program."""

    proposer_pin: str
    context_digest: str
    generator_checker_digest: str
    target_pin: str
    admission_policy_digest: str
    score_policy_digest: str
    m: int = Field(ge=1)
    rho: float = Field(default=0.5, gt=0, le=1)
    boundary: str = "research instance draw"


class CappedRelease(FrozenModel):
    epoch_digest: str
    candidate_digests: tuple[str, ...]
    scores: tuple[float, ...]
    retained_indices: tuple[int, ...]
    released_index: int
    release_seed: int
    cap: float
    audited_risk_bound: float | None = None
    refusal: str = "No independent validity audit; research selection mechanism only"


def capped_release(
    epoch: EpochManifest,
    candidate_digests: Sequence[str],
    scores: Sequence[float],
    release_seed: int,
) -> CappedRelease:
    """Retain ceil(rho*m) indices, break score ties by draw order, release uniformly.

    Repeated candidate values remain separate draws. Deduplicating would change the law.
    """
    import math
    import random

    from adversary.core.util import sha256_json

    if len(scores) != epoch.m or len(candidate_digests) != epoch.m:
        raise ValueError("complete fixed admitted batch required before release")
    if any(not math.isfinite(score) for score in scores):
        raise ValueError("score unavailable; cannot complete registered ranking")
    k = math.ceil(epoch.rho * epoch.m)
    retained = tuple(sorted(range(epoch.m), key=lambda i: (-scores[i], i))[:k])
    cap = epoch.m / k
    if cap > 1 / epoch.rho + 1e-12:
        raise ValueError("retention violates registered cap")
    return CappedRelease(
        epoch_digest=sha256_json(epoch.model_dump()),
        candidate_digests=tuple(candidate_digests),
        scores=tuple(scores),
        retained_indices=retained,
        released_index=random.Random(release_seed).choice(retained),
        release_seed=release_seed,
        cap=cap,
    )
