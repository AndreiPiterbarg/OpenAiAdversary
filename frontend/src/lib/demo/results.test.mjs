import assert from "node:assert/strict";
import test from "node:test";
import { RUN } from "./run-data.ts";
import { groupResultModes } from "./results.ts";

test("passing controls and unavailable follow-ups do not count as attack resistance", () => {
  const groups = groupResultModes(RUN.cases);
  assert.equal(groups.passed.length, 0);
  assert.equal(groups.failed.length, 3);
  assert.equal(groups.failed.reduce((n, mode) => n + mode.examples.length, 0), 3);
});

test("groups repeated modes, ranks by count, and retains matching examples", () => {
  const repeated = { ...RUN.cases[1], id: "second-search-example" };
  const groups = groupResultModes([...RUN.cases, repeated]);
  assert.equal(groups.failed[0].id, RUN.cases[1].mode.id);
  assert.deepEqual(groups.failed[0].examples.map((item) => item.id), [RUN.cases[1].id, repeated.id]);
  assert.equal(groups.failed.reduce((n, mode) => n + mode.examples.length, 0), 4);
});

test("successful attacked runs stay separate even when a mode id matches a failure", () => {
  const success = {
    ...RUN.cases[0],
    id: "test-only-success",
    mode: { ...RUN.cases[0].mode, label: "Correct API selection" },
    perturbed: { outcome: "passed", text: "Test-only successful attacked run", code: "PASS" },
  };
  const groups = groupResultModes([...RUN.cases, success]);
  assert.equal(groups.failed.length, 3);
  assert.equal(groups.passed.length, 1);
  assert.equal(groups.passed[0].label, success.mode.label);
  assert.deepEqual(groups.passed[0].examples, [success]);
  assert.notEqual(groups.passed[0].key, groups.failed[0].key);
});

test("an empty export creates no categories or implied results", () => {
  assert.deepEqual(groupResultModes([]), { failed: [], passed: [] });
});
