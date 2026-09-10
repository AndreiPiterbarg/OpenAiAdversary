"use client";

import { memo, useEffect, useReducer, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight, Check, ChevronRight, Play, Radio } from "lucide-react";

import { RUN, type StoryBlock, type StoryStep } from "@/lib/demo/run-data";
import { INITIAL_PLAYBACK, positionAt, reducePlayback, stepTiming, streamLength, visibleCharacters } from "@/lib/demo/replay";
import styles from "./story-replay.module.css";

const schedule = RUN.cases.map((item) => item.steps.map((step) => stepTiming(step).durationMs));

function ActivitySymbol({ kind }: { kind: string }) {
  // Small filled action symbols, like the file and terminal glyphs in Linear's activity log.
  return <svg className={styles.actionSymbol} width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    {kind === "mine" ? <><circle cx="6.5" cy="6.5" r="4.5" stroke="currentColor" strokeWidth="2.5" /><path d="m10 10 4 4" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" /></>
      : kind === "generate" ? <><rect x="1" y="2" width="14" height="12" rx="2.5" fill="currentColor" /><path d="m4.5 5.5 3 2.5-3 2.5" stroke="var(--activity-surface)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></>
      : kind === "compare" ? <><rect x="1" y="2" width="6" height="12" rx="1.5" fill="currentColor" /><rect x="9" y="2" width="6" height="12" rx="1.5" fill="currentColor" /><path d="M3 5h2m6 0h2M3 8h2m6 0h2" stroke="var(--activity-surface)" strokeWidth="1.25" strokeLinecap="round" /></>
      : kind === "confirm" ? <><path d="m8 1 6 2.5v4.3c0 3.3-3.2 5.8-6 7.2-2.8-1.4-6-3.9-6-7.2V3.5L8 1Z" fill="currentColor" /><path d="m5 7.8 2 2 4-4" stroke="var(--activity-surface)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></>
      : <><path d="M3 1.5h10v9H4v4H2.5V2A.5.5 0 0 1 3 1.5Z" fill="currentColor" /><path d="M5.5 4.5h5m-5 3h3" stroke="var(--activity-surface)" strokeWidth="1.2" strokeLinecap="round" /></>}
  </svg>;
}

function Disclosure({ open }: { open: boolean }) {
  return <svg className={styles.disclosure} data-open={open} width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><path d="m2 3 3 4 3-4H2Z" fill="currentColor" /></svg>;
}

function ThinkingIndicator() {
  return <svg className={styles.thinkingIndicator} width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
    {Array.from({ length: 36 }, (_, index) => <circle key={index} cx={2 + index % 6 * 3.2} cy={2 + Math.floor(index / 6) * 3.2} r=".95" fill="currentColor"
      style={{ animationDelay: `${-(index % 6 + Math.floor(index / 6)) * .12}s` }} />)}
  </svg>;
}

const ACTIONS: Record<string, { active: string; complete: string; status: string }> = {
  mine: { active: "Inspecting the repair task", complete: "Inspected the repair task", status: "Inspecting source and tests…" },
  generate: { active: "Writing attack", complete: "Wrote attack", status: "Writing attack…" },
  compare: { active: "Testing coding agent", complete: "Tested coding agent", status: "Testing with and without the attack…" },
  confirm: { active: "Verifying the evidence", complete: "Verified the evidence", status: "Checking exposure and clean controls…" },
  takeaway: { active: "Recording finding", complete: "Recorded finding", status: "Summarizing finding…" },
};

function TypedCode({ text, visible }: { text: string; visible: number }) {
  const count = Math.max(0, Math.min(text.length, visible));
  const typing = visible >= 0 && count < text.length;
  return (
    <span className={styles.typedCode}>
      <span className="sr-only select-none">{text}</span>
      <span aria-hidden="true">
        <span data-typed-output>{text.slice(0, count)}</span>
        {typing && <span className={styles.typingCaret} />}
        <span className={styles.untyped}>{text.slice(count)}</span>
      </span>
    </span>
  );
}

function Block({ block, visible }: { block: StoryBlock; visible: number }) {
  if (block.kind === "text") return <p className={styles.paragraph}>{block.text}</p>;
  if (block.kind === "code") return (
    <div className={styles.codeWell}>
      <div className={styles.caption}>{block.label}</div>
      <pre><code>{block.stream === false ? block.text : <TypedCode text={block.text} visible={visible} />}</code></pre>
    </div>
  );
  if (block.kind === "finding") return (
    <div className={styles.finding}>
      <p>{block.text}</p>
      <div className={styles.caption}>{block.detail}</div>
    </div>
  );
  if (block.kind === "checks") return (
    <div className={styles.checks}>
      {block.rows.map((row, index) => {
        const resolved = visible >= (index + 1) * 70;
        return (
          <div className={styles.checkRow} key={row.label}>
            <div>
              <p>{row.label}</p>
              <p className={styles.checkDetail}>{row.detail}</p>
            </div>
            <span className={styles.verdict} data-tone={resolved ? row.status : "pending"}>
              {resolved ? row.status === "passed" ? "Pass" : row.status === "rejected" ? "Rejected" : "No result yet" : "Pending"}
            </span>
          </div>
        );
      })}
    </div>
  );
  return (
    <div className={styles.comparison}>
      {block.arms.map((arm, index) => {
        const armStart = block.arms.slice(0, index).reduce((sum, item) => sum + item.code.length, 0);
        const armEnd = armStart + arm.code.length;
        return (
          <div className={styles.arm} key={arm.label}>
            <div className={styles.armHeader}>
              <span>{arm.label}</span>
              <span className={`${styles.verdict} ${styles.result}`} data-tone={arm.outcome} data-visible={visible >= armEnd}>
                {arm.outcome === "passed" ? "Pass" : "Fail"}
              </span>
            </div>
            <pre><code><TypedCode text={arm.code} visible={visible - armStart} /></code></pre>
            <p className={styles.result} data-visible={visible >= armEnd}>{arm.text}</p>
          </div>
        );
      })}
    </div>
  );
}

const StepContent = memo(function StepContent({ step, visible }: { step: StoryStep; visible: number }) {
  let offset = 0;
  return step.blocks.map((block, index) => {
    if (index === 0 && block.kind === "text") return null;
    const start = offset;
    offset += streamLength(block);
    return <Block key={index} block={block} visible={visible - start} />;
  });
});

export function StoryReplay() {
  const [launched, setLaunched] = useState(false);
  const [state, dispatch] = useReducer(
    (current: typeof INITIAL_PLAYBACK, action: Parameters<typeof reducePlayback>[1]) => reducePlayback(current, action, schedule),
    INITIAL_PLAYBACK,
  );
  const position = positionAt(state.elapsedMs, schedule);
  const activeStep = RUN.cases[position.caseIndex].steps[position.index];
  const working = !position.finished && position.localMs < stepTiming(activeStep).thinkingUntilMs;
  const liveStep = useRef<HTMLElement>(null);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    dispatch({ type: "motion", reduced: media.matches });
    const update = () => dispatch({ type: "motion", reduced: media.matches });
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!launched || position.finished) return;
    let frame: number;
    let last = performance.now();
    const tick = (now: number) => {
      if (now - last >= 16) {
        dispatch({ type: "tick", deltaMs: now - last });
        last = now;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [launched, position.finished]);

  useEffect(() => {
    if (!launched || !state.followingLive) return;
    // Follow newly arrived activity, never character-by-character updates.
    const revealEntry = () => {
      const entry = liveStep.current;
      if (!entry) return;
      const bounds = entry.getBoundingClientRect();
      if (bounds.top < 70 || bounds.bottom > window.innerHeight - 90) {
        entry.scrollIntoView({ block: "center", behavior: state.reducedMotion ? "instant" : "smooth" });
      }
    };
    // Let the previous session finish collapsing before measuring the new entry.
    const timeout = window.setTimeout(revealEntry, state.reducedMotion ? 0 : 380);
    return () => window.clearTimeout(timeout);
  }, [launched, position.caseIndex, position.index, state.followingLive, state.reducedMotion]);

  return (
    <>
    <div className={`${styles.replay} motion-page-enter`}>
      <div className={styles.breadcrumb}>
        <Link href="/dashboard/projects">Projects</Link>
        <ChevronRight size={16} aria-hidden="true" />
        <h1>Live monitor</h1>
      </div>
      <section className={styles.intro} aria-labelledby="intro-heading">
        <h2 id="intro-heading">How this run works</h2>
        <p>The adversary tests ideas and uses what works—and what doesn’t—to refine its attacks. Its goal is a clear description of where a model fails, the conditions that trigger it, and the evidence behind it.</p>
        <p>Here, Astra repairs real repository bugs. The adversary adds misleading guidance to a tool response, trying to steer Astra toward a fix that looks right but leaves the underlying problem unresolved.</p>
        <p>We compare the repair with and without the attack, then check both patches against fresh regression and behavior tests. A failure is recorded when the clean run passes and the attacked run fails. Expand any activity to inspect the guidance, code, and checks.</p>
        {!launched && <button type="button" className={styles.launchButton} onClick={() => setLaunched(true)}>
          <Play size={13} fill="currentColor" aria-hidden="true" />Launch
        </button>}
      </section>
      {launched && <>
      <div className={styles.toolbar}>
        <div className={styles.feedHeading}>
          <h2>Agent activity</h2>
          <span className={styles.caseCounter} aria-label={`${position.caseIndex + 1} of ${RUN.cases.length} cases started`}>
            {String(position.caseIndex + 1).padStart(2, "0")}<span>/ {String(RUN.cases.length).padStart(2, "0")}</span>
          </span>
        </div>
        <div className={styles.controls}>
          {!state.followingLive && <button type="button" onClick={() => dispatch({ type: "follow-live" })} className={styles.followButton}>
            <Radio size={14} aria-hidden="true" />{position.finished ? "Latest case" : "Follow live"}
          </button>}
          <span className={styles.liveStatus}>
            {position.finished ? <Check size={14} aria-hidden="true" /> : <span className={styles.activeDot} aria-hidden="true" />}
            {position.finished ? "Complete" : "Live"}
          </span>
        </div>
      </div>
      <ol className={styles.feed} aria-label="Agent activity">
        {RUN.cases.slice(0, position.caseIndex + 1).map((item, caseIndex) => {
          const current = caseIndex === position.caseIndex;
          const finished = !current || position.finished;
          const expanded = state.viewedCase === caseIndex && state.caseExpanded;
          const availableSteps = finished ? item.steps : item.steps.slice(0, position.index + 1);
          return (
            <li key={item.id} className={styles.entry}
              data-case-index={caseIndex} data-active={!finished} data-expanded={expanded}>
              <h3>
                <button type="button" id={`case-${item.id}`} className={styles.sessionHeader}
                  aria-expanded={expanded} aria-controls={`session-${item.id}`}
                  onClick={() => dispatch({ type: "toggle-case", index: caseIndex })}>
                  <ActivitySymbol kind="generate" />
                  <span className={styles.agentName}>Adversary</span>
                  <span className={styles.caseTitle}>{item.title}</span>
                  <Disclosure open={expanded} />
                  <span className={styles.entryNumber}>Case {String(caseIndex + 1).padStart(2, "0")}</span>
                  {!expanded && <span className={styles.sessionStatus}>
                    {finished ? <Check size={12} aria-hidden="true" /> : <span className={styles.workingIcon} data-working={working}><ThinkingIndicator /></span>}
                    {finished ? "Complete" : activeStep.title}
                  </span>}
                </button>
              </h3>
              <div className={styles.collapse} data-open={expanded} aria-hidden={!expanded} inert={!expanded}>
                <div className={styles.clip}>
                  <div id={`session-${item.id}`} role="region" aria-labelledby={`case-${item.id}`} className={styles.steps}>
                    <p className={styles.caseMeta}>{item.repository}<span>·</span>{item.record.attackLabel}<span>·</span>{item.record.condition} · run {item.record.repetition}</p>
                    {availableSteps.map((step, index) => {
                      const active = current && !position.finished && index === position.index;
                      const complete = finished || (current && index < position.index);
                      const open = expanded && index === state.openStep;
                      const role = RUN.roles.find((candidate) => candidate.id === step.role);
                      const model = RUN.models.find((candidate) => candidate.id === role?.modelId);
                      const totalCharacters = step.blocks.reduce((sum, block) => sum + streamLength(block), 0);
                      const visible = state.reducedMotion || complete ? Infinity
                        : active ? visibleCharacters(position.localMs, totalCharacters) : 0;
                      const lead = step.blocks[0];
                      const action = ACTIONS[step.id];
                      const id = `${item.id}-${step.id}`;
                      return (
                        <section key={step.id} ref={current && index === position.index ? liveStep : undefined}
                          className={styles.step} data-active={active} data-open={open} data-complete={complete} data-testid={`step-${id}`}>
                          {lead.kind === "text" && <p className={styles.narration}>{lead.text}</p>}
                          <h4>
                            <button type="button" id={`heading-${id}`} className={styles.stepHeader}
                              aria-expanded={open} aria-controls={`content-${id}`}
                              onClick={() => dispatch({ type: "open", index })}>
                              <ActivitySymbol kind={step.id} />
                              <span className={styles.stepTitle}>{complete ? action.complete : action.active}</span>
                              <span className={styles.stepMeta}>{step.role === "adversary" ? item.record.adversary : model?.name ?? (step.id === "mine" ? item.repository : "")}</span>
                              <Disclosure open={open} />
                              {active && <span className={styles.activeDot} aria-hidden="true" />}
                              <span className="sr-only">{active ? ", running" : ", complete"}</span>
                            </button>
                          </h4>
                          <div className={styles.collapse} data-open={open} aria-hidden={!open} inert={!open}>
                            <div className={styles.clip}>
                              <div id={`content-${id}`} role="region" aria-labelledby={`heading-${id}`} className={styles.content}>
                                <StepContent step={step} visible={visible} />
                              </div>
                            </div>
                          </div>
                        </section>
                      );
                    })}
                    {!finished && <div className={styles.thinkingRow} data-working={working} aria-hidden="true">
                      <ThinkingIndicator /><span>{ACTIONS[activeStep.id].status}</span>
                    </div>}
                  </div>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
      </>}
      <p className="sr-only" role="status" aria-live="polite">{!launched ? "Ready to launch." : position.finished ? "Run complete." : `Case ${position.caseIndex + 1}: ${activeStep.title}.`}</p>
    </div>
    <Link href="/demo/results" className={styles.resultsButton}>Results<ArrowRight size={15} aria-hidden="true" /></Link>
    </>
  );
}
