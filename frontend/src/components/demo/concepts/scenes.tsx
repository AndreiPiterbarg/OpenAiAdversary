"use client";

import { type CSSProperties, type ReactNode } from "react";
import { AnimatePresence, motion, useSpring, type TargetAndTransition } from "motion/react";
import { ArrowDownRight, ArrowUpRight, Check, Crosshair } from "lucide-react";
import { RUN } from "@/lib/demo/run-data";
import { Evidence } from "./evidence";
import type { LiveRun } from "./use-live-run";
import type { Concept } from "./concept-lab";
import s from "./concepts.module.css";

const number = (index: number) => String(index + 1).padStart(2, "0");

export function StageNav({ run, className = "" }: { run: LiveRun; className?: string }) {
  return <nav className={`${s.stageNav} ${className}`} aria-label="Run stages">
    {run.currentCase.steps.map((step, i) => <button type="button" key={step.id}
      disabled={!run.available(i)} aria-current={i === run.stepIndex ? "step" : undefined}
      onClick={() => run.dispatch({ type: "select-step", index: i })}>
      <span className={s.navNumber}>{number(i)}</span><span>{step.title}</span>
      <span className={s.navMark} aria-hidden="true">{i === run.stepIndex ? <ArrowUpRight size={14} /> : run.available(i) ? <Check size={12} /> : "·"}</span>
    </button>)}
  </nav>;
}

function Heading({ run }: { run: LiveRun }) {
  return <div className={s.heading}>
    <p className={s.eyebrow}><span>{number(run.stepIndex)} / 05</span><span>{run.role}</span></p>
    <h2 aria-label={run.step.title}>{run.step.title.split(" ").map((word, i) => <span className={s.wordMask} key={`${run.step.id}-${i}`} aria-hidden="true">
      <motion.span initial={run.state.reducedMotion ? false : { y: "110%", rotate: 4 }} animate={{ y: 0, rotate: 0 }}
        transition={{ duration: .65, delay: i * .055, ease: [.22, 1, .36, 1] }}>{word}&nbsp;</motion.span>
    </span>)}</h2>
  </div>;
}

const entrances: Record<Concept, TargetAndTransition> = {
  breach: { opacity: 0, clipPath: "inset(0% 0% 100% 0%)", y: 18 },
  wiretap: { opacity: 0, filter: "blur(6px)", x: 20 },
  counterplay: { opacity: 0, scaleX: .92, y: 16 },
  casefile: { opacity: 0, x: 55, rotateY: -9 },
  orbit: { opacity: 0, x: 36, filter: "blur(8px)" },
};

function Frame({ run, theme, children, className = "" }: { run: LiveRun; theme: Concept; children: ReactNode; className?: string }) {
  return <AnimatePresence mode="wait" initial={false}>
    <motion.div key={run.frameKey} className={`${s.frame} ${className}`}
      initial={run.state.reducedMotion ? false : entrances[theme]}
      animate={{ opacity: 1, x: 0, y: 0, rotateY: 0, scaleX: 1, clipPath: "inset(0% 0% 0% 0%)", filter: "blur(0px)" }}
      exit={run.state.reducedMotion ? { opacity: 0 } : { opacity: 0, y: -12 }}
      transition={{ duration: run.state.reducedMotion ? 0 : .55, ease: [.22, 1, .36, 1] }}>
      {children}
    </motion.div>
  </AnimatePresence>;
}

function Readout({ run }: { run: LiveRun }) {
  return <Evidence step={run.step} visible={run.visible} reduced={run.state.reducedMotion} />;
}

function AttackTrace({ run }: { run: LiveRun }) {
  return <div className={s.attackTrace} aria-hidden="true">
    <svg viewBox="0 0 1000 170" preserveAspectRatio="none" fill="none">
      <path d="M0 85 H1000" stroke="currentColor" strokeOpacity=".18" />
      {Array.from({ length: 5 }, (_, i) => <g key={i}>
        <path d={`M${130 + i * 175} 15 V155`} stroke="currentColor" strokeOpacity=".16" strokeDasharray="2 6" />
        <circle cx={130 + i * 175} cy="85" r="4" fill={i <= run.stepIndex ? "var(--accent)" : "currentColor"} opacity={i <= run.stepIndex ? 1 : .2} />
      </g>)}
      <motion.path d="M0 85 H130 C190 85 230 22 305 85 S405 148 480 85 S580 22 655 85 S755 148 830 85 H1000"
        stroke="var(--accent)" strokeWidth="1.5" initial={{ pathLength: 0 }} animate={{ pathLength: (run.stepIndex + 1) / 5 }}
        transition={{ duration: run.state.reducedMotion ? 0 : 1.2, ease: "easeInOut" }} />
      <path className={s.tracePacket} d="M0 85 H130 C190 85 230 22 305 85 S405 148 480 85 S580 22 655 85 S755 148 830 85 H1000"
        pathLength="100" stroke="var(--accent)" strokeWidth="3" strokeDasharray="2 98" />
    </svg>
    <div className={s.traceCaption}><span>ADVERSARY → OBSERVATION SURFACE</span><span>MODEL RESPONSE → EVIDENCE</span></div>
  </div>;
}

export function Breach({ run }: { run: LiveRun }) {
  return <section className={s.breachScene} aria-label="Breach presentation">
    <div className={s.breachMasthead}><span>ADVERSARIAL EVALUATION</span><span>{run.currentCase.channel}</span><Crosshair size={18} /></div>
    <Frame run={run} theme="breach" className={s.breachFrame}>
      <div className={s.breachTitle}>
        <span className={s.bigIndex}>{number(run.stepIndex)}</span>
        <Heading run={run} />
        <span className={s.caseCaption}>{run.currentCase.title}</span>
        <ArrowDownRight className={s.breachArrow} size={54} strokeWidth={1} aria-hidden="true" />
      </div>
      <div className={s.breachEvidence}><Readout run={run} /></div>
    </Frame>
    <AttackTrace run={run} />
    <StageNav run={run} className={s.horizontalNav} />
    <div className={s.scanEdge} aria-hidden="true" />
  </section>;
}

function Scope({ run }: { run: LiveRun }) {
  return <div className={s.scope} aria-hidden="true">
    <div className={s.scopeGrid} />
    <svg viewBox="0 0 1000 130" preserveAspectRatio="none" fill="none">
      <path d="M0 65 H200 L210 62 L220 69 L230 60 L240 66 H330 L345 30 L357 105 L370 8 L385 119 L398 40 L410 65 H560 L572 57 L588 80 L602 45 L615 65 H720 L730 58 L746 71 L760 64 H1000"
        stroke="currentColor" strokeWidth="1.4" vectorEffect="non-scaling-stroke" />
      <path className={s.scopeEcho} d="M0 65 H200 L210 62 L220 69 L230 60 L240 66 H330 L345 30 L357 105 L370 8 L385 119 L398 40 L410 65 H560 L572 57 L588 80 L602 45 L615 65 H720 L730 58 L746 71 L760 64 H1000"
        stroke="currentColor" strokeWidth="3" pathLength="100" strokeDasharray="9 91" vectorEffect="non-scaling-stroke" />
    </svg>
    <span className={s.scopeReadout}>CHANNEL / {run.currentCase.channel.toUpperCase()}</span>
    <span className={s.scopeBeam} />
  </div>;
}

export function Wiretap({ run }: { run: LiveRun }) {
  return <section className={s.wiretapScene} aria-label="Wiretap presentation">
    <div className={s.terminalMasthead}><span><i /> SIGNAL ACQUIRED</span><span>{run.currentCase.repository}</span><span>RX / TX</span></div>
    <Scope run={run} />
    <div className={s.wiretapBody}>
      <aside className={s.wiretapRail}><p className={s.eyebrow}>TRACE INDEX</p><StageNav run={run} /><div className={s.telemetry}><span className={s.telemetryBars} aria-hidden="true">{Array.from({ length: 24 }, (_, i) => <i key={i} style={{ "--bar": i } as CSSProperties} />)}</span><span>OBSERVING THE AGENT</span></div></aside>
      <Frame run={run} theme="wiretap" className={s.wiretapFrame}>
        <div className={s.terminalPrompt}><span>adversary@{run.currentCase.repository}</span><span>~ / {run.step.id}</span></div>
        <Heading run={run} /><Readout run={run} />
      </Frame>
    </div>
    <div className={s.terminalFooter}><span>{run.currentCase.title}</span><span>● {run.complete ? "RECORD AVAILABLE" : "STREAM OPEN"}</span></div>
  </section>;
}

export function Counterplay({ run }: { run: LiveRun }) {
  const offset = [0, -5, 6, 0, 3][run.stepIndex];
  return <section className={s.counterScene} aria-label="Counterplay presentation">
    <div className={s.duelBackdrop} aria-hidden="true"><span>A</span><span>D</span></div>
    <motion.div className={s.faultLine} animate={{ x: `${offset}vw` }} transition={{ type: "spring", stiffness: 55, damping: 15 }} aria-hidden="true"><i /></motion.div>
    <div className={s.duelMasthead}><div><span>01 / ADVERSARY</span><strong>{RUN.models.find((model) => model.id === "adversary")?.name}</strong></div><span className={s.duelVersus}>×</span><div><span>02 / SCORING AGENT</span><strong>{RUN.models.find((model) => model.id === "scoring")?.name}</strong></div></div>
    <Frame run={run} theme="counterplay" className={s.counterFrame}>
      <div className={s.counterTitle}><Heading run={run} /><span className={s.caseCaption}>{run.currentCase.title}</span></div>
      <Readout run={run} />
    </Frame>
    <div className={s.duelBottom}><span className={s.duelArrow} aria-hidden="true">→</span><StageNav run={run} className={s.horizontalNav} /><span className={s.duelArrow} aria-hidden="true">←</span></div>
  </section>;
}

export function Casefile({ run }: { run: LiveRun }) {
  return <section className={s.casefileScene} aria-label="Casefile presentation">
    <div className={s.paperUnderlay} aria-hidden="true" />
    <div className={s.paper}>
      <header className={s.dossierHeader}><span>ADVERSARY / FIELD RECORD</span><span>{run.currentCase.repository}</span><span>FILE {number(run.state.viewedCase)}</span></header>
      <div className={s.dossierBody}>
        <aside className={s.dossierMargin}><span className={s.folioNumber}>{number(run.stepIndex)}</span><p>CONTENTS</p><StageNav run={run} /><span className={s.marginNote}>{run.currentCase.channel}</span></aside>
        <Frame run={run} theme="casefile" className={s.dossierFrame}>
          <div className={s.dossierTitle}><span>{run.currentCase.title}</span><Heading run={run} /></div>
          <Readout run={run} />
          <motion.div key={`${run.frameKey}-stamp`} className={s.stamp} aria-hidden="true"
            initial={run.state.reducedMotion ? false : { scale: 1.6, rotate: -18, opacity: 0 }}
            animate={{ scale: 1, rotate: -8, opacity: 1 }} transition={{ delay: .5, type: "spring", stiffness: 230, damping: 15 }}>
            {run.stepIndex === 4 ? "FINDING" : "IN REVIEW"}
          </motion.div>
        </Frame>
      </div>
      <footer className={s.dossierFooter}><span>REPOSITORY → INTERVENTION → EVIDENCE</span><span>ADVERSARIAL EVALUATION / {number(run.stepIndex)}</span></footer>
    </div>
  </section>;
}

function OrbitalSystem({ run }: { run: LiveRun }) {
  const rotateX = useSpring(0, { stiffness: 90, damping: 20 });
  const rotateY = useSpring(0, { stiffness: 90, damping: 20 });
  return <div className={s.orbitSpace} onPointerMove={(event) => {
    if (run.state.reducedMotion) return;
    const rect = event.currentTarget.getBoundingClientRect();
    rotateY.set(((event.clientX - rect.left) / rect.width - .5) * 16);
    rotateX.set(-((event.clientY - rect.top) / rect.height - .5) * 16);
  }} onPointerLeave={() => { rotateX.set(0); rotateY.set(0); }}>
    <motion.div className={s.orbitRig} style={{ rotateX, rotateY }}>
      <div className={s.orbitRingOne} aria-hidden="true" /><div className={s.orbitRingTwo} aria-hidden="true" /><div className={s.orbitRingThree} aria-hidden="true" />
      <svg className={s.orbitTicks} viewBox="0 0 600 600" aria-hidden="true">
        {Array.from({ length: 80 }, (_, i) => <line key={i} x1="300" y1="84" x2="300" y2={i % 4 === 0 ? 96 : 89} transform={`rotate(${i * 4.5} 300 300)`} stroke="currentColor" opacity={i % 4 === 0 ? .45 : .17} />)}
      </svg>
      <div className={s.orbitCore}><Crosshair size={18} /><AnimatePresence mode="wait"><motion.span key={run.stepIndex} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }} transition={{ duration: .3 }}>{number(run.stepIndex)}</motion.span></AnimatePresence><small>ACTIVE FIELD</small></div>
      <nav className={s.orbitNodes} aria-label="Run stages">
        {run.currentCase.steps.map((step, i) => {
          const angle = (-90 + i * 72) * Math.PI / 180;
          return <button type="button" key={step.id} disabled={!run.available(i)}
            aria-current={i === run.stepIndex ? "step" : undefined} onClick={() => run.dispatch({ type: "select-step", index: i })}
            style={{ left: `${50 + 37 * Math.cos(angle)}%`, top: `${50 + 37 * Math.sin(angle)}%` }}>
            <span className={s.orbitNodeDot} /><small>{number(i)}</small><span>{step.title}</span>
          </button>;
        })}
      </nav>
    </motion.div>
    <div className={s.orbitCoordinate} aria-hidden="true"><span>OBSERVATION SPACE</span><span>MOVE TO EXPLORE ↗</span></div>
  </div>;
}

export function Orbit({ run }: { run: LiveRun }) {
  return <section className={s.orbitScene} aria-label="Orbit presentation">
    <div className={s.orbitMasthead}><span>ADVERSARIAL FIELD STUDY</span><span>{run.currentCase.channel}</span></div>
    <div className={s.orbitBody}><OrbitalSystem run={run} />
      <Frame run={run} theme="orbit" className={s.orbitFrame}><span className={s.caseCaption}>{run.currentCase.title}</span><Heading run={run} /><Readout run={run} /></Frame>
    </div>
    <div className={s.orbitFooter}><span>{run.currentCase.repository}</span><span>ONE INTERVENTION. A DIFFERENT TRAJECTORY.</span></div>
  </section>;
}
