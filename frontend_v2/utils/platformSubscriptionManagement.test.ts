import assert from "node:assert/strict";
import test from "node:test";

import {
  ACTIONS_REQUIRING_BILLING_CUSTOMER,
  POLICY_EFFECTIVE_STATE_LABEL,
  describePlatformOpsError,
  formatEngagementCount,
  formatTrialRemainingLabel,
  getAllowedSubscriptionActions,
  validateCommercialNumbers,
} from "./platformSubscriptionManagement.ts";

test("a company with no subscription row can only start a trial or activate paid", () => {
  assert.deepEqual(getAllowedSubscriptionActions(null), ["start_trial", "activate_paid"]);
});

test("a trial subscription can convert, suspend, or be cancelled", () => {
  assert.deepEqual(getAllowedSubscriptionActions("trial"), ["convert_to_paid", "suspend", "cancel"]);
});

test("an active subscription can be suspended, cancelled, or edited", () => {
  assert.deepEqual(getAllowedSubscriptionActions("active"), ["suspend", "cancel", "edit_settings"]);
});

test("a suspended subscription can resume, be cancelled, or have its terms edited", () => {
  // الخادم يرفض الملغى وحده، فالمعلّق يحتفظ بزر تعديل الشروط.
  assert.deepEqual(getAllowedSubscriptionActions("suspended"), ["resume", "cancel", "edit_settings"]);
});

test("a blank numeric field is refused instead of silently reading as zero", () => {
  assert.equal(
    validateCommercialNumbers({ monthly_fee: "300", included_quota: "", overage_unit_price: "2" }),
    "أدخل كل القيم الرقمية.",
  );
  assert.equal(
    validateCommercialNumbers({ monthly_fee: "300", included_quota: "300", overage_unit_price: "2", trial_days: "" }),
    "أدخل كل القيم الرقمية.",
  );
});

test("commercial numbers refuse negatives and fractional counts, and accept a valid set", () => {
  assert.equal(
    validateCommercialNumbers({ monthly_fee: "-1", included_quota: "300", overage_unit_price: "2" }),
    "الرسوم وأسعار التجاوز يجب أن تكون أرقاماً غير سالبة.",
  );
  assert.equal(
    validateCommercialNumbers({ monthly_fee: "300", included_quota: "1.5", overage_unit_price: "2" }),
    "الحصة يجب أن تكون عدداً صحيحاً غير سالب.",
  );
  assert.equal(
    validateCommercialNumbers({ monthly_fee: "300", included_quota: "300", overage_unit_price: "2", trial_days: "-7" }),
    "أيام التجربة يجب أن تكون عدداً صحيحاً غير سالب.",
  );
  assert.equal(
    validateCommercialNumbers({ monthly_fee: "300.50", included_quota: "300", overage_unit_price: "2", trial_days: "7" }),
    null,
  );
});

test("a cancelled subscription never resumes — only a fresh paid activation", () => {
  assert.deepEqual(getAllowedSubscriptionActions("cancelled"), ["activate_paid"]);
});

test("a scheduled cancellation adds a withdraw action to trial/active/suspended", () => {
  assert.deepEqual(
    getAllowedSubscriptionActions("active", true),
    ["suspend", "cancel", "edit_settings", "withdraw_cancellation"],
  );
});

test("a scheduled cancellation flag is ignored once already cancelled", () => {
  assert.deepEqual(getAllowedSubscriptionActions("cancelled", true), ["activate_paid"]);
});

test("trial remaining label uses the Arabic plural for 3–10 days", () => {
  const now = new Date("2026-01-01T00:00:00Z");
  const endsIn3Days = new Date("2026-01-04T00:00:00Z").toISOString();
  assert.equal(formatTrialRemainingLabel(endsIn3Days, now), "يتبقّى 3 أيام على انتهاء التجربة");
});

test("trial remaining label uses the Arabic dual and long-count forms", () => {
  const now = new Date("2026-01-01T00:00:00Z");
  assert.equal(
    formatTrialRemainingLabel(new Date("2026-01-03T00:00:00Z").toISOString(), now),
    "يتبقّى يومان على انتهاء التجربة",
  );
  assert.equal(
    formatTrialRemainingLabel(new Date("2026-01-12T00:00:00Z").toISOString(), now),
    "يتبقّى 11 يوماً على انتهاء التجربة",
  );
});

test("trial remaining label handles a single day left", () => {
  const now = new Date("2026-01-01T00:00:00Z");
  const endsInOneDay = new Date("2026-01-01T12:00:00Z").toISOString();
  assert.equal(formatTrialRemainingLabel(endsInOneDay, now), "يتبقّى يوم واحد على انتهاء التجربة");
});

test("trial remaining label reports an expired trial", () => {
  const now = new Date("2026-01-05T00:00:00Z");
  const endedYesterday = new Date("2026-01-04T00:00:00Z").toISOString();
  assert.equal(formatTrialRemainingLabel(endedYesterday, now), "انتهت التجربة");
});

test("trial remaining label is empty when there is no trial at all", () => {
  assert.equal(formatTrialRemainingLabel(null), "");
});

test("engagement counts use correct Arabic counted nouns", () => {
  assert.equal(formatEngagementCount(0), "لا ارتباطات نشطة");
  assert.equal(formatEngagementCount(1), "ارتباطاً واحداً");
  assert.equal(formatEngagementCount(2), "ارتباطين");
  assert.equal(formatEngagementCount(3), "3 ارتباطات");
  assert.equal(formatEngagementCount(10), "10 ارتباطات");
  assert.equal(formatEngagementCount(11), "11 ارتباطاً");
  assert.equal(formatEngagementCount(1200), "1200 ارتباطاً");
});

test("paid activation and trial conversion are the actions gated on a billing customer", () => {
  assert.deepEqual([...ACTIONS_REQUIRING_BILLING_CUSTOMER].sort(), ["activate_paid", "convert_to_paid"]);
});

test("every policy effective state has a label", () => {
  assert.deepEqual(Object.keys(POLICY_EFFECTIVE_STATE_LABEL).sort(), ["current", "draft", "retired", "scheduled"]);
});

test("subscription errors: 403 gets the permission message, other failures use the DRF body", () => {
  assert.equal(
    describePlatformOpsError(Object.assign(new Error("x"), { status: 403 }), "لا صلاحية", "فشل"),
    "لا صلاحية",
  );
  const drfBody = Object.assign(new Error(JSON.stringify({ detail: "عميل الفوترة مطلوب." })), { status: 400 });
  assert.equal(describePlatformOpsError(drfBody, "لا صلاحية", "فشل"), "عميل الفوترة مطلوب.");
  assert.equal(describePlatformOpsError(null, "لا صلاحية", "فشل"), "فشل");
});
