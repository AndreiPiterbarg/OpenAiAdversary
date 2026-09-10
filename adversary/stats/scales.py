"""Screen-only comparisons of rate and conditional-logit interaction scales."""

from collections.abc import Mapping, Sequence

import numpy as np
from statsmodels.discrete.conditional_models import ConditionalLogit


def sign_class(low: float, high: float) -> str:
    if not np.isfinite([low, high]).all() or low > high:
        return "unmeasurable"
    return "positive" if low > 0 else "negative" if high < 0 else "uncertain"


def difficulty_strata(baseline: Mapping[str, float], cutpoints: Sequence[float]) -> dict[str, int]:
    """Registered numeric baseline cutpoints, independent of any mode labels."""
    if list(cutpoints) != sorted(set(cutpoints)) or any(not 0 < x < 1 for x in cutpoints):
        raise ValueError("strictly increasing registered probability cutpoints required")
    if any(not 0 <= value <= 1 for value in baseline.values()):
        raise ValueError("invalid baseline probabilities")
    return {task: sum(value > cut for cut in cutpoints) for task, value in baseline.items()}


def conditional_logit_interaction(tallies: Mapping[str, Sequence[tuple[int, int]]]) -> dict:
    """Per task: (failures, trials) for empty, A, B, AB; drop constant-response groups."""
    y, x, groups = [], [], []
    informative = 0
    for task, cells in tallies.items():
        if len(cells) != 4 or any(not 0 <= failures <= n or n < 1 for failures, n in cells):
            raise ValueError("four complete binomial task cells required")
        failures, trials = sum(f for f, _ in cells), sum(n for _, n in cells)
        if failures in (0, trials):
            continue
        informative += 1
        for (failed, n), design in zip(
            cells, ((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 1)), strict=True
        ):
            y.extend([1] * failed + [0] * (n - failed))
            x.extend([design] * n)
            groups.extend([task] * n)
    result = {
        "informative_tasks": informative,
        "coefficient": None,
        "interval": None,
        "label": "screen-only",
    }
    if informative < 2:
        return {**result, "refusal": "insufficient informative tasks"}
    try:
        fit = ConditionalLogit(np.array(y), np.array(x), groups=np.array(groups)).fit(disp=False)
        interval = tuple(float(v) for v in fit.conf_int()[2])
        if not np.isfinite([fit.params[2], *interval]).all():
            raise ValueError("nonfinite fit")
        return {
            **result,
            "coefficient": float(fit.params[2]),
            "interval": interval,
            "refusal": "D7 reliability requires independently measured stability",
        }
    except (ValueError, np.linalg.LinAlgError) as exc:
        return {**result, "refusal": f"interaction fit unmeasurable: {exc}"}


def scale_report(tallies: Mapping[str, Sequence[tuple[int, int]]]) -> dict:
    logit = conditional_logit_interaction(tallies)
    if not tallies:
        return {"rate_contrast": None, "logit": logit, "label": "screen-only"}
    contrasts = [
        cells[3][0] / cells[3][1]
        - cells[1][0] / cells[1][1]
        - cells[2][0] / cells[2][1]
        + cells[0][0] / cells[0][1]
        for cells in tallies.values()
    ]
    return {
        "rate_contrast": float(np.mean(contrasts)),
        "tasks": len(tallies),
        "logit": logit,
        "label": "screen-only; coordinate-dependent raw contrast",
    }
