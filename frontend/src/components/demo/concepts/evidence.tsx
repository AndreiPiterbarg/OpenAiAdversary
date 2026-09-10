"use client";

import { memo } from "react";
import { motion } from "motion/react";
import type { StoryBlock, StoryStep } from "@/lib/demo/run-data";
import { streamLength } from "@/lib/demo/replay";
import s from "./concepts.module.css";

function Code({ text, visible }: { text: string; visible: number }) {
  const count = Math.max(0, Math.min(text.length, visible));
  return <pre className={s.code}><code>
    <span className="sr-only select-none">{text}</span>
    <span aria-hidden="true"><span data-typed-output>{text.slice(0, count)}</span>
      {visible >= 0 && count < text.length && <span className={s.caret} />}
      <span className={s.untyped}>{text.slice(count)}</span>
    </span>
  </code></pre>;
}

function Block({ block, visible }: { block: StoryBlock; visible: number }) {
  if (block.kind === "text") return <p className={s.bodyCopy}>{block.text}</p>;
  if (block.kind === "code") return <div className={s.source}>
    <div className={s.sourceLabel}><span>{block.label}</span><span aria-hidden="true">↗</span></div>
    <Code text={block.text} visible={block.stream === false ? Infinity : visible} />
  </div>;
  if (block.kind === "finding") return <div className={s.finding}>
    <p>{block.text}</p><span>{block.detail}</span>
  </div>;
  if (block.kind === "checks") return <div className={s.checks}>
    {block.rows.map((row, i) => <div className={s.check} key={row.label}>
      <span>{row.label}<small>{row.detail}</small></span>
      <span className={s.verdict} data-tone={visible >= (i + 1) * 70 ? row.status : "pending"}>
        {visible < (i + 1) * 70 ? "Pending" : row.status === "passed" ? "Pass" : row.status === "rejected" ? "Rejected" : "Not measured"}
      </span>
    </div>)}
  </div>;
  return <div className={s.comparison}>
    {block.arms.map((arm, i) => {
      const start = block.arms.slice(0, i).reduce((sum, item) => sum + item.code.length, 0);
      const resolved = visible >= start + arm.code.length;
      return <div className={s.comparisonArm} key={arm.label} data-arm={i}>
        <div className={s.sourceLabel}><span>{arm.label}</span>
          <span className={s.outcome} data-tone={arm.outcome} data-resolved={resolved}>{arm.outcome === "passed" ? "PASS" : "FAIL"}</span>
        </div>
        <Code text={arm.code} visible={visible - start} />
        <p className={s.armSummary} data-resolved={resolved}>{arm.text}</p>
      </div>;
    })}
  </div>;
}

export const Evidence = memo(function Evidence({ step, visible, reduced }: { step: StoryStep; visible: number; reduced: boolean }) {
  return <div className={s.evidence}>
    {step.blocks.map((block, i) => {
      const start = step.blocks.slice(0, i).reduce((sum, item) => sum + streamLength(item), 0);
      return <motion.div key={i} className={s.evidenceBlock}
        initial={reduced || block.kind === "text" || block.kind === "finding" ? false : { opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }} transition={{ duration: .45, delay: i * .04, ease: [.22, 1, .36, 1] }}>
        <Block block={block} visible={visible - start} />
      </motion.div>;
    })}
  </div>;
});
