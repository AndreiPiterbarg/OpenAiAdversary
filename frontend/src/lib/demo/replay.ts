import type { StoryBlock, StoryStep } from "./run-data";

export type Playback = {
  elapsedMs: number;
  viewedCase: number;
  caseExpanded: boolean;
  openStep: number | null;
  followingLive: boolean;
  reducedMotion: boolean;
};

export type PlaybackAction =
  | { type: "tick"; deltaMs: number }
  | { type: "motion"; reduced: boolean }
  | { type: "open"; index: number }
  | { type: "select-step"; index: number }
  | { type: "view-case"; index: number }
  | { type: "toggle-case"; index: number }
  | { type: "follow-live" };

export const INITIAL_PLAYBACK: Playback = {
  elapsedMs: 0, viewedCase: 0, caseExpanded: true, openStep: 0,
  followingLive: true, reducedMotion: false,
};

export function positionAt(elapsedMs: number, schedule: readonly (readonly number[])[]) {
  const durations = schedule.flat();
  if (!schedule.length || schedule.some((steps) => !steps.length) ||
      durations.some((duration) => !Number.isFinite(duration) || duration <= 0)) {
    throw new Error("Monitor cases need steps with positive, finite durations.");
  }
  const totalMs = durations.reduce((total, duration) => total + duration, 0);
  const finished = elapsedMs >= totalMs;
  let remaining = Math.max(0, Math.min(elapsedMs, totalMs));
  for (let caseIndex = 0; caseIndex < schedule.length; caseIndex++) {
    for (let index = 0; index < schedule[caseIndex].length; index++) {
      const durationMs = schedule[caseIndex][index];
      if (remaining < durationMs || (caseIndex === schedule.length - 1 && index === schedule[caseIndex].length - 1)) {
        return { caseIndex, index, localMs: remaining, durationMs, totalMs, finished };
      }
      remaining -= durationMs;
    }
  }
  throw new Error("Monitor position unavailable.");
}

export function reducePlayback(state: Playback, action: PlaybackAction, schedule: readonly (readonly number[])[]): Playback {
  const position = positionAt(state.elapsedMs, schedule);
  switch (action.type) {
    case "motion":
      return { ...state, reducedMotion: action.reduced };
    case "tick": {
      if (position.finished || action.deltaMs <= 0 || !Number.isFinite(action.deltaMs)) return state;
      const elapsedMs = Math.min(state.elapsedMs + action.deltaMs, position.totalMs);
      const next = positionAt(elapsedMs, schedule);
      return { ...state, elapsedMs,
        viewedCase: state.followingLive ? next.caseIndex : state.viewedCase,
        caseExpanded: state.followingLive || state.caseExpanded,
        openStep: state.followingLive ? next.index : state.openStep };
    }
    case "open": case "select-step": {
      const lastAvailableStep = state.viewedCase < position.caseIndex || position.finished
        ? schedule[state.viewedCase].length - 1 : position.index;
      if (!Number.isInteger(action.index) || action.index < 0 || action.index > lastAvailableStep) return state;
      return { ...state, openStep: action.type === "open" && state.openStep === action.index ? null : action.index, followingLive: false };
    }
    case "view-case":
      if (!Number.isInteger(action.index) || action.index < 0 || action.index > position.caseIndex) return state;
      return { ...state, viewedCase: action.index, caseExpanded: true,
        openStep: action.index === position.caseIndex ? position.index : 0, followingLive: false };
    case "toggle-case": {
      if (!Number.isInteger(action.index) || action.index < 0 || action.index > position.caseIndex) return state;
      const sameCase = action.index === state.viewedCase;
      const latestStep = action.index === position.caseIndex ? position.index : schedule[action.index].length - 1;
      return { ...state, viewedCase: action.index,
        caseExpanded: sameCase ? !state.caseExpanded : true,
        openStep: sameCase ? state.openStep : latestStep, followingLive: false };
    }
    case "follow-live":
      return { ...state, viewedCase: position.caseIndex, caseExpanded: true, openStep: position.index, followingLive: true };
  }
}

// Static explanations, source context, and the final finding never type.
// Check results arrive as complete updates, spaced within the same stream.
export function streamLength(block: StoryBlock): number {
  switch (block.kind) {
    case "text": case "finding": return 0;
    case "code": return block.stream === false ? 0 : block.text.length;
    case "checks": return block.rows.length * 70;
    case "comparison": return block.arms.reduce((sum, arm) => sum + arm.code.length, 0);
  }
}

const THINKING_PAUSE_SCALE = 1.25;
const OUTPUT_START_MS = 250 * THINKING_PAUSE_SCALE;
const OUTPUT_HOLD_MS = 650 * THINKING_PAUSE_SCALE;

function typingDuration(totalCharacters: number) {
  return Math.ceil(Math.min(3500, Math.max(600, totalCharacters / 90 * 1000)) / 0.9);
}

// Type at 90% of the original speed; give thinking pauses 25% more time.
// Keep the square visible through the pause after streamed output finishes.
export function stepTiming(step: StoryStep) {
  const characters = step.blocks.reduce((sum, block) => sum + streamLength(block), 0);
  const outputEndMs = characters > 0 ? OUTPUT_START_MS + typingDuration(characters) : 0;
  const staticReadingMs = step.blocks.some((block) => block.kind === "finding") ? 4500 : 1500 * THINKING_PAUSE_SCALE;
  return {
    characters,
    outputEndMs,
    thinkingUntilMs: characters > 0 ? outputEndMs + OUTPUT_HOLD_MS : 350 * THINKING_PAUSE_SCALE,
    durationMs: characters > 0 ? outputEndMs + OUTPUT_HOLD_MS : staticReadingMs,
  };
}

export function visibleCharacters(localMs: number, totalCharacters: number) {
  const progress = Math.max(0, Math.min(1, (localMs - OUTPUT_START_MS) / typingDuration(totalCharacters)));
  return Math.floor(progress * totalCharacters);
}
