import assert from "node:assert/strict";
import test from "node:test";

import { evaluateArithmeticExpression } from "./arithmetic.ts";

test("respects multiplication and division precedence", () => {
  assert.equal(evaluateArithmeticExpression("2 + 3 * 4 - 8 / 2"), 10);
});

test("supports unary signs and decimal values", () => {
  assert.equal(evaluateArithmeticExpression("-2.5 * -4 + .5"), 10.5);
});

test("rejects JavaScript, malformed numbers and non-finite results", () => {
  for (const expression of ["alert(1)", "1..2 + 3", "1 / 0", "", "2 +"]) {
    assert.throws(() => evaluateArithmeticExpression(expression));
  }
});
