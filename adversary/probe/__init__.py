"""Probe exports, loaded on demand so program workers need no statistics stack."""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "Evidence": "adversary.probe.evidence",
    "HeldOutRef": "adversary.probe.evidence",
    "TransferResult": "adversary.probe.evidence",
    "KillRecord": "adversary.probe.kill",
    "MeasuredOutcome": "adversary.probe.kill",
    "MinimalPair": "adversary.probe.kill",
    "Prediction": "adversary.probe.kill",
    "LicenseError": "adversary.probe.library",
    "ProbeLibrary": "adversary.probe.library",
    "Probe": "adversary.probe.probe",
    "ProbeProvenance": "adversary.probe.probe",
    "ProbeStatus": "adversary.probe.probe",
    "ProgramError": "adversary.probe.program",
    "ProgramKind": "adversary.probe.program",
    "ProgramSource": "adversary.probe.program",
}
__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(_EXPORTS[name]), name)
    globals()[name] = value
    return value
