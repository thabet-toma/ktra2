import assert from "node:assert/strict";
import test from "node:test";

import {
  canApproveHealthCheck,
  formatCapacityLabel,
  formatOnboardingRemainingLabel,
  getAllowedEngagementActions,
  missingMandatoryEvidenceCodes,
} from "./platformHealthAssignment.ts";

const item = (overrides: Partial<{
  code: string; mandatory: boolean; evidence_value: string | null; evidence_note: string;
}> = {}) => ({
  code: "opening_balance_completeness",
  mandatory: true,
  evidence_value: null,
  evidence_note: "",
  ...overrides,
});

test("a mandatory item with neither a value nor a note is reported as missing evidence", () => {
  assert.deepEqual(missingMandatoryEvidenceCodes([item()]), ["opening_balance_completeness"]);
});

test("a mandatory item with only a note, or only a value, is not missing evidence", () => {
  assert.deepEqual(missingMandatoryEvidenceCodes([item({ evidence_note: "تحقّقت يدوياً" })]), []);
  assert.deepEqual(missingMandatoryEvidenceCodes([item({ evidence_value: "3" })]), []);
});

test("a non-mandatory item never counts as missing evidence", () => {
  assert.deepEqual(missingMandatoryEvidenceCodes([item({ mandatory: false })]), []);
});

test("a draft with no complexity yet cannot be approved even with full evidence", () => {
  assert.equal(canApproveHealthCheck({ complexity: "" }, [item({ evidence_note: "تم" })]), false);
});

test("a draft with complexity and no missing evidence can be approved", () => {
  assert.equal(canApproveHealthCheck({ complexity: "low" }, [item({ evidence_note: "تم" })]), true);
});

test("a draft with complexity but a missing mandatory item cannot be approved", () => {
  assert.equal(canApproveHealthCheck({ complexity: "low" }, [item()]), false);
});

test("onboarding remaining label counts down and flips to expired", () => {
  const now = new Date("2026-01-01T00:00:00Z");
  assert.equal(
    formatOnboardingRemainingLabel(new Date("2026-01-02T00:00:00Z").toISOString(), now),
    "يتبقّى يوم واحد على انتهاء التهيئة المؤقتة",
  );
  assert.equal(
    formatOnboardingRemainingLabel(new Date("2025-12-31T00:00:00Z").toISOString(), now),
    "انتهت مهلة التهيئة المؤقتة",
  );
  assert.equal(formatOnboardingRemainingLabel(null), "");
});

test("capacity label pairs load against target through formatNumber", () => {
  assert.equal(formatCapacityLabel(2, 3), "2 / 3");
  assert.equal(formatCapacityLabel("2.00", "3.00"), "2 / 3");
});

test("allowed engagement actions follow status: active, suspended, revoked", () => {
  assert.deepEqual(getAllowedEngagementActions("active"), ["transfer", "suspend", "revoke"]);
  assert.deepEqual(getAllowedEngagementActions("suspended"), ["resume", "revoke"]);
  assert.deepEqual(getAllowedEngagementActions("revoked"), []);
});
