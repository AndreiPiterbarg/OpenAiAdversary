"""The model-free command line drives the pre-registration protocol."""

import json
from pathlib import Path

import pytest

from adversary.__main__ import main

PREREG = """title: "T"
question: "Q?"
hypothesis: "H"
kill_rules:
  - name: thesis
    all_of:
      - {metric: upper, op: "<", threshold: 0.0}
    consequence: "dead"
analysis_plan: "compute things"
"""



def _experiment(tmp_path: Path) -> Path:
    d = tmp_path / "e99"
    d.mkdir()
    (d / "preregistration.yaml").write_text(PREREG)
    (d / "config.yaml").write_text("target: x\n")
    return d


def test_protocol_commands_refuse_cleanly(tmp_path, capsys):
    d = _experiment(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["verify", str(d)])
    assert exc.value.code == 1 and "register first" in capsys.readouterr().out
    main(["register", str(d)])
    assert (d / "registration.json").exists()
    main(["verify", str(d)])
    assert capsys.readouterr().out.strip().endswith("intact")
    with pytest.raises(SystemExit, match="already registered"):
        main(["register", str(d)])
    with pytest.raises(SystemExit, match="nothing to amend"):
        main(["amend", str(d), "--reason", "no change"])
    with pytest.raises(SystemExit, match="not sealed"):
        main(["decide", str(d)])
    (d / "results").mkdir()
    (d / "results" / "metrics.json").write_text(json.dumps({"upper": -0.5}))
    main(["seal", str(d)])
    main(["decide", str(d)])
    assert json.loads((d / "verdict.json").read_text())["outcome"] == "killed"
    # A broken chain makes verify exit non-zero and decide refuse.
    (d / "config.yaml").write_text("target: y\n")
    with pytest.raises(SystemExit) as exc:
        main(["verify", str(d)])
    assert exc.value.code == 1 and "config.yaml changed" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="chain is broken"):
        main(["decide", str(d)])
