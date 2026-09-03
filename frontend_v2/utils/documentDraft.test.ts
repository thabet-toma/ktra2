import assert from "node:assert/strict";
import test from "node:test";

import {
  DRAFT_MAX_AGE_MS,
  buildDocumentDraftKey,
  evaluateDraftRestore,
  isDraftExpired,
  selectExpiredDraftKeys,
  shouldPersistDraft,
} from "./documentDraft.ts";

/* ─────────────────────────── هويّة المسودّة ─────────────────────────── */

test("مفتاح مستند قائم يختلف عن مفتاح مستند جديد لنفس التبويب", () => {
  const existing = buildDocumentDraftKey({
    tenantId: 3,
    docType: "purchase_invoice",
    docId: 42,
    tabId: "tab-a",
  });
  const fresh = buildDocumentDraftKey({
    tenantId: 3,
    docType: "purchase_invoice",
    docId: null,
    tabId: "tab-a",
  });
  assert.notEqual(existing, fresh);
});

test("فاتورتان جديدتان في تبويبين مختلفين تحملان مفتاحين مختلفين", () => {
  const a = buildDocumentDraftKey({
    tenantId: 3,
    docType: "purchase_invoice",
    docId: undefined,
    tabId: "tab-a",
  });
  const b = buildDocumentDraftKey({
    tenantId: 3,
    docType: "purchase_invoice",
    docId: undefined,
    tabId: "tab-b",
  });
  assert.notEqual(a, b, "العطب القائم: مفتاح واحد ('new') لكل الفواتير الجديدة");
});

test("نفس المستند بشركتين مختلفتين يحمل مفتاحين مختلفين", () => {
  const t3 = buildDocumentDraftKey({
    tenantId: 3,
    docType: "purchase_invoice",
    docId: 42,
    tabId: "tab-a",
  });
  const t4 = buildDocumentDraftKey({
    tenantId: 4,
    docType: "purchase_invoice",
    docId: 42,
    tabId: "tab-a",
  });
  assert.notEqual(t3, t4);
});

test("مستندان جديدان في نفس التبويب لنوعين مختلفين لا يتصادمان", () => {
  const invoice = buildDocumentDraftKey({
    tenantId: 3,
    docType: "purchase_invoice",
    docId: null,
    tabId: "tab-a",
  });
  const quote = buildDocumentDraftKey({
    tenantId: 3,
    docType: "price_offer",
    docId: null,
    tabId: "tab-a",
  });
  assert.notEqual(invoice, quote);
});

/* ─────────────────────────── علامة «لُمِس» ─────────────────────────── */

test("لا كتابة بلا لمسة — التعبئة البرمجية وحدها لا تكفي", () => {
  // المستدعي هو من يرفع isTouched؛ التعبئة البرمجية (تحميل مستند من الخادم)
  // لا يجوز أن ترفعها — هنا نختبر أن الدالة تحترم القيمة كما وصلت.
  assert.equal(shouldPersistDraft(false), false);
});

test("أوّل تعديل مستخدم يُفعّل الكتابة", () => {
  assert.equal(shouldPersistDraft(true), true);
});

test("رأسٌ بلا بنود مؤهَّلٌ للحفظ — نقض lines.length > 0", () => {
  // لا حقل `lines` في القرار أصلاً: القرار وحيدٌ هو isTouched. رأسٌ لُمِس (عميل
  // أو تاريخ كُتب) يُحفَظ حتى بلا بند واحد.
  const touchedHeaderOnly = true;
  assert.equal(shouldPersistDraft(touchedHeaderOnly), true);
});

test("مستندٌ مرحَّلٌ لُمِس يُحفَظ أيضاً — نقض status === 'draft'", () => {
  // shouldPersistDraft لا تقرأ حالة المستند إطلاقاً؛ القرار بمعزل عنها.
  assert.equal(shouldPersistDraft(true), true);
});

/* ─────────────────────────── أهليّة الاستعادة ─────────────────────────── */

test("ختمان متطابقان ⇒ استعادة تلقائية", () => {
  const result = evaluateDraftRestore({
    isPosted: false,
    draftDocUpdatedAt: "2026-09-03T16:05:00.000Z",
    currentDocUpdatedAt: "2026-09-03T16:05:00.000Z",
  });
  assert.equal(result, "restore");
});

test("مستندٌ جديد (بلا ختم من الأصل) ⇒ استعادة تلقائية", () => {
  const result = evaluateDraftRestore({
    isPosted: false,
    draftDocUpdatedAt: null,
    currentDocUpdatedAt: null,
  });
  assert.equal(result, "restore");
});

test("ختم الخادم أحدث من ختم المسودّة ⇒ لا استعادة تلقائية (تعارض)", () => {
  const result = evaluateDraftRestore({
    isPosted: false,
    draftDocUpdatedAt: "2026-09-03T16:05:00.000Z",
    currentDocUpdatedAt: "2026-09-03T17:20:00.000Z",
  });
  assert.equal(result, "stale");
});

test("مستندٌ مرحَّلٌ ⇒ لا استعادة تلقائية إطلاقاً ولو تطابقت الأختام", () => {
  const result = evaluateDraftRestore({
    isPosted: true,
    draftDocUpdatedAt: "2026-09-03T16:05:00.000Z",
    currentDocUpdatedAt: "2026-09-03T16:05:00.000Z",
  });
  assert.equal(result, "posted");
});

test("الحفظ والاستعادة حكمان منفصلان: مرحَّلٌ لُمِس يُحفَظ ويبقى بلا استعادة تلقائية", () => {
  assert.equal(shouldPersistDraft(true), true);
  assert.equal(
    evaluateDraftRestore({
      isPosted: true,
      draftDocUpdatedAt: "2026-09-03T16:05:00.000Z",
      currentDocUpdatedAt: "2026-09-03T16:05:00.000Z",
    }),
    "posted",
  );
});

/* ─────────────────────────── الكنس — ٣٠ يوماً ─────────────────────────── */

test("مسودة عمرها ٣١ يوماً تُكنَس", () => {
  const now = Date.parse("2026-09-03T00:00:00.000Z");
  const updatedAt = now - 31 * 24 * 60 * 60 * 1000;
  assert.equal(isDraftExpired(updatedAt, now), true);
});

test("مسودة عمرها ٢٩ يوماً تبقى", () => {
  const now = Date.parse("2026-09-03T00:00:00.000Z");
  const updatedAt = now - 29 * 24 * 60 * 60 * 1000;
  assert.equal(isDraftExpired(updatedAt, now), false);
});

test("عند حافة الـ٣٠ يوماً بالضبط: لم تتجاوز المهلة بعد فتبقى", () => {
  const now = Date.parse("2026-09-03T00:00:00.000Z");
  const updatedAt = now - DRAFT_MAX_AGE_MS;
  assert.equal(isDraftExpired(updatedAt, now), false);
});

test("طابعٌ زمنيّ تالف يُعامَل كمنتهٍ — يُكنَس لا يُوثَق به", () => {
  assert.equal(isDraftExpired("not-a-date", Date.now()), true);
});

test("selectExpiredDraftKeys يفرز ٣١ يوماً عن ٢٩ يوماً في نفس المجموعة", () => {
  const now = Date.parse("2026-09-03T00:00:00.000Z");
  const drafts = [
    { key: "old:31d", updatedAt: now - 31 * 24 * 60 * 60 * 1000 },
    { key: "fresh:29d", updatedAt: now - 29 * 24 * 60 * 60 * 1000 },
    { key: "today", updatedAt: now },
  ];
  assert.deepEqual(selectExpiredDraftKeys(drafts, now), ["old:31d"]);
});
