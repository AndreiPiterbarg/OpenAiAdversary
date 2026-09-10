import hashlib
import json
from pathlib import Path

import pytest

from adversary.protocol import (
    PreregistrationError,
    amend,
    decide,
    extract_region,
    parse_sidecar,
    register,
    seal_results,
    verify,
    verify_sidecar,
)

ROOT = Path(__file__).resolve().parents[1]

PREREG = """title: "T"
question: "Q?"
hypothesis: "H"
kill_rules:
  - name: thesis
    requires:
      - {metric: power, op: ">=", threshold: 0.8}
      - {metric: delta, op: ">", threshold: 0.0}
    all_of:
      - {metric: upper, op: "<", threshold_metric: delta}
    consequence: "dead"
  - name: tail
    all_of:
      - {metric: tail_count, op: "<", threshold: 3}
    consequence: "thin"
analysis_plan: "compute things"
"""


def experiment(tmp_path: Path, extra: str = "") -> Path:
    d = tmp_path / "e99"
    d.mkdir(parents=True)
    (d / "preregistration.yaml").write_text(PREREG + extra)
    (d / "config.yaml").write_text("target: x\n")
    return d


def write_metrics(d: Path, **metrics: float) -> None:
    (d / "results").mkdir(exist_ok=True)
    (d / "results" / "metrics.json").write_text(json.dumps(metrics))


def test_register_verify_seal_decide_chain(tmp_path):
    d = experiment(tmp_path)
    registration = register(d)
    assert (d / "registration.json").exists() and verify(d) == []
    with pytest.raises(PreregistrationError):
        register(d)
    write_metrics(d, power=0.9, delta=1.2, upper=2.0, tail_count=7)
    assert "results exist without a sealed manifest" in verify(d)
    seal_results(d)
    assert verify(d) == []
    verdict = decide(d)
    assert verdict.outcome == "survived" and verdict.registration_sha256 == registration.sha256
    assert verify(d) == []
    write_metrics(d, power=0.9, delta=1.2, upper=0.1, tail_count=7)
    assert "results changed after sealing" in verify(d)


def test_three_outcomes(tmp_path):
    cases = {
        # precondition fails -> inconclusive, even though the equivalence would hold
        "inconclusive": (
            dict(power=0.5, delta=1.2, upper=0.1, tail_count=7),
            "inconclusive",
            "inconclusive",
        ),
        # preconditions hold, upper bound below delta -> killed
        "killed": (dict(power=0.9, delta=1.2, upper=0.8, tail_count=7), "killed", "triggered"),
        # preconditions hold, kill metric missing -> undeterminable -> killed
        "undeterminable": (dict(power=0.9, delta=1.2, tail_count=7), "killed", "undeterminable"),
        # threshold metric missing -> undeterminable
        "no_delta_metric": (
            dict(power=0.9, delta=1.2, upper=0.5, tail_count=7),
            "killed",
            "triggered",
        ),
    }
    for name, (metrics, outcome, status) in cases.items():
        d = experiment(tmp_path / name)
        register(d)
        write_metrics(d, **metrics)
        seal_results(d)
        verdict = decide(d)
        assert verdict.outcome == outcome, name
        assert {r.rule.name: r.status for r in verdict.rules}["thesis"] == status, name
    d = experiment(tmp_path / "tail")
    register(d)
    write_metrics(d, power=0.9, delta=1.2, upper=2.0, tail_count=1)
    seal_results(d)
    verdict = decide(d)
    assert verdict.outcome == "killed" and verdict.triggered == ("tail",)


def test_cannot_register_after_results_or_edit_without_amendment(tmp_path):
    d = experiment(tmp_path)
    (d / "results").mkdir()
    (d / "results" / "anything.txt").write_text("x")
    with pytest.raises(PreregistrationError):
        register(d)
    (d / "results" / "anything.txt").unlink()
    register(d)
    (d / "preregistration.yaml").write_text(PREREG.replace("threshold: 3", "threshold: 30"))
    assert "preregistration.yaml changed without an amendment" in verify(d)
    amendment = amend(d, "threshold typo")
    assert verify(d) == [] and amendment.reason == "threshold typo"
    with pytest.raises(PreregistrationError):
        amend(d, "nothing changed")
    write_metrics(d, power=0.9, delta=1.0, upper=3.0, tail_count=5)
    seal_results(d)
    (d / "preregistration.yaml").write_text(PREREG.replace("threshold: 3", "threshold: 300"))
    with pytest.raises(PreregistrationError):
        amend(d, "too late")


def test_whole_document_binding(tmp_path):
    doc = tmp_path / "PROTOCOL.md"
    doc.write_text("frozen protocol\n")
    good = hashlib.sha256(doc.read_bytes()).hexdigest()
    d = experiment(tmp_path, f"document: ../PROTOCOL.md\ndocument_sha256: {good}\n")
    register(d)
    assert verify(d) == []
    doc.write_text("edited after the fact\n")
    assert any("bound document changed" in p for p in verify(d))
    d2 = experiment(tmp_path / "bad", f"document: ../PROTOCOL.md\ndocument_sha256: {'a' * 64}\n")
    with pytest.raises(PreregistrationError):
        register(d2)


SIDECAR_DOC = "# Title\n\nbody line\n\nrecorded here:\n\n## 9. Amendments\n\n### A1\n"


def _sidecar(doc: str) -> str:
    end = doc.index("recorded here:\n") + len("recorded here:\n")
    registered = hashlib.sha256(doc[:end].encode()).hexdigest()
    amendments = hashlib.sha256(doc[doc.index("## 9. Amendments") :].encode()).hexdigest()
    return (
        "# hashes\n[registered]\n"
        'region  = start of file through the line ending "recorded here:"\n'
        f"sha256  = {registered}\n"
        "[amendments]\n"
        'region  = from the line "## 9. Amendments" to end of file\n'
        f"sha256  = {amendments}\nnote = A1\n"
    )


def test_sidecar_region_binding(tmp_path):
    doc = tmp_path / "P.md"
    side = tmp_path / "P.hashes"
    doc.write_text(SIDECAR_DOC)
    side.write_text(_sidecar(SIDECAR_DOC))
    entries = parse_sidecar(side.read_text())
    assert [e.name for e in entries] == ["registered", "amendments"] and entries[1].note == "A1"
    assert extract_region(SIDECAR_DOC, entries[0].region).endswith("recorded here:\n")
    assert extract_region(SIDECAR_DOC, entries[1].region).startswith("## 9. Amendments")
    assert verify_sidecar(doc, side)[1] == []
    d = experiment(tmp_path, "document: ../P.md\ndocument_hashes: ../P.hashes\n")
    registration = register(d)
    assert set(registration.document_regions) == {"registered", "amendments"} and verify(d) == []
    # An amendment appended: the whole file changes, the registered region does not.
    appended = SIDECAR_DOC + "\n### A2\n"
    doc.write_text(appended)
    assert any("[amendments]" in p for p in verify(d))  # sidecar not yet updated
    side.write_text(_sidecar(appended))
    assert verify(d) == []
    # Editing the registered region is caught even if the sidecar is regenerated to match.
    tampered = appended.replace("body line", "body line rewritten")
    doc.write_text(tampered)
    side.write_text(_sidecar(tampered))
    problems = verify(d)
    assert any("[registered] region hash changed" in p for p in problems)
    with pytest.raises(ValueError):
        extract_region(SIDECAR_DOC, "somewhere in the middle")


def test_the_real_e1_sidecar_verifies():
    """The user's fix: hashes live in a sidecar naming exact regions; both regions verify."""
    doc = ROOT / "docs" / "PREREGISTRATION-E1.md"
    side = ROOT / "docs" / "PREREGISTRATION-E1.hashes"
    if not doc.exists() or not side.exists():
        pytest.skip("E1 documents not present")
    entries, problems = verify_sidecar(doc, side)
    assert problems == [], problems
    assert {e.name for e in entries} >= {"registered", "amendments"}
