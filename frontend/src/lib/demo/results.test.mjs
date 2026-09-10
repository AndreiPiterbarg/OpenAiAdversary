import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync, readdirSync } from "node:fs";
import { RUN } from "./run-data.ts";
import { groupResultModes } from "./results.ts";

const dataRoot = new URL("../../../public/data/astra/", import.meta.url);
const evidenceById = new Map(RUN.cases.map(item => [
  item.id,
  JSON.parse(readFileSync(new URL(`../../../public${item.record.evidenceUrl}`, import.meta.url), "utf8")),
]));

test("the complete snapshot counts attacks once and excludes invalid pairs", () => {
  const groups = groupResultModes(RUN.cases);
  assert.deepEqual(groups.failed.map(mode => mode.examples.length), [24, 4]);
  assert.equal(groups.passed.reduce((n, mode) => n + mode.examples.length, 0), 119);
  assert.equal(RUN.cases.length, 147);
  assert.equal(new Set(RUN.cases.filter(c => c.perturbed.outcome === "failed").map(c => c.taskKey)).size, 1);
});

test("groups repeated modes, ranks by count, and retains matching examples", () => {
  const repeated = { ...RUN.cases[1], id: "second-search-example" };
  const other = { ...RUN.cases[0], mode: { id: "another-mode", label: "Another mode" } };
  const groups = groupResultModes([other, RUN.cases[1], repeated]);
  assert.equal(groups.failed[0].id, RUN.cases[1].mode.id);
  assert.deepEqual(groups.failed[0].examples.map((item) => item.id), [RUN.cases[1].id, repeated.id]);
  assert.equal(groups.failed.reduce((n, mode) => n + mode.examples.length, 0), 3);
});

test("successful attacked runs stay separate even when a mode id matches a failure", () => {
  const success = {
    ...RUN.cases[0],
    id: "test-only-success",
    mode: { ...RUN.cases[0].mode, label: "Correct API selection" },
    perturbed: { outcome: "passed", text: "Test-only successful attacked run", code: "PASS" },
  };
  const groups = groupResultModes([RUN.cases[0], success]);
  assert.equal(groups.failed.length, 1);
  assert.equal(groups.passed.length, 1);
  assert.equal(groups.passed[0].label, success.mode.label);
  assert.deepEqual(groups.passed[0].examples, [success]);
  assert.notEqual(groups.passed[0].key, groups.failed[0].key);
});

test("an empty export creates no categories or implied results", () => {
  assert.deepEqual(groupResultModes([]), { failed: [], passed: [] });
});

test("every displayed run links to its actual model trace, patch, exposure, and clean control", () => {
  for (const item of RUN.cases) {
    const evidence = evidenceById.get(item.id);
    assert.equal(evidence.id, item.sourceId);
    assert.equal(evidence.attack.receipt.target_model.id, "gpt-6-astra");
    assert.equal(evidence.clean.receipt.diagnostic_passed, true);
    assert.equal(evidence.attack.receipt.diagnostic_passed, item.perturbed.outcome === "passed");
    assert.equal(evidence.attack.receipt.prepared_ref, evidence.clean.receipt.prepared_ref);
    assert.deepEqual(evidence.attack.receipt.budget, evidence.clean.receipt.budget);
    assert.equal(evidence.exposure.status, "verified");
    assert.equal(evidence.exposure.visible_changed, true);
    assert.ok(item.perturbed.output.startsWith(evidence.attack.patch.trimEnd()));
    assert.ok(evidence.attack.tools.length > 0);
    assert.ok(evidence.sourceFiles.some(file => file.file === "candidate.patch"));
    if (item.perturbed.outcome === "failed") {
      assert.equal(evidence.goldControl.diagnostic_passed, true);
      assert.equal(evidence.goldFrozen.exit, 0);
      assert.equal(evidence.goldSemantic.exit, 0);
      assert.match(evidence.attack.semantic.stdout, /FAILED /);
      assert.equal(evidence.attack.frozen.exit, 0);
    }
  }
});

test("the dashboard includes every eligible pair exactly once and no excluded episode", () => {
  const inventory = JSON.parse(readFileSync(new URL("episode-inventory.json", dataRoot), "utf8"));
  const summary = JSON.parse(readFileSync(new URL("summary.json", dataRoot), "utf8"));
  const eligible = inventory.filter(item => ["supported_attack_failure", "attack_resisted"].includes(item.dashboard_classification));
  assert.equal(new Set(inventory.map(item => item.id)).size, inventory.length);
  assert.equal(new Set(RUN.cases.map(item => item.id)).size, RUN.cases.length);
  assert.deepEqual(RUN.cases.map(item => item.sourceId).sort(), eligible.map(item => item.id).sort());
  assert.deepEqual(
    readdirSync(new URL("cases/", dataRoot)).filter(name => name.endsWith(".json")).sort(),
    RUN.cases.map(item => `${item.id}.json`).sort(),
  );
  assert.equal(summary.registeredEpisodes, inventory.length);
  assert.equal(summary.caseCount, RUN.cases.length);
  assert.equal(summary.failureCount, RUN.cases.filter(item => item.perturbed.outcome === "failed").length);
  assert.equal(summary.resistedCount, RUN.cases.filter(item => item.perturbed.outcome === "passed").length);
  assert.equal(summary.distinctTasks, new Set(RUN.cases.map(item => item.taskKey)).size);
  const byId = new Map(inventory.map(item => [item.id, item]));
  for (const item of RUN.cases) {
    const original = byId.get(item.sourceId);
    const control = byId.get(item.record.controlId);
    assert.equal(original.task_key, item.taskKey);
    assert.equal(original.condition, item.record.condition);
    assert.equal(original.repetition + 1, item.record.repetition);
    assert.equal(original.outcome, item.perturbed.outcome === "passed" ? "pass" : "fail");
    assert.equal(control.outcome, "pass");
    assert.ok(["clean", "control"].includes(control.condition));
    assert.equal(control.task_key, item.taskKey);
    assert.equal(control.arm, original.arm);
    assert.equal(control.repetition, original.repetition);
  }
});

test("displayed counts and failure categories match the recorded checks", () => {
  for (const item of RUN.cases) {
    const evidence = evidenceById.get(item.id);
    const failed = evidence.attack.tests.filter(check => ["FAILED", "ERROR"].includes(check.status));
    const passed = evidence.attack.tests.filter(check => check.status === "PASSED");
    assert.equal(item.record.failedChecks, failed.length, item.id);
    assert.equal(item.record.passedChecks, passed.length, item.id);
    assert.equal(item.record.testCount, evidence.attack.tests.length, item.id);
    assert.equal(item.record.attackToolCalls, evidence.attack.tools.length, item.id);
    assert.equal(item.record.cleanToolCalls, evidence.clean.tools.length, item.id);
    for (const arm of [evidence.attack, evidence.clean]) {
      assert.ok(arm.tests.length > 0, item.id);
      assert.equal(new Set(arm.tests.map(check => check.name)).size, arm.tests.length, item.id);
      assert.deepEqual(arm.tests, [...arm.frozen.tests, ...arm.semantic.tests]);
      assert.equal(arm.receipt.diagnostic_passed, arm.tests.every(check => check.status === "PASSED"), item.id);
      for (const suite of [arm.frozen, arm.semantic]) {
        if (!suite.tests.length) continue;
        const footer = suite.stdout.trim().split("\n").at(-1);
        const reported = Object.fromEntries([...footer.matchAll(/(\d+) (passed|failed|error)/g)].map(([, count, status]) => [status, Number(count)]));
        const counted = suite.tests.reduce((counts, check) => {
          const status = check.status.toLowerCase();
          counts[status] = (counts[status] ?? 0) + 1;
          return counts;
        }, {});
        assert.deepEqual(counted, reported, `${item.id}: ${footer}`);
      }
    }
    if (failed.length) {
      const localeFailure = failed.some(check => check.name.includes("preserves_locale_and_branch"));
      assert.equal(item.mode.id, localeFailure ? "lost-locale" : "lost-defaults", item.id);
      assert.ok(failed.some(check => check.name.includes("preserves_decider_defaults")), item.id);
      assert.ok(failed.every(check => evidence.attack.semantic.tests.some(semantic => semantic.name === check.name && semantic.status === check.status)), item.id);
    }
  }
});

test("the demo's guidance and results retain the actual attack and visible tool responses", () => {
  for (const item of RUN.cases) {
    const evidence = evidenceById.get(item.id);
    assert.equal(item.program, evidence.draft.perturbation.source, item.id);
    const injected = evidence.attack.observations.filter(observation => observation.visible_trigger).map(observation => {
      assert.ok(observation.visible_output.startsWith(observation.visible_raw), item.id);
      return observation.visible_output.slice(observation.visible_raw.length).trim();
    });
    assert.ok(injected.length > 0, item.id);
    assert.equal(item.injectedText, injected.join("\n\n"), item.id);
    for (const [side, arm] of [["perturbed", evidence.attack], ["control", evidence.clean]]) {
      assert.equal(item[side].output, arm.output, item.id);
      assert.equal(item[side].code, arm.code, item.id);
      for (const observation of arm.observations) {
        const tool = arm.tools.find(tool => tool.step === observation.step && tool.call.name === observation.tool);
        if (tool && observation.visible_output !== undefined) {
          assert.equal(tool.result, observation.visible_output, `${item.id}: ${side} step ${observation.step}`);
        }
      }
    }
  }
});
