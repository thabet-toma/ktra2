/**
 * شريط القيد السريع بثلاث خانات (issue #133): مقبوضات · مدفوعات · عمليات ذمم
 * تحلّ محلّ خانة المبلغ الواحدة في الوضع البسيط. مقبوضات تقترح المدين = الصندوق
 * الافتراضي، مدفوعات تقترح الدائن = الصندوق الافتراضي، وعمليات ذمم طرفٌ لطرف
 * بلا صندوق وبلا اقتراح على أي جهة.
 */
import assert from "node:assert/strict";
import test from "node:test";
import {
  applyQuickEntryAmount,
  emptyQuickEntryAmounts,
  noQuickEntryTouch,
  suggestQuickEntrySides,
} from "./journalQuickEntry.ts";

const noCurrent = { debitAccountId: null, creditAccountId: null };

test("مقبوضات تقترح المدين = الصندوق الافتراضي ولا تمسّ الدائن", () => {
  const sides = suggestQuickEntrySides({
    kind: "receipts",
    previousKind: null,
    amount: 100,
    defaultCashAccountId: 5,
    touched: noQuickEntryTouch(),
    current: noCurrent,
  });
  assert.deepEqual(sides, { debitAccountId: 5, creditAccountId: null });
});

test("مدفوعات تقترح الدائن = الصندوق الافتراضي ولا تمسّ المدين", () => {
  const sides = suggestQuickEntrySides({
    kind: "payments",
    previousKind: null,
    amount: 100,
    defaultCashAccountId: 5,
    touched: noQuickEntryTouch(),
    current: noCurrent,
  });
  assert.deepEqual(sides, { debitAccountId: null, creditAccountId: 5 });
});

test("عمليات ذمم — لا صندوق ولا اقتراح على أي جهة", () => {
  const current = { debitAccountId: 11, creditAccountId: 22 };
  const sides = suggestQuickEntrySides({
    kind: "receivable",
    previousKind: null,
    amount: 100,
    defaultCashAccountId: 5,
    touched: noQuickEntryTouch(),
    current,
  });
  assert.deepEqual(sides, current);
});

test("بلا صندوق افتراضي مُعرَّف: لا اقتراح ولا انهيار", () => {
  const sidesReceipt = suggestQuickEntrySides({
    kind: "receipts",
    previousKind: null,
    amount: 100,
    defaultCashAccountId: null,
    touched: noQuickEntryTouch(),
    current: noCurrent,
  });
  assert.deepEqual(sidesReceipt, noCurrent);

  const sidesPayment = suggestQuickEntrySides({
    kind: "payments",
    previousKind: null,
    amount: 100,
    defaultCashAccountId: null,
    touched: noQuickEntryTouch(),
    current: noCurrent,
  });
  assert.deepEqual(sidesPayment, noCurrent);
});

test("حسابٌ لمسه المستخدم لا يُدهس حين يتغيّر المبلغ لاحقاً", () => {
  const current = { debitAccountId: 42, creditAccountId: null };
  const sides = suggestQuickEntrySides({
    kind: "receipts",
    previousKind: "receipts",
    amount: 250, // مبلغ جديد بعد أن اختار المستخدم حساب 42 يدوياً
    defaultCashAccountId: 5,
    touched: { debit: true, credit: false },
    current,
  });
  assert.deepEqual(sides, current);
  assert.equal(sides.debitAccountId, 42);
});

test("الطرف الآخر (الدائن) يبقى يُقترح رغم لمس المدين لأنه مقبوضات لا يمسّه أصلاً", () => {
  // توضيحٌ إضافي: touched.credit=false لكن «مقبوضات» أصلاً لا تقترح على الدائن.
  const current = { debitAccountId: 42, creditAccountId: 7 };
  const sides = suggestQuickEntrySides({
    kind: "receipts",
    previousKind: "receipts",
    amount: 250,
    defaultCashAccountId: 5,
    touched: { debit: true, credit: false },
    current,
  });
  assert.deepEqual(sides, current);
});

test("التمانع المتبادل: رقمٌ في مقبوضات يُفرغ مدفوعات وذمم", () => {
  const prev = { receipts: "", payments: "50", receivable: "" };
  const next = applyQuickEntryAmount(prev, "receipts", "100");
  assert.deepEqual(next, { receipts: "100", payments: "", receivable: "" });
});

test("التمانع المتبادل: رقمٌ في عمليات ذمم يُفرغ مقبوضات ومدفوعات", () => {
  const prev = { receipts: "30", payments: "", receivable: "" };
  const next = applyQuickEntryAmount(prev, "receivable", "70");
  assert.deepEqual(next, { receipts: "", payments: "", receivable: "70" });
});

test("قيمة ابتدائية فارغة للخانات الثلاث", () => {
  assert.deepEqual(emptyQuickEntryAmounts(), {
    receipts: "", payments: "", receivable: "",
  });
});

/* ── التراجع عن اقتراحٍ سابق عند تبديل الخانة (دفعٌ من المراجعة) ──────────
 * التبديل بين الخانات كان يُفرغ نصوص المبالغ الثلاثة (`applyQuickEntryAmount`)
 * بلا أن يمسّ الحساب الذي اقترحته الخانة السابقة — فيبقى صندوقٌ واحدٌ على
 * الجهتين معاً (مقبوضات ثم مدفوعات)، أو صندوقٌ يتيّم عمليات الذمم التي يجب
 * ألّا تحمل صندوقاً على أيّ جهة. الإصلاح: `suggestQuickEntrySides` تعرف
 * الخانة السابقة، وتُفرغ الجهة التي اقترحتها ما لم يكن المستخدم قد لمسها. */

test("مقبوضات ثم مدفوعات: تُفرَغ الجهة المقترَحة سابقاً (المدين) وتُقترَح الجديدة (الدائن)", () => {
  const afterReceipts = suggestQuickEntrySides({
    kind: "receipts",
    previousKind: null,
    amount: 100,
    defaultCashAccountId: 5,
    touched: noQuickEntryTouch(),
    current: noCurrent,
  });
  assert.deepEqual(afterReceipts, { debitAccountId: 5, creditAccountId: null });

  const afterPayments = suggestQuickEntrySides({
    kind: "payments",
    previousKind: "receipts",
    amount: 100,
    defaultCashAccountId: 5,
    touched: noQuickEntryTouch(),
    current: afterReceipts,
  });
  assert.deepEqual(afterPayments, { debitAccountId: null, creditAccountId: 5 });
});

test("مقبوضات ثم عمليات ذمم: تنتهي الجهتان معاً بلا صندوق", () => {
  const afterReceipts = suggestQuickEntrySides({
    kind: "receipts",
    previousKind: null,
    amount: 100,
    defaultCashAccountId: 5,
    touched: noQuickEntryTouch(),
    current: noCurrent,
  });
  assert.deepEqual(afterReceipts, { debitAccountId: 5, creditAccountId: null });

  const afterReceivable = suggestQuickEntrySides({
    kind: "receivable",
    previousKind: "receipts",
    amount: 100,
    defaultCashAccountId: 5,
    touched: noQuickEntryTouch(),
    current: afterReceipts,
  });
  assert.deepEqual(afterReceivable, { debitAccountId: null, creditAccountId: null });
});

test("مقبوضات، تعديل المدين يدوياً، ثم مدفوعات: حساب المستخدم يبقى (اللمس يغلب التراجع)", () => {
  const afterReceipts = suggestQuickEntrySides({
    kind: "receipts",
    previousKind: null,
    amount: 100,
    defaultCashAccountId: 5,
    touched: noQuickEntryTouch(),
    current: noCurrent,
  });
  assert.deepEqual(afterReceipts, { debitAccountId: 5, creditAccountId: null });

  // المستخدم يغيّر المدين المقترَح بيده إلى حسابٍ آخر (99) ويُعلَّم لَمسُه.
  const manualCurrent = { debitAccountId: 99, creditAccountId: afterReceipts.creditAccountId };
  const touchedAfterManualEdit = { debit: true, credit: false };

  const afterPayments = suggestQuickEntrySides({
    kind: "payments",
    previousKind: "receipts",
    amount: 100,
    defaultCashAccountId: 5,
    touched: touchedAfterManualEdit,
    current: manualCurrent,
  });
  assert.deepEqual(afterPayments, { debitAccountId: 99, creditAccountId: 5 });
});
