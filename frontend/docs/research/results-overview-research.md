# Results overview: ranked outcome categories

Research, interactive design previews, and selected implementation, 2026-09-10.

## User decisions

- The overview should show distributions of failure modes and success modes.
- Success means completing the task despite an attack. Passing control runs are excluded.
- Ranked category bars are the selected direction.
- Failure and success occupy separate mirrored lists, distinguished by color, labels, and icons. The latest instruction keeps both bar designs identical and solid; stripes are removed in the product.
- Selecting a mode reveals its example slides, using the established Sentry-style evidence detail.
- After reviewing the three options, the user selected mirrored bars and requested integration with the current Results page styling.

## Inspected references

1. **Plausible: ranked category rows.** [Live dashboard](https://plausible.io/plausible.io), [interaction documentation](https://plausible.io/docs/top-pages), [source repository](https://github.com/plausible/analytics). Inspected the dark dashboard and its ranked source/page rows. Clicking Google changed the scope to that source, added a removable filter, and updated the related breakdown. Removing the filter returned to the overview. Fine transition timing was not measured. Borrow its compact full-row hit areas, clear labels, aligned values, and understated bar fills. Capture: `results-overview-captures/plausible-ranked-bars.png`.

2. **Linear Insights: distribution to matching issues.** [Documentation and screenshot](https://linear.app/docs/insights). Inspected the enlarged official screenshot. The documentation specifies that selecting bars, segments, or table cells filters the associated issue list and highlights corresponding data. Product animation was not verified. Borrow the relationship between category selection and the underlying examples. Capture: `results-overview-captures/linear-insights.png`.

3. **Highcharts: animated drill-down.** [Standalone working example](https://www.highcharts.com/samples/nonav/highcharts/demo/column-drilldown), [demo and source editor](https://www.highcharts.com/demo/highcharts/column-drilldown), [drill-down documentation](https://www.highcharts.com/docs/chart-concepts/drilldown). Clicked the Chrome category in the standalone example and verified that the chart changed from browser categories to Chrome versions, retaining a parent breadcrumb. The documentation explains the animation connecting a selected point to its detail series. No timing claim is based on screenshots. Captures: `highcharts-distribution.png` and `highcharts-drilldown.png` in the captures directory. This is an interaction reference; installing Highcharts is not proposed.

4. **Motion: shared selection and content transitions.** [Working example with View source](https://examples.motion.dev/react/shared-layout-animation?utm_source=embed), [documentation](https://motion.dev/docs/react-layout-animations). Tested tab selection and inspected the source exposed by its View source button. A shared underline follows selection; the content uses a 200ms opacity/vertical-position transition. Borrow continuity between selection and detail, with restrained easing and no decorative spring. The proposed previews use native browser animation, so they need no dependency.

5. **IBM Carbon: choosing a categorical chart.** [Simple charts](https://carbondesignsystem.com/data-visualization/simple-charts/), [spatial charts](https://carbondesignsystem.com/data-visualization/spatial-charts/). Bars support direct category comparisons. Carbon describes treemaps as useful for many hierarchical categories when exact comparisons are secondary. A [Highcharts treemap](https://www.highcharts.com/samples/nonav/highcharts/demo/treemap-with-levels) was also inspected. Ranked bars fit the user's named, textual failure modes more directly; treemaps were not pursued after the user selected bars.

## Three interactive options

- **Separate columns (`dual-lanes.html`), recommended:** independent ranked failure and success lists, both visible. Failures use a warm solid fill and an alert symbol; successes use a muted green patterned fill and a check. The selected category label moves into the detail heading while the evidence area enters. This preserves direct comparison and long labels.
- **Mirrored bars (`mirrored-bars.html`):** failures grow left from a central divider; successes grow right. Lists rank independently; rows across the divider do not imply matching categories or negative values. The selected outcome determines the direction of the detail entrance.
- **Focused outcome views (`focused-outcomes.html`):** a sliding outcome selector exposes one full-width ranked list at a time. The selected underline and incoming list move together; choosing a category carries its label into the detail. This leaves more room for long categories, at the cost of simultaneous comparison.

Each preview supports Context/Evidence slides and a return to all modes. These are simplified interaction previews, not new product routes. They are supplied as inline conversation fragments. The host may expose a transition-duration control. The default duration is 300ms; reduced motion disables movement.

## Data constraints for implementation

The previews explicitly use illustrative bar lengths and no invented evaluation totals. Failure examples use the existing RUN fixtures. Success labels describe prospective categories; successful attacked-run evidence is unavailable and is shown as such. Control outputs are not repurposed as successful attacked runs.

The supplied fixture is a selection of three failure examples, one per current mode. It does not establish model-wide prevalence, a denominator, or an attack-resistance rate. An eventual distribution needs recorded attacked-run outcomes, primary category labels, and per-category examples. Show counts in the selected evaluation scope; calculate shares only with an explicit matching denominator. Keep unavailable follow-up checks separate. Do not double-count examples across primary categories or silently turn overlapping tags into a partition.

The product overview should initially hide the detail explorer. On selection, retain the selected outcome/category as context, show only matching examples, and use success-specific headings and evidence when success is selected. Returning restores the overview and reading position. Keep the enclosing page unboxed.

## Verification

All three fragments parse as JavaScript and were tested in the browser at 736px and 360px. Category selection, failure evidence, success-unavailable states, the outcome switch, Context/Evidence navigation, and return-to-overview controls worked. Narrow layouts had no horizontal overflow. No console errors were reported. Temporary standalone wrappers and the verification server were removed afterward. No application routes, fixture outcomes, or playback behavior changed.

## Selected implementation

The mirrored layout is integrated at `/demo/results`, with the current product’s compact typography and unboxed dark surface. The earlier preview fragments remain design-history artifacts. The product uses the same solid bar shape on both sides, with warm failure fills and muted green success fills. The left and right lists have independent category rankings and share a count scale; opposite rows do not imply paired categories.

The fixture now supplies a typed primary mode and explicit outcomes for both paired arms. `groupResultModes` counts only the attacked arm, ranks modes, and retains their matching examples. The three available failure modes each contain one example. There are no successful attacked-run examples, so the right side states that clearly rather than substituting controls or prospective categories. Counts describe available evidence only.

Selecting a category animates its label into the detail context and opens the existing Sentry evidence view, with mode-specific example navigation. The selected outcome determines entrance direction. Returning restores the category button’s focus and the overview’s scroll position. Motion uses the existing dependency, short eased transitions, and reduced-motion support. Model labels, source evidence, unavailable follow-up checks, and monitor playback remain unchanged.

The user’s follow-up adds a compact footer: show the top three categories per outcome initially, expand to all with Show more, and collapse with Show less. The expanded state survives detail inspection. When no additional categories exist, the footer states that all modes are shown and disables expansion. A component render check with five test-only modes per outcome verified the initial six rows, expansion to ten, both footer states, identical solid fills, and the shared count scale; no additional examples were added to the product.

The next refinement centers an icon-only expansion chevron on the gray divider and removes visible footer text. Its count and action labels remain available to assistive technology. Example text, code, and section spacing are relaxed, and the former purple UI accents are replaced with neutral grays while retaining the outcome colors.
