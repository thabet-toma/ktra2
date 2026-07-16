import assert from "node:assert/strict";
import test from "node:test";

import {
  remainingRequestBudgetMs,
  retryFitsRequestBudget,
} from "./networkRequestBudget.ts";

test("shares one deadline across every fetch attempt", () => {
  const deadline = 30_000;
  assert.equal(remainingRequestBudgetMs(deadline, 0), 30_000);
  assert.equal(remainingRequestBudgetMs(deadline, 12_500), 17_500);
  assert.equal(remainingRequestBudgetMs(deadline, 31_000), 0);
});

test("does not start a retry when backoff consumes the remaining budget", () => {
  assert.equal(retryFitsRequestBudget(30_000, 1_200, 28_700), true);
  assert.equal(retryFitsRequestBudget(30_000, 1_200, 28_800), false);
});
