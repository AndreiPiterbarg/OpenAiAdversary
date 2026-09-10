"""Markdown rendering of an atlas. Python and text only; no dashboard."""

from adversary.report.atlas import Atlas


def _pct(value: float) -> str:
    return f"{100 * value:+.1f}"


def render_markdown(atlas: Atlas) -> str:
    """Render the atlas as a Markdown document."""
    out: list[str] = [f"# {atlas.title}", ""]
    target = atlas.target
    out.append(f"Target: `{target.id}` ({target.version or 'unversioned'}, {target.license})")
    if atlas.registration_sha256:
        out.append(f"Pre-registration: `{atlas.registration_sha256}`")
    out += [f"Generated: {atlas.generated_at.isoformat()}", ""]

    space = atlas.factor_space
    out += ["## Coverage claim", ""]
    out.append(
        f"Factor space `{space.name}` v{space.version}, fingerprint `{space.fingerprint()[:16]}`."
    )
    out.append(f"Claim language: {atlas.coverage_language}.")
    if atlas.plant_recall:
        parts = ", ".join(
            f"order {o}: {r:.2f}" for o, r in sorted(atlas.plant_recall.by_order.items())
        )
        out.append(f"Planted-mode relative recall: {parts}.")
    if atlas.permutation_null:
        out.append(
            "Region test empirical false-discovery rate under permuted labels: "
            f"{atlas.permutation_null.rate:.3f} over "
            f"{atlas.permutation_null.permutations} permutations."
        )
    out.append("")

    if atlas.undeclared_space:
        u = atlas.undeclared_space
        out += ["## Undeclared space (sentinel arm)", ""]
        out.append(
            f"{u.observed_regions} regions in {u.proposals} sentinel proposals; "
            f"discovery probability {u.discovery_probability:.3f}; "
            f"Chao1 lower bound {u.chao1_lower:.1f}"
            + (f"; Chao2 lower bound {u.chao2_lower:.1f}" if u.chao2_lower is not None else "")
            + f"; no extrapolation past {u.extrapolation_limit} proposals."
        )
        out.append("")

    if atlas.interaction_order:
        curve = atlas.interaction_order
        out += ["## Interaction-order curve", ""]
        out += ["| order | cumulative fraction of failing configurations explained |", "|---|---|"]
        for t, frac in zip(curve.orders, curve.cumulative_fraction, strict=True):
            out.append(f"| {t} | {frac:.2f} |")
        out.append("")
        out.append(
            f"{curve.failing_configurations} failing configurations, "
            f"{curve.unexplained} unexplained at order <= {curve.orders[-1]}."
        )
        out.append("")

    out += ["## Hot cells", ""]
    out += [
        "| cell | n | observed | predicted | excess (pts) | 95% CI | one-sided upper | baseline |"
    ]
    out += ["|---|---|---|---|---|---|---|---|"]
    for e in atlas.hot_cells:
        out.append(
            f"| `{e.cell.label()}` | {e.n} | {e.observed:.2f} | {e.predicted:.2f} "
            f"| {e.excess_points:+.1f} | [{_pct(e.ci_low)}, {_pct(e.ci_high)}] "
            f"| {_pct(e.one_sided_upper)} | {e.baseline} |"
        )
    out.append("")

    counts = atlas.grade_counts
    out += ["## Confirmed modes", ""]
    out.append(
        f"{len(atlas.modes)} confirmed: {counts[1]} at grade 1 (found in the wild), "
        f"{counts[2]} at grade 2 (attested, injected on real items); "
        f"{atlas.discovery_free_modes} consist only of deployment conditions."
    )
    out.append("")
    if not atlas.modes:
        out.append("None confirmed.")
    by_id = {m.id: m for m in atlas.modes}
    for ranked in atlas.ranking:
        mode = by_id[ranked.mode_id]
        probe, receipt, imp = mode.probe, mode.receipt, ranked.importance
        out.append(f"### {probe.hypothesis}")
        out.append(f"- Region: `{probe.cell.label()}`; grade {receipt.grade}")
        out.append(
            f"- Real held-out: {receipt.n_mode} mode items, success {receipt.mode_success:.2f}; "
            f"{receipt.n_control} matched control, success {receipt.control_success:.2f}; "
            f"gap {receipt.gap_points:.1f} pts; p={receipt.p_value:.4f}; "
            f"sources {', '.join(receipt.sources)}"
        )
        out.append(
            f"- Importance: {imp.score:.4f} (severity {imp.severity:.1f}, "
            f"prevalence {imp.prevalence.value:.3f} [{imp.prevalence.source}], "
            f"silence {imp.silence:.2f}, systematicity {imp.systematicity:.2f})"
        )
        if probe.excess:
            out.append(f"- Excess on generated data: {probe.excess.excess_points:+.1f} pts")
        out.append(f"- Kills on the way: {probe.killed} killed, {probe.survived} survived")
        for t in probe.evidence.transfer:
            out.append(
                f"- Transfer to `{t.model_id}`: mode {t.mode_failure_rate:.2f} vs control "
                f"{t.control_failure_rate:.2f}, severity ratio {t.severity_ratio:.2f}"
            )
        out.append("")

    gaps = atlas.not_reached
    out += ["## Not reached", ""]
    out.append(f"- Instances that produced no episode: {sum(u.count for u in gaps.unreached)}")
    out += [f"  - `{u.cell.label()}` at {u.stage} x {u.count}" for u in gaps.unreached[:50]]
    out.append(f"- Episodes whose perturbation never applied: {gaps.unrealised_episodes}")
    out.append(f"- Held constant: `{gaps.pinned.label() or 'nothing'}`")
    out.append(f"- Discretised continua: {', '.join(gaps.discretised) or 'none'}")
    out.append(f"- Probes outside the swept envelope: {len(gaps.outside_envelope)}")
    out.append("")

    out += ["## Kill log", "", f"{atlas.killed} killed, {atlas.survived} survived.", ""]
    out += ["| when | verdict | isolated factor | test | effect (pts) | p | hypothesis |"]
    out += ["|---|---|---|---|---|---|---|"]
    for k in sorted(atlas.kills, key=lambda k: k.recorded_at):
        m = k.measured
        out.append(
            f"| {k.recorded_at:%Y-%m-%d %H:%M} | {k.verdict} | {k.pair.factor} | {m.test} "
            f"| {_pct(m.effect)} | {m.p_value:.3f} | {k.hypothesis} |"
        )
    out.append("")

    if atlas.proof:
        proof = atlas.proof
        ships = "yes" if proof.ships else "no"
        margin = f"(margin +/-{100 * proof.margin:.0f} pts)"
        out += ["## Non-regression proof", "", f"Ships: **{ships}** {margin}", ""]
        out += ["| suite | n | before | after | delta | 90% CI | equivalent |"]
        out += ["|---|---|---|---|---|---|---|"]
        for s in proof.suites:
            e = s.equivalence
            out.append(
                f"| {s.name} | {s.n} | {s.before_pass_rate:.3f} | {s.after_pass_rate:.3f} "
                f"| {_pct(e.mean_difference)} | [{_pct(e.ci_low)}, {_pct(e.ci_high)}] "
                f"| {'yes' if e.equivalent else 'no'} |"
            )
        h = proof.honesty
        out.append("")
        if h.determinable:
            out.append(
                f"Honesty probe: honest {h.before.honest_rate:.3f} -> {h.after.honest_rate:.3f}, "
                f"silent failures {h.before.silent_failure_rate:.3f} -> "
                f"{h.after.silent_failure_rate:.3f}; "
                f"moved: {'yes' if h.moved else 'no'}"
            )
        else:
            out.append(
                "Honesty probe: not determinable (a side elicited no self-reports); "
                "counts as moved."
            )
        out.append("")
    return "\n".join(out)
