import assert from "node:assert/strict";
import test from "node:test";
import { INITIAL_PLAYBACK, positionAt, reducePlayback, stepTiming, streamLength, visibleCharacters } from "./replay.ts";
import { RUN } from "./run-data.ts";

const schedule = RUN.cases.map((item) => item.steps.map((step) => stepTiming(step).durationMs));
const apply = (state, action) => reducePlayback(state, action, schedule);
const firstCaseMs = schedule[0].reduce((sum, duration) => sum + duration, 0);
const secondCaseMs = schedule[1].reduce((sum, duration) => sum + duration, 0);
const firstAttackOffset = schedule[0][0] + 300;
const secondAttackOffset = schedule[1][0] + 300;
const totalMs = schedule.flat().reduce((sum, duration) => sum + duration, 0);

test("automatic following closes each step and opens the next, then advances cases", () => {
  let state = apply(INITIAL_PLAYBACK, { type: "tick", deltaMs: schedule[0][0] - 1 });
  assert.equal(state.openStep, 0);
  state = apply(state, { type: "tick", deltaMs: 1 });
  assert.equal(state.openStep, 1);
  assert.equal(positionAt(state.elapsedMs, schedule).localMs, 0);
  state = apply(state, { type: "tick", deltaMs: firstCaseMs - state.elapsedMs });
  assert.equal(state.viewedCase, 1);
  assert.equal(state.openStep, 0);
});

test("a selected section stays open while later cases become available", () => {
  const active = apply(INITIAL_PLAYBACK, { type: "tick", deltaMs: firstAttackOffset });
  const reviewing = apply(active, { type: "open", index: 0 });
  assert.equal(reviewing.followingLive, false);
  const advanced = apply(reviewing, { type: "tick", deltaMs: firstCaseMs });
  assert.equal(advanced.viewedCase, 0);
  assert.equal(advanced.openStep, 0);
  assert.equal(positionAt(advanced.elapsedMs, schedule).caseIndex, 1);
  assert.equal(apply(advanced, { type: "open", index: 4 }).openStep, 4);
  const next = apply(advanced, { type: "view-case", index: 1 });
  assert.equal(next.viewedCase, 1);
  assert.equal(next.openStep, 1);
  assert.equal(next.elapsedMs, advanced.elapsedMs);
  assert.equal(next.followingLive, false);
});

test("case navigation blocks future pages and Follow live returns to the latest output", () => {
  assert.deepEqual(apply(INITIAL_PLAYBACK, { type: "view-case", index: 1 }), INITIAL_PLAYBACK);
  assert.deepEqual(apply(INITIAL_PLAYBACK, { type: "open", index: 4 }), INITIAL_PLAYBACK);
  let state = apply(INITIAL_PLAYBACK, { type: "tick", deltaMs: firstCaseMs + secondAttackOffset });
  state = apply(state, { type: "view-case", index: 0 });
  assert.deepEqual(apply(state, { type: "view-case", index: 2 }), state);
  assert.deepEqual(apply(state, { type: "view-case", index: -1 }), state);
  const followed = apply(state, { type: "follow-live" });
  assert.equal(followed.viewedCase, 1);
  assert.equal(followed.openStep, 1);
  assert.equal(followed.followingLive, true);
  assert.equal(followed.elapsedMs, state.elapsedMs);
});

test("selecting the current stage in a concept preserves it as the run advances", () => {
  const active = apply(INITIAL_PLAYBACK, { type: "tick", deltaMs: firstAttackOffset });
  const selected = apply(active, { type: "select-step", index: 1 });
  assert.equal(selected.openStep, 1);
  assert.equal(selected.followingLive, false);
  const advanced = apply(selected, { type: "tick", deltaMs: firstCaseMs });
  assert.equal(advanced.viewedCase, 0);
  assert.equal(advanced.openStep, 1);
  assert.equal(positionAt(advanced.elapsedMs, schedule).caseIndex, 1);
  assert.deepEqual(apply(INITIAL_PLAYBACK, { type: "select-step", index: 4 }), INITIAL_PLAYBACK);
});

test("finishing the queue preserves review and does not replay cases under new numbers", () => {
  let state = apply(INITIAL_PLAYBACK, { type: "tick", deltaMs: firstCaseMs + 1000 });
  state = apply(state, { type: "view-case", index: 0 });
  state = apply(state, { type: "tick", deltaMs: totalMs * 2 });
  assert.equal(state.elapsedMs, totalMs);
  assert.equal(state.viewedCase, 0);
  assert.equal(positionAt(state.elapsedMs, schedule).finished, true);
  assert.deepEqual(apply(state, { type: "tick", deltaMs: 1000 }), state);
  assert.equal(apply(state, { type: "view-case", index: RUN.cases.length - 1 }).viewedCase, RUN.cases.length - 1);
});

test("closing an agent session keeps it closed while later cases arrive", () => {
  let state = apply(INITIAL_PLAYBACK, { type: "toggle-case", index: 0 });
  assert.equal(state.caseExpanded, false);
  state = apply(state, { type: "tick", deltaMs: firstCaseMs + secondAttackOffset });
  assert.equal(positionAt(state.elapsedMs, schedule).caseIndex, 1);
  assert.equal(state.viewedCase, 0);
  assert.equal(state.caseExpanded, false);
  const reopened = apply(state, { type: "toggle-case", index: 0 });
  assert.equal(reopened.caseExpanded, true);
  assert.equal(reopened.openStep, 0);
  assert.equal(reopened.elapsedMs, state.elapsedMs);
});

test("reviewing an agent session holds its evidence as the live case moves ahead", () => {
  let state = apply(INITIAL_PLAYBACK, { type: "tick", deltaMs: firstCaseMs + 1000 });
  state = apply(state, { type: "toggle-case", index: 0 });
  assert.equal(state.caseExpanded, true);
  assert.equal(state.openStep, schedule[0].length - 1);
  state = apply(state, { type: "open", index: 1 });
  state = apply(state, { type: "tick", deltaMs: secondCaseMs });
  assert.equal(state.viewedCase, 0);
  assert.equal(state.openStep, 1);
  assert.equal(state.caseExpanded, true);
  assert.equal(positionAt(state.elapsedMs, schedule).caseIndex, 2);
  const followed = apply(state, { type: "follow-live" });
  assert.equal(followed.viewedCase, 2);
  assert.equal(followed.caseExpanded, true);
  assert.equal(followed.openStep, 0);
  assert.equal(followed.followingLive, true);
});

test("agent sessions become available only when their case starts", () => {
  for (const index of [-1, 0.5, 1, NaN]) {
    assert.deepEqual(apply(INITIAL_PLAYBACK, { type: "toggle-case", index }), INITIAL_PLAYBACK);
  }
  const advanced = apply(INITIAL_PLAYBACK, { type: "tick", deltaMs: firstCaseMs });
  assert.equal(advanced.viewedCase, 1);
  assert.equal(advanced.caseExpanded, true);
});

test("reduced motion removes typing without stopping case progression", () => {
  const state = apply(INITIAL_PLAYBACK, { type: "motion", reduced: true });
  assert.equal(state.reducedMotion, true);
  assert.equal(apply(state, { type: "tick", deltaMs: firstCaseMs }).viewedCase, 1);
});

test("explanations, source context, and the final finding never consume typing time", () => {
  for (const item of RUN.cases) {
    for (const step of item.steps) {
      for (const block of step.blocks) {
        if (block.kind === "text" || block.kind === "finding") assert.equal(streamLength(block), 0);
        if (block.kind === "code") assert.equal(streamLength(block), block.stream === false ? 0 : block.text.length);
        if (block.kind === "comparison") assert.equal(streamLength(block), block.arms.reduce((sum, arm) => sum + arm.code.length, 0));
      }
    }
    assert.equal(item.steps.at(-1).blocks.reduce((sum, block) => sum + streamLength(block), 0), 0);
  }
});

test("typing progresses within words at ten percent below the original speed", () => {
  const startMs = 250 * 1.25;
  assert.equal(visibleCharacters(startMs, 270), 0);
  assert.equal(visibleCharacters(startMs + 100, 270), 8);
  const sample = { blocks: [{ kind: "code", label: "Program", text: "x".repeat(270) }] };
  assert.equal(stepTiming(sample).outputEndMs - startMs, Math.ceil(3000 / 0.9));
  for (const item of RUN.cases) {
    const step = item.steps.find((step) => step.id === "generate");
    const chars = step.blocks.reduce((sum, block) => sum + streamLength(block), 0);
    assert.equal(visibleCharacters(stepTiming(step).outputEndMs, chars), chars);
    assert.equal(visibleCharacters(stepTiming(step).durationMs, chars), chars);
  }
});

test("thinking pauses last 25 percent longer and the square covers the final pause", () => {
  for (const item of RUN.cases) {
    for (const step of item.steps) {
      const timing = stepTiming(step);
      if (!timing.characters) continue;
      assert.ok(visibleCharacters(timing.outputEndMs - 1, timing.characters) < timing.characters);
      assert.equal(visibleCharacters(timing.outputEndMs, timing.characters), timing.characters);
      assert.equal(timing.thinkingUntilMs, timing.durationMs);
      assert.equal(timing.durationMs - timing.outputEndMs, 650 * 1.25);
    }
  }
  const program = RUN.cases[0].steps[1];
  const shorter = { ...program, blocks: [{ kind: "code", label: "Program", text: "x = 1" }] };
  assert.ok(stepTiming(shorter).durationMs < stepTiming(program).durationMs);
});

test("static content gets a reading beat without a long thinking animation", () => {
  for (const item of RUN.cases) {
    for (const step of [item.steps[0], item.steps.at(-1)]) {
      const timing = stepTiming(step);
      assert.equal(timing.characters, 0);
      assert.equal(timing.outputEndMs, 0);
      assert.equal(timing.thinkingUntilMs, 350 * 1.25);
      assert.equal(timing.durationMs, step.id === "takeaway" ? 4500 : 1875);
    }
  }
});

test("each distinct case supplies its own channel, evidence, and five stages", () => {
  assert.equal(RUN.identity.source, "proxy");
  assert.equal(new Set(RUN.cases.map((item) => item.id)).size, RUN.cases.length);
  assert.equal(new Set(RUN.cases.map((item) => item.channel)).size, RUN.cases.length);
  for (const item of RUN.cases) {
    assert.deepEqual(item.steps.map((step) => step.id), ["mine", "generate", "compare", "confirm", "takeaway"]);
    for (const step of item.steps) assert.ok(RUN.roles.some((role) => role.id === step.role));
    const confirmation = item.steps.find((step) => step.id === "confirm");
    const checks = confirmation.blocks.find((block) => block.kind === "checks");
    assert.ok(checks.rows.every((row) => row.status === "unavailable"));
  }
});

test("invalid schedules and actions cannot corrupt navigation or timing", () => {
  assert.throws(() => positionAt(0, []));
  assert.throws(() => positionAt(0, [[]]));
  assert.throws(() => positionAt(0, [[0]]));
  assert.throws(() => positionAt(0, [[NaN]]));
  assert.deepEqual(apply(INITIAL_PLAYBACK, { type: "tick", deltaMs: NaN }), INITIAL_PLAYBACK);
  assert.deepEqual(apply(INITIAL_PLAYBACK, { type: "view-case", index: 0.5 }), INITIAL_PLAYBACK);
});
