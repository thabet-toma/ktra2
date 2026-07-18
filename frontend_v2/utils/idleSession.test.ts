import test from "node:test";
import assert from "node:assert/strict";
import {
  ACTIVITY_KEY,
  idleRemainingMs,
  isUserActivityRequest,
  readLastActivity,
  writeLastActivity,
} from "./idleSession.ts";

/** مخزن بسيط يحاكي localStorage المشترك بين التبويبات. */
const makeStore = (initial: Record<string, string> = {}) => {
  const data: Record<string, string> = { ...initial };
  return {
    data,
    getItem: (k: string) => (k in data ? data[k] : null),
    setItem: (k: string, v: string) => {
      data[k] = v;
    },
  };
};

const TIMEOUT = 3 * 60 * 60 * 1000;

test("writeLastActivity ثم readLastActivity يعيد نفس اللحظة", () => {
  const store = makeStore();
  writeLastActivity(store, 1_700_000_000_000);
  assert.equal(store.data[ACTIVITY_KEY], "1700000000000");
  assert.equal(readLastActivity(store), 1_700_000_000_000);
});

test("غياب القيمة = لا سجل نشاط سابق", () => {
  assert.equal(readLastActivity(makeStore()), null);
});

test("قيمة تالفة تُعامل كغياب بدل أن تُنهي الجلسة فوراً", () => {
  assert.equal(readLastActivity(makeStore({ [ACTIVITY_KEY]: "abc" })), null);
  assert.equal(idleRemainingMs(makeStore({ [ACTIVITY_KEY]: "abc" }), 1000, TIMEOUT), TIMEOUT);
});

test("بلا سجل نشاط تبدأ المهلة كاملة", () => {
  assert.equal(idleRemainingMs(makeStore(), 1000, TIMEOUT), TIMEOUT);
});

test("نشاط في تبويب آخر يمدّد المهلة المتبقية لهذا التبويب", () => {
  // التبويب «أ» ساكن منذ ساعتين، لكن المستخدم كان نشطاً في التبويب «ب» قبل دقيقة.
  const store = makeStore();
  const now = 10_000_000_000;
  writeLastActivity(store, now - 60_000);
  assert.equal(idleRemainingMs(store, now, TIMEOUT), TIMEOUT - 60_000);
});

test("انقضاء المهلة يعطي صفراً ولا ينزل تحته", () => {
  const store = makeStore();
  const now = 10_000_000_000;
  writeLastActivity(store, now - TIMEOUT - 5 * 60_000);
  assert.equal(idleRemainingMs(store, now, TIMEOUT), 0);
});

test("طابع زمني مستقبلي (ساعة جهاز مضبوطة للخلف) لا يُنهي الجلسة", () => {
  const store = makeStore();
  const now = 10_000_000_000;
  writeLastActivity(store, now + 60_000);
  assert.equal(idleRemainingMs(store, now, TIMEOUT), TIMEOUT);
});

test("طلبات الكتابة تُحتسب نشاطاً للمستخدم", () => {
  for (const m of ["POST", "PUT", "PATCH", "DELETE", "post", "patch"]) {
    assert.equal(isUserActivityRequest(m), true, m);
  }
});

test("القراءة لا تُحتسب نشاطاً — وإلا أبقتها المؤقتات الخلفية حيّة للأبد", () => {
  for (const m of ["GET", "HEAD", "OPTIONS", "get", undefined]) {
    assert.equal(isUserActivityRequest(m), false, String(m));
  }
});

test("مخزن يرمي استثناءً (وضع الخصوصية) لا يكسر الحساب", () => {
  const throwing = {
    getItem: () => {
      throw new Error("denied");
    },
    setItem: () => {
      throw new Error("denied");
    },
  };
  assert.equal(readLastActivity(throwing), null);
  assert.equal(idleRemainingMs(throwing, 1000, TIMEOUT), TIMEOUT);
  assert.doesNotThrow(() => writeLastActivity(throwing, 1000));
});
