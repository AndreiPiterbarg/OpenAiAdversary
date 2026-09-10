"""Conservative metadata repair; never infer a test outcome from a prefix match."""

import re


def possible_nodes(text: str) -> set[str]:
    nodes = set()
    for line in text.splitlines():
        m = re.fullmatch(r"(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) (.+)", line)
        if not m:
            continue
        payload = m.group(2)
        nodes.add(payload)
        # A reason delimiter may also occur inside a parameter. Keep every
        # possible boundary; intersection/uniqueness below must disambiguate it.
        if m.group(1) != "PASSED":
            nodes.update(payload[: match.start()] for match in re.finditer(" - ", payload))
    return nodes


def canonicalize(row: dict, baseline: str, gold: str) -> tuple[dict, dict[str, str]]:
    expected = row["FAIL_TO_PASS"] + row["PASS_TO_PASS"]
    common = possible_nodes(baseline) & possible_nodes(gold)
    mapping = {}
    for raw in expected:
        if raw in common and ("[" not in raw or raw.endswith("]")):
            mapping[raw] = raw
            continue
        # Dataset whitespace truncation leaves an unfinished parameter suffix.
        # Ordinary names, complete parameter IDs and ambiguous prefixes refuse.
        if "[" not in raw or raw.endswith("]"):
            raise ValueError("missing identifier is not an unfinished parameter: " + raw)
        choices = {node for node in common if node.startswith(raw + " ") and node.endswith("]")}
        if len(choices) != 1:
            raise ValueError("parameter completion missing or ambiguous: " + raw)
        mapping[raw] = choices.pop()
    if len(set(mapping.values())) != len(expected):
        raise ValueError("identifier completion would merge distinct tests")
    repaired = {
        **row,
        "FAIL_TO_PASS": [mapping[t] for t in row["FAIL_TO_PASS"]],
        "PASS_TO_PASS": [mapping[t] for t in row["PASS_TO_PASS"]],
    }
    return repaired, {k: v for k, v in mapping.items() if k != v}
