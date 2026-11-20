import assert from "node:assert/strict";
import test from "node:test";

import {
  computeInvoiceTotals,
  estimateInvoiceCogs,
  expectedUnitCost,
  lineExpectedUnitCost,
  missingMethodCost,
} from "./salesInvoiceMath.ts";

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

test("expectedUnitCost uses method cost for standard/last_purchase and falls back to avg_cost", () => {
  assert.equal(
    expectedUnitCost({ avg_cost: "10.00", cogs_method_unit_cost: "11.0000" }, "fifo"),
    10,
  );
  assert.equal(
    expectedUnitCost({ avg_cost: "10.00", cogs_method_unit_cost: 11 }, "standard"),
    11,
  );
  assert.equal(
    expectedUnitCost({ avg_cost: "10.00", cogs_method_unit_cost: null }, "standard"),
    10,
  );
  assert.equal(
    expectedUnitCost({ avg_cost: "10.00", cogs_method_unit_cost: "16.0000" }, "last_purchase"),
    16,
  );
  assert.equal(
    expectedUnitCost({ avg_cost: "10.00", cogs_method_unit_cost: "0.0000" }, "standard"),
    0,
  );
  assert.equal(
    expectedUnitCost({ avg_cost: "10.00", cogs_method_unit_cost: 0 }, "last_purchase"),
    0,
  );
  assert.equal(
    expectedUnitCost({ avg_cost: null, cogs_method_unit_cost: null }, "fifo"),
    0,
  );
});

test("lineExpectedUnitCost: returns and services use avg_cost, stock sales use the method cost", () => {
  const withMethod = { avg_cost: "10.00", cogs_method_unit_cost: "11.0000" };
  // مرتجع: متوسط التكلفة ولو وُجدت كلفة الطريقة (سلوك ما قبل M2)
  assert.equal(lineExpectedUnitCost(withMethod, "standard", true), 10);
  // خدمة: متوسط التكلفة لا كلفة الطريقة
  assert.equal(lineExpectedUnitCost({ ...withMethod, is_service: true }, "standard", false), 10);
  // بيع مخزني بكلفة طريقة
  assert.equal(lineExpectedUnitCost(withMethod, "standard", false), 11);
  // بيع مخزني بلا كلفة طريقة: السقوط إلى avg_cost
  assert.equal(
    lineExpectedUnitCost({ avg_cost: "10.00", cogs_method_unit_cost: null }, "standard", false),
    10,
  );
  assert.equal(lineExpectedUnitCost(null, "standard", false), 0);
  assert.equal(lineExpectedUnitCost(undefined, "standard", true), 0);
});

test("missingMethodCost flags stock products missing method cost in standard/last_purchase only", () => {
  assert.equal(
    missingMethodCost({ is_service: false, cogs_method_unit_cost: null }, "standard"),
    true,
  );
  assert.equal(
    missingMethodCost({ is_service: false, cogs_method_unit_cost: null }, "last_purchase"),
    true,
  );
  assert.equal(
    missingMethodCost({ is_service: false, cogs_method_unit_cost: "0.0000" }, "standard"),
    false,
  );
  assert.equal(
    missingMethodCost({ is_service: false, cogs_method_unit_cost: "16.0000" }, "last_purchase"),
    false,
  );
  assert.equal(
    missingMethodCost({ is_service: false, cogs_method_unit_cost: null }, "fifo"),
    false,
  );
  assert.equal(
    missingMethodCost({ is_service: true, cogs_method_unit_cost: null }, "standard"),
    false,
  );
});

test("estimateInvoiceCogs computes cogsTotal, invTotal, variance, and fallbacks", () => {
  const stockLowStd = { is_service: false, avg_cost: "15", cogs_method_unit_cost: "11" };
  const stockHighLast = { is_service: false, avg_cost: "12", cogs_method_unit_cost: "16" };
  const serviceProd = { is_service: true, avg_cost: "5", cogs_method_unit_cost: "99" };
  const missingProd = { is_service: false, avg_cost: "8", cogs_method_unit_cost: null };

  // 1) standard with method cost below avg:
  //    qty 4: cogs = 4 * 11 = 44, inv = 4 * 15 = 60, variance = 60 - 44 = +16 (debit)
  assert.deepEqual(
    estimateInvoiceCogs([{ product: stockLowStd, qty: 4 }], "standard", false),
    { cogsTotal: 44, invTotal: 60, hasFixedMethodLine: true, variance: 16 },
  );

  // 2) last_purchase above avg:
  //    qty 3: cogs = 3 * 16 = 48, inv = 3 * 12 = 36, variance = 36 - 48 = -12 (credit)
  assert.deepEqual(
    estimateInvoiceCogs([{ product: stockHighLast, qty: 3 }], "last_purchase", false),
    { cogsTotal: 48, invTotal: 36, hasFixedMethodLine: true, variance: -12 },
  );

  // 3) return invoice -> no fixed line, cogsTotal = invTotal = 4 * 15 = 60, variance = 0
  assert.deepEqual(
    estimateInvoiceCogs([{ product: stockLowStd, qty: 4 }], "standard", true),
    { cogsTotal: 60, invTotal: 60, hasFixedMethodLine: false, variance: 0 },
  );

  // 4) service line and missing-cost line fall back to avg (no fixed line):
  //    service: 2 * 5 = 10, missing: 5 * 8 = 40 -> total = 50, invTotal = 50, variance = 0
  //    zero/negative qty and null product are skipped
  assert.deepEqual(
    estimateInvoiceCogs(
      [
        { product: serviceProd, qty: 2 },
        { product: missingProd, qty: 5 },
        { product: stockLowStd, qty: 0 },
        { product: null, qty: 3 },
      ],
      "standard",
      false,
    ),
    { cogsTotal: 50, invTotal: 50, hasFixedMethodLine: false, variance: 0 },
  );

  // 5) fifo -> no fixed line, uses avg:
  //    qty 4: cogs = 4 * 15 = 60, inv = 60, variance = 0
  assert.deepEqual(
    estimateInvoiceCogs([{ product: stockLowStd, qty: 4 }], "fifo", false),
    { cogsTotal: 60, invTotal: 60, hasFixedMethodLine: false, variance: 0 },
  );
});
