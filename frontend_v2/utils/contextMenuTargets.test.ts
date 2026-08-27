import test from "node:test";
import assert from "node:assert/strict";
import {
  calcSeedFromRawValue,
  formatCalcResult,
  readPartnerContext,
  readItemContext,
} from "./contextMenuTargets.ts";

test("calcSeedFromRawValue ينظّف فواصل الآلاف والعملة إلى رقم", () => {
  assert.equal(calcSeedFromRawValue("1,234.5"), "1234.5");
  assert.equal(calcSeedFromRawValue("12.50"), "12.5");
  assert.equal(calcSeedFromRawValue("-50"), "-50");
  assert.equal(calcSeedFromRawValue("$ 2,000"), "2000");
});

test("calcSeedFromRawValue يعيد فراغاً لغير الرقمي/الفارغ", () => {
  assert.equal(calcSeedFromRawValue(""), "");
  assert.equal(calcSeedFromRawValue(null), "");
  assert.equal(calcSeedFromRawValue(undefined), "");
  assert.equal(calcSeedFromRawValue("abc"), "");
  assert.equal(calcSeedFromRawValue("-"), "");
});

test("formatCalcResult يقصّ لأربع منازل بلا أصفار زائدة", () => {
  assert.equal(formatCalcResult(12.5), "12.5");
  assert.equal(formatCalcResult(10), "10");
  assert.equal(formatCalcResult(1 / 3), "0.3333");
  assert.equal(formatCalcResult(12.34567), "12.3457");
});

test("readPartnerContext يقرأ سياق عميل/مورد صالح", () => {
  const attrs: Record<string, string> = {
    "data-ctx-partner-id": "42",
    "data-ctx-partner-name": "محمد",
    "data-ctx-partner-kind": "customer",
  };
  assert.deepEqual(readPartnerContext((n) => attrs[n] ?? null), {
    id: "42",
    name: "محمد",
    kind: "customer",
  });
});

test("readPartnerContext يرفض السياق الناقص/غير الصالح", () => {
  assert.equal(readPartnerContext(() => null), null);
  assert.equal(
    readPartnerContext((n) => (n === "data-ctx-partner-id" ? "7" : null)),
    null,
  ); // نوع مفقود
  assert.equal(
    readPartnerContext((n) =>
      n === "data-ctx-partner-id" ? "7" : n === "data-ctx-partner-kind" ? "vendor" : null,
    ),
    null,
  ); // نوع غير معروف
});

test("readPartnerContext يتحمّل غياب الاسم", () => {
  const ctx = readPartnerContext((n) =>
    n === "data-ctx-partner-id" ? "9" : n === "data-ctx-partner-kind" ? "supplier" : null,
  );
  assert.deepEqual(ctx, { id: "9", name: "", kind: "supplier" });
});

test("readItemContext يقرأ سياق منتج صالح ويرفض الناقص", () => {
  const attrs: Record<string, string> = {
    "data-ctx-item-id": "500",
    "data-ctx-item-name": "إطار",
  };
  assert.deepEqual(readItemContext((n) => attrs[n] ?? null), { id: "500", name: "إطار" });
  assert.deepEqual(
    readItemContext((n) => (n === "data-ctx-item-id" ? "3" : null)),
    { id: "3", name: "" },
  );
  assert.equal(readItemContext(() => null), null);
});
