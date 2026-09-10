# Five monitor directions

Open `/demo-lab`. The bottom navigation switches between five complete presentations without resetting the case or the reader's place. Direct links use `?view=breach`, `wiretap`, `counterplay`, `casefile`, or `orbit`. **Replay sample** restarts the three-case sequence for another motion review. **Original** returns to `/demo`.

All five use the unchanged `RUN.cases` content and the existing monitor reducer. Case history, newly available pages, Follow live, immediate explanatory copy, fast code typing, and static findings keep their original behavior. These are alternative story presentations; they do not add a results explorer. The intended review viewport is the full desktop browser.

| Direction | Presentation | Motion |
| --- | --- | --- |
| Breach | Condensed typography, asymmetric editorial spread, attack trajectory | Masked stage changes, rising headings, SVG path drawing, traveling signal, scanning edge |
| Wiretap | Phosphor terminal, oscilloscope, vertical trace index | Sweeping scan, illuminated waveform, animated signal bars, soft terminal arrival |
| Counterplay | Opposing adversary/agent fields and a central fault line | Spring-driven boundary shifts, competing directional motion, split evidence transitions |
| Casefile | Warm paper, serif typography, margin index, ink outcomes | Perspective page arrival, layered sheet, spring-stamped annotation |
| Orbit | Five stage nodes around an interactive spatial instrument | Three rotating 3D rings, traveling points, spring response to pointer movement, orbital stage selection |

The compositions are original. Motion's open-source React library supplies the animation primitives; no paid examples or proprietary site assets are copied. CSS supplies continuous decorative motion, disabled under reduced-motion preferences. Motion handles stage entry/exit, springs, headings, and SVG path drawing.

Research and references:

- [Motion: SVG animation](https://motion.dev/docs/react-svg-animation) — path-length drawing and SVG transforms.
- [Motion: AnimatePresence](https://motion.dev/docs/react-animate-presence) — staged entry and exit.
- [Motion: useSpring](https://motion.dev/docs/react-use-spring) — restrained physical response for the orbital instrument and shifting boundary.
- [Codrops: kinetic typography transitions](https://tympanus.net/codrops/2021/09/29/kinetic-typography-page-transition/) — type as the transition surface, rather than another rounded container.
- [React Bits: Grid Scan](https://reactbits.dev/backgrounds/grid-scan) — reference for scanning geometry; this implementation uses a custom SVG/CSS signal scene.
- [Rauno Freiberg](https://rauno.me/) — reference for restrained typography and detailed interaction.
- [Bruno Simon](https://bruno-simon.com/) — reference for spatial play and interaction as part of the presentation, scaled here to a lightweight instrument.

Validation: `npm run test:demo`, targeted ESLint, TypeScript, and `npm run build`; inspect each direction in the browser, including switching concepts while reviewing a completed step.
