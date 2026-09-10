"""Repair: fix-set synthesis, training handoff, and the non-regression proof."""

from adversary.repair.fixset import FixExample, FixSet, FixSetSynthesiser
from adversary.repair.handoff import RepairRecipe, TrainingHandoff
from adversary.repair.partition import PoolPartition, SeedPartition
from adversary.repair.proof import NonRegressionProof, ProofResult, SuiteResult

__all__ = [
    "FixExample",
    "FixSet",
    "FixSetSynthesiser",
    "NonRegressionProof",
    "PoolPartition",
    "ProofResult",
    "RepairRecipe",
    "SeedPartition",
    "SuiteResult",
    "TrainingHandoff",
]
