"use client";

import { useEffect, useReducer } from "react";
import { RUN } from "@/lib/demo/run-data";
import { INITIAL_PLAYBACK, positionAt, reducePlayback, stepTiming, streamLength, visibleCharacters } from "@/lib/demo/replay";

const schedule = RUN.cases.map((item) => item.steps.map((step) => stepTiming(step).durationMs));

export function useLiveRun() {
  const [state, dispatch] = useReducer(
    (current: typeof INITIAL_PLAYBACK, action: Parameters<typeof reducePlayback>[1]) => reducePlayback(current, action, schedule),
    INITIAL_PLAYBACK,
  );
  const position = positionAt(state.elapsedMs, schedule);
  const currentCase = RUN.cases[state.viewedCase];
  const stepIndex = state.openStep ?? (state.viewedCase === position.caseIndex ? position.index : 0);
  const step = currentCase.steps[stepIndex];
  const available = (index: number) => state.viewedCase < position.caseIndex || position.finished || index <= position.index;
  const complete = state.viewedCase < position.caseIndex || position.finished || stepIndex < position.index;
  const count = step.blocks.reduce((sum, block) => sum + streamLength(block), 0);
  const visible = complete || state.reducedMotion ? Infinity : visibleCharacters(position.localMs, count);
  const role = RUN.roles.find((item) => item.id === step.role);
  const model = RUN.models.find((item) => item.id === role?.modelId);

  useEffect(() => {
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => dispatch({ type: "motion", reduced: media.matches });
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (position.finished) return;
    let frame: number;
    let last = performance.now();
    const tick = (now: number) => {
      if (now - last >= 24) {
        dispatch({ type: "tick", deltaMs: now - last });
        last = now;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [position.finished]);

  return { state, dispatch, position, currentCase, stepIndex, step, available, complete, visible,
    role: model?.name ?? role?.label ?? "", frameKey: `${currentCase.id}-${step.id}` };
}

export type LiveRun = ReturnType<typeof useLiveRun>;
