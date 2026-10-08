import assert from "node:assert/strict";
import test from "node:test";

import {
  isLongNoteBody,
  pinnedNotesCollapsedKey,
  pinnedNotesSummary,
  readPinnedNotesCollapsed,
  splitPageNotes,
  writePinnedNotesCollapsed,
} from "./pinnedPageNotes.ts";

function memoryStorage() {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => { data.set(key, value); },
    removeItem: (key: string) => { data.delete(key); },
  };
}

test("الشريط يعرض المثبّت غير المنجز فقط، والعدّاد يعدّ كل المفتوح", () => {
  const notes = [
    { id: 1, is_done: false, is_pinned: true },
    { id: 2, is_done: true, is_pinned: true },
    { id: 3, is_done: false, is_pinned: false },
    { id: 4, is_done: false },
  ];
  const { open, pinned } = splitPageNotes(notes);
  assert.deepEqual(open.map((n) => n.id), [1, 3, 4]);
  assert.deepEqual(pinned.map((n) => n.id), [1]);
});

test("مفتاح الطيّ لكل مستخدم ولكل مسار", () => {
  assert.equal(
    pinnedNotesCollapsedKey("u7", "/sales/invoices"),
    "ktra.pinnedNotes.collapsed.u7./sales/invoices",
  );
  assert.notEqual(
    pinnedNotesCollapsedKey("u7", "/sales/invoices"),
    pinnedNotesCollapsedKey("u8", "/sales/invoices"),
  );
  assert.notEqual(
    pinnedNotesCollapsedKey("u7", "/sales/invoices"),
    pinnedNotesCollapsedKey("u7", "/purchase-invoices"),
  );
});

test("حالة الطيّ تُحفظ وتُقرأ وتُمسح عند الفتح", () => {
  const storage = memoryStorage();
  const get = () => storage;
  assert.equal(readPinnedNotesCollapsed(get, "u7", "/a"), false);
  writePinnedNotesCollapsed(get, "u7", "/a", true);
  assert.equal(readPinnedNotesCollapsed(get, "u7", "/a"), true);
  assert.equal(readPinnedNotesCollapsed(get, "u8", "/a"), false);
  writePinnedNotesCollapsed(get, "u7", "/a", false);
  assert.equal(storage.data.size, 0);
});

test("تعطّل التخزين لا يرمي: القراءة «غير مطويّ» والكتابة صامتة", () => {
  const broken = () => { throw new Error("SecurityError"); };
  assert.equal(readPinnedNotesCollapsed(broken, "u7", "/a"), false);
  assert.doesNotThrow(() => writePinnedNotesCollapsed(broken, "u7", "/a", true));
  const throwingMethods = () => ({
    getItem: () => { throw new Error("denied"); },
    setItem: () => { throw new Error("quota"); },
    removeItem: () => { throw new Error("denied"); },
  });
  assert.equal(readPinnedNotesCollapsed(throwingMethods, "u7", "/a"), false);
  assert.doesNotThrow(() => writePinnedNotesCollapsed(throwingMethods, "u7", "/a", false));
});

test("سطر الطيّ يصرف العدد العربي: مفرد ومثنّى وجمع وتمييز", () => {
  assert.equal(pinnedNotesSummary(1, "1"), "ملاحظة مثبّتة على هذه الصفحة");
  assert.equal(pinnedNotesSummary(2, "2"), "ملاحظتان مثبّتتان على هذه الصفحة");
  assert.equal(pinnedNotesSummary(3, "3"), "3 ملاحظات مثبّتة على هذه الصفحة");
  assert.equal(pinnedNotesSummary(10, "10"), "10 ملاحظات مثبّتة على هذه الصفحة");
  assert.equal(pinnedNotesSummary(11, "11"), "11 ملاحظةً مثبّتة على هذه الصفحة");
});

test("النص الطويل يُقصّ بالحرف أو بالأسطر", () => {
  assert.equal(isLongNoteBody("قصيرة"), false);
  assert.equal(isLongNoteBody("س".repeat(221)), true);
  assert.equal(isLongNoteBody("1\n2\n3\n4"), false);
  assert.equal(isLongNoteBody("1\n2\n3\n4\n5"), true);
});
