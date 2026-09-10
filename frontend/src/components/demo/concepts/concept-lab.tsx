"use client";

import { useState } from "react";
import Link from "next/link";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { ArrowUpRight, ChevronLeft, ChevronRight, Radio, RotateCcw } from "lucide-react";
import { RUN } from "@/lib/demo/run-data";
import { useLiveRun } from "./use-live-run";
import { Breach, Wiretap, Counterplay, Casefile, Orbit } from "./scenes";
import s from "./concepts.module.css";

export type Concept = "breach" | "wiretap" | "counterplay" | "casefile" | "orbit";
const concepts: { id: Concept; name: string; description: string }[] = [
  { id: "breach", name: "Breach", description: "Cinematic / kinetic type" },
  { id: "wiretap", name: "Wiretap", description: "Phosphor / signal tracing" },
  { id: "counterplay", name: "Counterplay", description: "Split field / opposing forces" },
  { id: "casefile", name: "Casefile", description: "Editorial / physical paper" },
  { id: "orbit", name: "Orbit", description: "Spatial / reactive geometry" },
];
const scenes = { breach: Breach, wiretap: Wiretap, counterplay: Counterplay, casefile: Casefile, orbit: Orbit };

function Monitor({ concept, setConcept, restart }: { concept: Concept; setConcept: (next: Concept) => void; restart: () => void }) {
  const run = useLiveRun();
  const Scene = scenes[concept];
  return <MotionConfig reducedMotion="user"><main className={s.lab} data-concept={concept} data-reduced={run.state.reducedMotion}>
    <h1 className="sr-only">Live monitor — {concepts.find((item) => item.id === concept)?.name}</h1>
    <header className={s.labHeader}>
      <Link href="/demo" className={s.brand}><span aria-hidden="true">a/</span>adversary<span className={s.headerDivider}>/</span><small>Live monitor</small></Link>
      <nav className={s.caseControls} aria-label="Attack cases">
        <button type="button" aria-label="Previous case" disabled={run.state.viewedCase === 0} onClick={() => run.dispatch({ type: "view-case", index: run.state.viewedCase - 1 })}><ChevronLeft size={14} /></button>
        <span>Case {String(run.state.viewedCase + 1).padStart(2, "0")} <span>/ {String(RUN.cases.length).padStart(2, "0")}</span></span>
        <button type="button" aria-label="Next available case" disabled={run.state.viewedCase >= run.position.caseIndex} onClick={() => run.dispatch({ type: "view-case", index: run.state.viewedCase + 1 })}><ChevronRight size={14} /></button>
      </nav>
      <div className={s.liveControls}>
        {!run.state.followingLive && <button type="button" onClick={() => run.dispatch({ type: "follow-live" })}><Radio size={13} />{run.position.finished ? "Latest case" : "Follow live"}</button>}
        <span><i data-finished={run.position.finished} />{run.position.finished ? "Complete" : `Live · ${String(run.position.caseIndex + 1).padStart(2, "0")}/${String(RUN.cases.length).padStart(2, "0")}`}</span>
      </div>
    </header>
    <div className={s.sceneViewport}>
      <AnimatePresence mode="wait">
        <motion.div key={concept} className={s.sceneWrapper} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: run.state.reducedMotion ? 0 : .22 }}><Scene run={run} /></motion.div>
      </AnimatePresence>
    </div>
    <footer className={s.conceptDock}>
      <div className={s.dockLabel}><span>DESIGN STUDIES</span><small>Choose a direction</small></div>
      <nav aria-label="Presentation concepts" className={s.conceptTabs}>
        {concepts.map((item, index) => <button type="button" key={item.id} aria-pressed={concept === item.id} onClick={() => setConcept(item.id)} title={item.description}>
          <span className={s.conceptNumber}>0{index + 1}</span><span>{item.name}<small>{item.description}</small></span>
          {concept === item.id && <motion.span className={s.selectedConcept} layoutId="concept-selection" transition={{ type: "spring", stiffness: 380, damping: 34 }} />}
        </button>)}
      </nav>
      <div className={s.dockActions}><button type="button" onClick={restart} title="Restart the sample to watch its motion"><RotateCcw size={13} />Replay sample</button><Link href="/demo">Original <ArrowUpRight size={13} /></Link></div>
    </footer>
    <p className="sr-only" role="status" aria-live="polite">{run.position.finished ? "Run complete." : `Case ${run.position.caseIndex + 1}: ${RUN.cases[run.position.caseIndex].steps[run.position.index].title}.`}</p>
  </main></MotionConfig>;
}

export function ConceptLab({ initialConcept }: { initialConcept: Concept }) {
  const [concept, setConcept] = useState(initialConcept);
  const [session, setSession] = useState(0);
  const select = (next: Concept) => {
    setConcept(next);
    window.history.replaceState(null, "", `/demo-lab?view=${next}`);
  };
  return <Monitor key={session} concept={concept} setConcept={select} restart={() => setSession((value) => value + 1)} />;
}
