// Exercises the tally logic in isolation from the DOM. Uses Node's built-in
// test runner and assert module — no new dependencies, matches the "no new
// deps" constraint on this frontend.
//
// Run with: node --test src/tally.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { recordPriced, totalOf, percentOf, colorFor } from "./tally.ts";

test("known values (v1/v2) split as expected", () => {
  const counts = new Map<string, number>();
  recordPriced(counts, "v1");
  recordPriced(counts, "v1");
  recordPriced(counts, "v1");
  recordPriced(counts, "v2");

  assert.equal(counts.get("v1"), 3);
  assert.equal(counts.get("v2"), 1);
  assert.equal(totalOf(counts), 4);
  assert.equal(percentOf(counts, "v1"), 75);
  assert.equal(percentOf(counts, "v2"), 25);
});

test("an unexpected priced_by value gets its own bucket, not folded into an existing one", () => {
  const counts = new Map<string, number>();
  recordPriced(counts, "v1");
  recordPriced(counts, "v1");
  recordPriced(counts, "pricing-v1"); // e.g. served_by from a different service naming scheme

  // The old bug: anything !== "v1" was counted as v2. Prove that no longer
  // happens — "pricing-v1" must NOT be added to "v1"'s count, and must NOT
  // silently create/inflate a "v2" bucket that was never actually seen.
  assert.equal(counts.get("v1"), 2);
  assert.equal(counts.get("pricing-v1"), 1);
  assert.equal(counts.has("v2"), false);
  assert.equal(counts.size, 2);
  assert.equal(totalOf(counts), 3);
});

test("three distinct versions each get their own bucket", () => {
  const counts = new Map<string, number>();
  recordPriced(counts, "v1");
  recordPriced(counts, "v2");
  recordPriced(counts, "v3-canary");

  assert.equal(counts.size, 3);
  assert.equal(percentOf(counts, "v1"), 33);
  assert.equal(percentOf(counts, "v2"), 33);
  assert.equal(percentOf(counts, "v3-canary"), 33);
});

test("colorFor is stable per key and does not reassign on repeated calls", () => {
  const assigned = new Map<string, string>();
  const first = colorFor("v1", assigned);
  const second = colorFor("v2", assigned);
  const firstAgain = colorFor("v1", assigned);

  assert.equal(firstAgain, first);
  assert.notEqual(first, second);
});

test("empty counts: total and percent are 0, not NaN or a divide-by-zero error", () => {
  const counts = new Map<string, number>();
  assert.equal(totalOf(counts), 0);
  assert.equal(percentOf(counts, "v1"), 0);
});
