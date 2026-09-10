"use client";

import { ArrowLeft, ArrowRight, Check, ChevronDown, CircleAlert } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { ResultMode } from "@/lib/demo/results";
import styles from "./results-explorer.module.css";

type Props = {
  groups: { failed: ResultMode[]; passed: ResultMode[] };
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
  onSelect: (mode: ResultMode) => void;
  registerButton: (key: string, element: HTMLButtonElement | null) => void;
};

export function ResultsOverview({ groups, expanded, onExpandedChange, onSelect, registerButton }: Props) {
  const reducedMotion = useReducedMotion();
  const totalModes = groups.failed.length + groups.passed.length;
  const hiddenModes = Math.max(0, groups.failed.length - 3) + Math.max(0, groups.passed.length - 3);
  const maxCount = Math.max(1, ...[...groups.failed, ...groups.passed].map((mode) => mode.examples.length));
  return <section className={styles.overview} aria-label="Distribution of outcomes under attack">
    <div className={styles.distributions} id="result-mode-lists">
      {(["failed", "passed"] as const).map((outcome) => {
        const modes = groups[outcome];
        const total = modes.reduce((count, mode) => count + mode.examples.length, 0);
        const failed = outcome === "failed";
        const Icon = failed ? CircleAlert : Check;
        return <section key={outcome} className={styles.distribution} data-outcome={outcome}
          aria-labelledby={`${outcome}-modes-heading`}>
          <header className={styles.distributionHeading}>
            <h3 id={`${outcome}-modes-heading`}><Icon size={14} aria-hidden="true" />{failed ? "Failures" : "Successes"}</h3>
            <span>{total} {total === 1 ? "example" : "examples"}</span>
          </header>
          {modes.length ? <>
            <ol className={styles.modeList}>
              <AnimatePresence initial={false}>
              {(expanded ? modes : modes.slice(0, 3)).map((mode) => <motion.li key={mode.key}
                initial={{ opacity: 0, height: reducedMotion ? "auto" : 0 }} animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: reducedMotion ? "auto" : 0 }} transition={{ duration: reducedMotion ? 0 : 0.24, ease: [0.22, 1, 0.36, 1] }}>
                <button type="button" className={styles.modeButton}
                  ref={(element) => registerButton(mode.key, element)} onClick={() => onSelect(mode)}
                  aria-label={`${failed ? "Failure" : "Success"}: ${mode.label}, ${mode.examples.length} ${mode.examples.length === 1 ? "example" : "examples"}`}>
                  <span className={styles.modeRow}>
                    <span className={styles.modeValue}>{mode.examples.length}</span>
                    <motion.span layout="position" layoutId={reducedMotion ? undefined : `mode-label-${mode.key}`} className={styles.modeLabel}
                      transition={{ duration: reducedMotion ? 0 : 0.3, ease: [0.22, 1, 0.36, 1] }}>{mode.label}</motion.span>
                    {failed ? <ArrowLeft className={styles.modeArrow} size={13} aria-hidden="true" /> : <ArrowRight className={styles.modeArrow} size={13} aria-hidden="true" />}
                  </span>
                  <span className={styles.modeTrack} aria-hidden="true">
                    <span className={styles.modeFill} style={{ width: `${mode.examples.length / maxCount * 100}%` }} />
                  </span>
                </button>
              </motion.li>)}
              </AnimatePresence>
            </ol>
            <div className={styles.distributionScale} aria-hidden="true"><span>{failed ? maxCount : 0}</span><span>Examples per mode</span><span>{failed ? 0 : maxCount}</span></div>
          </> : <div className={styles.emptyDistribution}>
            <Icon size={18} aria-hidden="true" />
            <p>No {failed ? "failed" : "successful"} attacked-run examples supplied.</p>
          </div>}
        </section>;
      })}
    </div>
    <div className={styles.overviewFooter}>
      <span>{hiddenModes && !expanded ? `${totalModes - hiddenModes} of ${totalModes} modes` : `All ${totalModes} modes shown`}</span>
      <button type="button" className={styles.expandModes} aria-expanded={expanded} aria-controls="result-mode-lists"
        disabled={!hiddenModes} onClick={() => onExpandedChange(!expanded)}>
        {expanded ? "Show less" : "Show more"}<ChevronDown size={13} data-open={expanded} aria-hidden="true" />
      </button>
    </div>
  </section>;
}
