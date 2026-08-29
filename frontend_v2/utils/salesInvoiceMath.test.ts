import assert from "node:assert/strict";
import test from "node:test";

import { computeInvoiceTotals } from "./salesInvoiceMath.ts";

const VAT16 = new Map([[1, 16]]);
const line = (price: number, tax: number | null = 1, qty = 1, disc = 0) => ({
  quantity: qty,
  unit_price: price,
  line_discount: disc,
  tax_rate_id: tax,
});

/** T-TAXINCL: أرقام القياس الحيّ — 99 «شامل الضريبة» كانت الواجهة تعرضها
 *  114.84 والخادم يخزّن 98.99، فتظهر «مدفوعة» ناقصةً بمتبقٍّ وهميّ 15.85. */
test("prices_include_tax divides like the server: 99 @16% → 85.34 + 13.65 = 98.99", () => {
  const t = computeInvoiceTotals([line(99)], VAT16, 0, { pricesIncludeTax: true });
  assert.equal(t.subtotalExclTax, 85.34);
  assert.equal(t.taxAmount, 13.65);
  assert.equal(t.grandTotal, 98.99);
  assert.equal(t.perLine[0].lineTotal, 98.99);
});

test("without the flag the old exclusive math is untouched", () => {
  const t = computeInvoiceTotals([line(100)], VAT16, 0);
  assert.equal(t.subtotalExclTax, 100);
  assert.equal(t.taxAmount, 16);
  assert.equal(t.grandTotal, 116);
});

test("discount_percent applies after the fixed discount, mirroring the server", () => {
  // 200 - 20 مقطوع = 180، ثم 10% = 162 صافياً + 25.92 ضريبة.
  const t = computeInvoiceTotals([line(200)], VAT16, 20, { discountPercent: 10 });
  assert.equal(t.subtotalExclTax, 162);
  assert.equal(t.taxAmount, 25.92);
  assert.equal(t.grandTotal, 187.92);
});

test("inclusive line without a tax rate keeps its price whole", () => {
  const t = computeInvoiceTotals([line(50, null)], VAT16, 0, { pricesIncludeTax: true });
  assert.equal(t.grandTotal, 50);
  assert.equal(t.taxAmount, 0);
});

test("header totals equal the sum of per-line rounded amounts", () => {
  // ثلاثة أسطر شاملة بأسعار تُنتج كسوراً — الترويسة مجموع الأسطر بالقرش.
  const lines = [line(33.33), line(66.67), line(9.99)];
  const t = computeInvoiceTotals(lines, VAT16, 0, { pricesIncludeTax: true });
  const excl = t.perLine.reduce((s, l) => s + l.lineNetAdjusted, 0);
  const tax = t.perLine.reduce((s, l) => s + l.lineTax, 0);
  assert.equal(t.subtotalExclTax, Math.round(excl * 100) / 100);
  assert.equal(t.taxAmount, Math.round(tax * 100) / 100);
  assert.equal(t.grandTotal, Math.round((excl + tax) * 100) / 100);
});
