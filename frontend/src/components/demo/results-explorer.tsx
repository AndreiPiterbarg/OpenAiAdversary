"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Check, ChevronDown, ChevronRight, CircleAlert, Code2, Cpu, FileText, GitBranch, List, Minus } from "lucide-react";
import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from "motion/react";

import { RUN, type StoryBlock } from "@/lib/demo/run-data";
import { groupResultModes, type ResultMode } from "@/lib/demo/results";
import { ResultsOverview } from "./results-overview";
import monitorStyles from "./story-replay.module.css";
import styles from "./results-explorer.module.css";

type Finding = (typeof RUN.cases)[number];
const resultGroups = groupResultModes(RUN.cases);
const transitionEase = [0.22, 1, 0.36, 1] as const;

function modelFor(roleId: string) {
  const role = RUN.roles.find((role) => role.id === roleId);
  return RUN.models.find((model) => model.id === role?.modelId)?.name ?? "Not available";
}

function CodeText({ text }: { text: string }) {
  // Presentation only: preserve every character, with restrained Python token colors.
  return text.split(/("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b(?:def|if|return|in)\b)/g).map((part, index) =>
    <span key={index} className={/^["']/.test(part) ? styles.string : /^(def|if|return|in)$/.test(part) ? styles.keyword : undefined}>{part}</span>);
}

function Output({ text, highlight = true }: { text?: string; highlight?: boolean }) {
  if (!text) return <p className={styles.unavailable}>Output unavailable.</p>;
  return <pre className={styles.code}><code>{text.split("\n").map((line, index) => (
    <span className={styles.codeLine} key={index}
      data-tone={/^PASS\b/.test(line) ? "passed" : /^(FAIL\b|\w*Error:)/.test(line) ? "failed" : undefined}>
      <span className={styles.lineNumber} aria-hidden="true">{index + 1}</span>
      <span>{line ? highlight ? <CodeText text={line} /> : line : "\u00a0"}</span>
    </span>
  ))}</code></pre>;
}

function Verdict({ outcome }: { outcome: "passed" | "failed" }) {
  return <span className={styles.verdict} data-tone={outcome}>
    {outcome === "passed" ? <Check size={11} aria-hidden="true" /> : <CircleAlert size={11} aria-hidden="true" />}
    {outcome === "passed" ? "Pass" : "Fail"}
  </span>;
}

function Evidence({ title, meta, icon, children, open, onToggle, id }: {
  title: string; meta: string; icon: ReactNode; children: ReactNode;
  open: boolean; onToggle: () => void; id: string;
}) {
  return <div className={styles.evidenceItem} id={id}>
    <h4><button type="button" className={styles.evidenceButton} aria-expanded={open} aria-controls={`${id}-content`}
      id={`${id}-heading`} onClick={onToggle}>
      {icon}<span>{title}</span><span className={styles.evidenceMeta}>{meta}</span>
      <ChevronDown size={13} className={styles.disclosure} data-open={open} aria-hidden="true" />
    </button></h4>
    <div className={styles.collapse} data-open={open} aria-hidden={!open} inert={!open}>
      <div className={styles.clip}><div id={`${id}-content`} role="region" aria-labelledby={`${id}-heading`} className={styles.evidenceContent}>{children}</div></div>
    </div>
  </div>;
}

function FindingEvidence({ finding }: { finding: Finding }) {
  const arms = [{ label: "Without attack", ...finding.control }, { label: "With attack", ...finding.perturbed }];
  const [selected, setSelected] = useState(() => Math.max(0, arms.findIndex((arm) => arm.label === "With attack")));
  const [outputOpen, setOutputOpen] = useState(true);
  const [repositoryOpen, setRepositoryOpen] = useState(false);
  const [attackOpen, setAttackOpen] = useState(false);
  const [guidanceOpen, setGuidanceOpen] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const [trace, setTrace] = useState<{ attack: { tools: RecordedTool[] }; clean: { tools: RecordedTool[] } } | null>(null);
  const [traceError, setTraceError] = useState(false);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const id = useId();

  return <div className={styles.eventPanel}>
    <div className={styles.eventBar}>
      <span className={styles.eventId} title={finding.sourceId}>{finding.record.arm} · {finding.record.condition} · run {finding.record.repetition}</span>
      <nav aria-label="Jump to evidence"><span>Jump to:</span>
        <a href="#agent-output" onClick={() => setOutputOpen(true)}>Output</a>
        <a href="#repository-evidence" onClick={() => setRepositoryOpen(true)}>Repository</a>
        <a href="#attack-evidence" onClick={() => setAttackOpen(true)}>Attack</a>
      </nav>
    </div>
    <div className={styles.eventTags}>
      <span><Cpu size={12} aria-hidden="true" />{modelFor("scoring")}</span>
      <span><GitBranch size={12} aria-hidden="true" />{finding.repository}</span>
      <span>{finding.channel}</span>
    </div>
    <section className={styles.conditions} aria-label="Task and attack context">
      <div><h3>Task</h3><p>{finding.context}</p></div>
      <div><h3>Attack condition</h3><p>{finding.hypothesis}<span className={styles.boundary}>{finding.boundary}</span></p></div>
    </section>
    <section className={styles.traceSection} id="agent-output" aria-labelledby={`${id}-heading`}>
      <h3 id={`${id}-heading`}>Agent output</h3>
      <p className={styles.sectionNote}>{finding.comparison}</p>
      {arms.length ? <>
        <div className={styles.outputToolbar}>
          <div className={styles.armTabs} role="tablist" aria-label="Paired test output">
            {arms.map((arm, index) => <button type="button" role="tab" key={arm.label}
              ref={(element) => { tabs.current[index] = element; }} id={`${id}-tab-${index}`}
              aria-selected={selected === index} aria-controls={`${id}-output`} tabIndex={selected === index ? 0 : -1}
              onClick={() => { setSelected(index); setOutputOpen(true); }} onKeyDown={(event) => {
                if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                event.preventDefault();
                const next = event.key === "Home" ? 0 : event.key === "End" ? arms.length - 1
                  : (index + (event.key === "ArrowRight" ? 1 : -1) + arms.length) % arms.length;
                setSelected(next);
                setOutputOpen(true);
                tabs.current[next]?.focus({ preventScroll: true });
              }}>
              {arm.label}<Verdict outcome={arm.outcome} />
            </button>)}
          </div>
          <span className={styles.outputLabel}>Paired test</span>
        </div>
        <div className={styles.frames}>
          <div id={`${id}-output`} role="tabpanel" aria-labelledby={`${id}-tab-${selected}`} tabIndex={0}>
            <Evidence title="Patch and test results" meta={arms[selected]?.text ?? "Unavailable"} icon={<Code2 size={13} aria-hidden="true" />}
              id="observed-response" open={outputOpen} onToggle={() => setOutputOpen(!outputOpen)}>
              <div key={selected} className={styles.outputEnter}><Output text={arms[selected]?.output} /></div>
            </Evidence>
          </div>
          <Evidence title="Repository context" meta={finding.repository} icon={<FileText size={13} aria-hidden="true" />}
            id="repository-evidence" open={repositoryOpen} onToggle={() => setRepositoryOpen(!repositoryOpen)}>
            <Output text={finding.seed} highlight={false} />
          </Evidence>
          <Evidence title="Injected guidance" meta="Exact text shown to Astra" icon={<FileText size={13} aria-hidden="true" />}
            id="injected-guidance" open={guidanceOpen} onToggle={() => setGuidanceOpen(!guidanceOpen)}>
            <Output text={finding.injectedText} highlight={false} />
          </Evidence>
          <Evidence title="Attack code" meta={finding.record.adversary} icon={<Code2 size={13} aria-hidden="true" />}
            id="attack-evidence" open={attackOpen} onToggle={() => setAttackOpen(!attackOpen)}>
            <Output text={finding.program} />
          </Evidence>
          <Evidence title="Agent trace" meta={`${selected === 0 ? finding.record.cleanToolCalls : finding.record.attackToolCalls} tool calls · commands and responses`} icon={<List size={13} aria-hidden="true" />}
            id="agent-trace" open={traceOpen} onToggle={async () => {
              setTraceOpen(!traceOpen);
              if (trace || traceOpen) return;
              setTraceError(false);
              try {
                const response = await fetch(finding.record.evidenceUrl);
                if (!response.ok) throw new Error("Evidence unavailable");
                setTrace(await response.json());
              } catch { setTraceError(true); }
            }}>
            {trace ? (selected === 0 ? trace.clean : trace.attack).tools.map((step, index) => <details className={styles.traceStep} key={`${step.step}-${index}`}>
              <summary><span>{String(step.step).padStart(2, "0")}</span>{step.call.name === "submit" ? "Submitted repair" : "Shell command"}</summary>
              <Output text={step.call.arguments.command ?? step.call.arguments.summary ?? JSON.stringify(step.call.arguments, null, 2)} />
              {step.result && <Output text={step.result} highlight={false} />}
            </details>) : <p className={styles.unavailable}>{traceError ? "Could not load the trace. Close and reopen to retry." : "Loading recorded trace…"}</p>}
          </Evidence>
        </div>
      </> : <p className={styles.unavailable}>Paired results unavailable.</p>}
    </section>
    <section className={styles.outcomeSection} aria-labelledby={`${id}-outcomes`}>
      <h3 id={`${id}-outcomes`}>Paired outcome</h3>
      <dl className={styles.outcomes}>{arms.map((arm) => <div key={arm.label}>
        <dt>{arm.label}</dt><dd><Verdict outcome={arm.outcome} /><span>{arm.text}</span></dd>
      </div>)}</dl>
      <a className={styles.downloadEvidence} href={finding.record.evidenceUrl} download>Download full run evidence<ArrowRight size={12} aria-hidden="true" /></a>
    </section>
  </div>;
}

type RecordedTool = { step: number; call: { name: string; arguments: { command?: string; summary?: string } }; result?: string };

function EvaluationContext({ finding, examples, onSelect }: { finding: Finding; examples: Finding[]; onSelect: (index: number) => void }) {
  const confirmation = finding.steps.flatMap<StoryBlock>((step) => step.blocks).find((block) => block.kind === "checks");
  return <aside className={styles.context} aria-label="Evaluation context">
    <section><h3>Evaluation</h3>
      <dl className={styles.metadata}>
        <div><dt>Coding model</dt><dd>{modelFor("scoring")}</dd></div>
        <div><dt>Adversary</dt><dd>{finding.record.adversary}</dd></div>
        <div><dt>Attack channel</dt><dd>{finding.channel}</dd></div>
        <div><dt>Execution</dt><dd>{finding.record.condition} · repetition {finding.record.repetition}</dd></div>
        <div><dt>Checks</dt><dd>{finding.record.passedChecks} passed · {finding.record.failedChecks} failed</dd></div>
      </dl>
    </section>
    <section><h3>Evidence checks</h3>
      <dl className={styles.metadata}><div><dt>Evaluation</dt><dd>{finding.record.evidenceLevel}</dd></div></dl>
      <dl className={styles.checks}>{confirmation?.rows.map((row) => <div key={row.label}>
        <dt>{row.label}</dt><dd data-tone={row.status}>
          {row.status === "unavailable" ? <Minus size={10} aria-hidden="true" /> : row.status === "passed" ? <Check size={10} aria-hidden="true" /> : <CircleAlert size={10} aria-hidden="true" />}
          {row.status === "unavailable" ? "No result yet" : row.status === "passed" ? "Pass" : "Rejected"}
        </dd>
      </div>)}</dl>
      {!confirmation && <p className={styles.sectionNote}>No result yet.</p>}
    </section>
    <section className={styles.mechanism}><h3>{finding.perturbed.outcome === "failed" ? "Failure mechanism" : "Observed mechanism"}</h3><p>{finding.mechanism}</p></section>
    {examples.length > 1 && <section className={styles.related}><h3>Other examples</h3>
      <ul>{examples.map((item, index) => item.id !== finding.id && <li key={item.id}>
        <button type="button" onClick={() => onSelect(index)}>{item.perturbed.outcome === "failed" ? <CircleAlert size={12} aria-hidden="true" /> : <Check size={12} aria-hidden="true" />}<span>{item.title}<span className={styles.findingChannel}>{item.record.attackLabel} · {item.record.condition} · run {item.record.repetition}</span></span><ChevronRight size={12} aria-hidden="true" /></button>
      </li>)}</ul>
    </section>}
  </aside>;
}

function FindingDetail({ mode }: { mode: ResultMode }) {
  const [selected, setSelected] = useState(0);
  const [direction, setDirection] = useState(1);
  const [indexOpen, setIndexOpen] = useState(false);
  const reducedMotion = useReducedMotion();
  const selector = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const finding = mode.examples[selected];
  const failed = mode.outcome === "failed";
  const OutcomeIcon = failed ? CircleAlert : Check;

  function selectFinding(index: number) {
    setDirection(index >= selected ? 1 : -1);
    setSelected(index);
    setIndexOpen(false);
    title.current?.focus({ preventScroll: true });
  }

  useEffect(() => {
    if (!indexOpen) return;
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !selector.current?.contains(event.target)) setIndexOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setIndexOpen(false);
      trigger.current?.focus({ preventScroll: true });
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [indexOpen]);

  return <article className={styles.issue} aria-labelledby="finding-title" data-outcome={mode.outcome}>
      <header className={styles.issueHeader}>
        <div className={styles.titleRow}><OutcomeIcon size={18} aria-hidden="true" /><h2 id="finding-title" ref={title} tabIndex={-1}>{finding.title}</h2></div>
        <p className={styles.finding}>{finding.finding}</p>
      </header>
      <div className={styles.issueToolbar}>
        <div className={styles.selector} ref={selector} onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) setIndexOpen(false);
        }}>
          <button type="button" className={styles.indexTrigger} ref={trigger} aria-expanded={indexOpen} aria-controls="finding-index" onClick={() => setIndexOpen(!indexOpen)}>
            <List size={13} aria-hidden="true" /><span>Examples</span><span className={styles.count}>{mode.examples.length}</span><ChevronDown size={12} aria-hidden="true" />
          </button>
          <div id="finding-index" className={styles.findingIndex} data-open={indexOpen} inert={!indexOpen} aria-hidden={!indexOpen}>
            <p>{mode.label}</p>
            <ul aria-label="Examples in this mode">{mode.examples.map((item, index) => <li key={item.id}>
              <button type="button" aria-current={selected === index ? "true" : undefined} onClick={() => selectFinding(index)}>
                <span className={styles.findingNumber}>{String(index + 1).padStart(2, "0")}</span>
                <span><span className={styles.findingTitle}>{item.title}</span><span className={styles.findingChannel}>{item.record.attackLabel} · {item.record.condition} · run {item.record.repetition}</span></span>
                {selected === index && <Check size={13} aria-hidden="true" />}
              </button>
            </li>)}</ul>
          </div>
        </div>
        <div className={styles.testedModel}><Cpu size={13} aria-hidden="true" /><span>{modelFor("scoring")}</span></div>
        <span className={styles.channelTag}>{finding.channel}</span>
      </div>
      <motion.div className={styles.detailGrid} key={finding.id} initial={{ opacity: 0, x: reducedMotion ? 0 : direction * 12 }}
        animate={{ opacity: 1, x: 0 }} transition={{ duration: reducedMotion ? 0 : 0.24, ease: transitionEase }}>
        <div className={styles.mainColumn}>
          <div className={styles.detailHeading}><h3>{failed ? "Failure details" : "Success details"}</h3>
            <div className={styles.findingNavigation}>
              <span>{String(selected + 1).padStart(2, "0")} <span>of {String(mode.examples.length).padStart(2, "0")}</span></span>
              <button type="button" aria-label="Previous example" disabled={selected === 0} onClick={() => selectFinding(selected - 1)}><ArrowLeft size={13} aria-hidden="true" /></button>
              <button type="button" aria-label="Next example" disabled={selected === mode.examples.length - 1} onClick={() => selectFinding(selected + 1)}><ArrowRight size={13} aria-hidden="true" /></button>
            </div>
          </div>
          <FindingEvidence key={finding.id} finding={finding} />
        </div>
        <EvaluationContext finding={finding} examples={mode.examples} onSelect={selectFinding} />
      </motion.div>
    </article>;
}

export function ResultsExplorer() {
  const [mode, setMode] = useState<ResultMode | null>(null);
  const [expanded, setExpanded] = useState(false);
  const reducedMotion = useReducedMotion();
  const buttonRefs = useRef(new Map<string, HTMLButtonElement>());
  const lastSelection = useRef<string | null>(null);
  const overviewScroll = useRef(0);
  const restoringOverview = useRef(false);
  const selectedHeading = useRef<HTMLHeadingElement>(null);
  const transition = { duration: reducedMotion ? 0 : 0.3, ease: transitionEase };

  function selectMode(next: ResultMode) {
    overviewScroll.current = window.scrollY;
    lastSelection.current = next.key;
    setMode(next);
  }

  return <div className={`${styles.results} motion-page-enter`}>
    <div className={monitorStyles.breadcrumb}>
      <Link href="/demo">Live monitor</Link><ChevronRight size={16} aria-hidden="true" /><h1>Results</h1>
    </div>
    <header className={styles.overviewHeader}>
      <div><h2>Behavior under attack</h2><p><Cpu size={13} aria-hidden="true" />{modelFor("scoring")}</p></div>
      <div className={styles.headerActions}>
        <span>{RUN.summary.caseCount} paired runs · {RUN.summary.distinctTasks} tasks</span>
        <Link href="/demo/results/report" className={styles.reportButton}><FileText size={13} aria-hidden="true" />Final report<ArrowRight size={13} aria-hidden="true" /></Link>
      </div>
    </header>
    <LayoutGroup>
      <AnimatePresence mode="popLayout" initial={false}>
        {!mode ? <motion.div key="overview" initial={{ opacity: 0, y: reducedMotion ? 0 : -8 }} animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: reducedMotion ? 0 : -6 }} transition={{ ...transition, duration: reducedMotion ? 0 : 0.18 }}
          onAnimationComplete={(definition) => {
            if (!restoringOverview.current || typeof definition !== "object" || !("opacity" in definition) || definition.opacity !== 1) return;
            restoringOverview.current = false;
            window.scrollTo({ top: overviewScroll.current, behavior: "auto" });
            if (lastSelection.current) buttonRefs.current.get(lastSelection.current)?.focus({ preventScroll: true });
          }}>
          <ResultsOverview groups={resultGroups} expanded={expanded} onExpandedChange={setExpanded} onSelect={selectMode} registerButton={(key, element) => {
            if (element) buttonRefs.current.set(key, element);
            else buttonRefs.current.delete(key);
          }} />
          <a className={styles.downloadEvidence} href="/data/astra/episode-inventory.json" download>Full collection inventory · {RUN.summary.registeredEpisodes} registered runs<ArrowRight size={12} aria-hidden="true" /></a>
        </motion.div> : <motion.div key={mode.key} initial={{ opacity: 0, x: reducedMotion ? 0 : mode.outcome === "failed" ? -14 : 14 }}
          animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: reducedMotion ? 0 : mode.outcome === "failed" ? -8 : 8 }} transition={transition}
          onAnimationComplete={(definition) => {
            if (typeof definition === "object" && "opacity" in definition && definition.opacity === 1) selectedHeading.current?.focus({ preventScroll: true });
          }}>
          <div className={styles.modeNavigation} data-outcome={mode.outcome}>
            <button type="button" className={styles.backToModes} onClick={() => { restoringOverview.current = true; setMode(null); }}>
              <ArrowLeft size={13} aria-hidden="true" />All modes
            </button>
            <ChevronRight size={12} className={styles.modeSeparator} aria-hidden="true" />
            <span className={styles.selectedOutcome}>{mode.outcome === "failed" ? <CircleAlert size={13} aria-hidden="true" /> : <Check size={13} aria-hidden="true" />}{mode.outcome === "failed" ? "Failure" : "Success"}</span>
            <h3 ref={selectedHeading} tabIndex={-1}><motion.span layout="position" layoutId={reducedMotion ? undefined : `mode-label-${mode.key}`} transition={transition}>{mode.label}</motion.span></h3>
          </div>
          <FindingDetail mode={mode} />
        </motion.div>}
      </AnimatePresence>
    </LayoutGroup>
    <p className={styles.selectionAnnouncement} role="status">{mode ? `${mode.label}: ${mode.examples.length} ${mode.examples.length === 1 ? "example" : "examples"}` : "Choose a failure or success mode."}</p>
  </div>;
}
