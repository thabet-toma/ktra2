/**
 * يطابق منطق recalculate_invoice_amounts في sales/services/calc.py حرفياً.
 *
 * T-TAXINCL: المرآة كانت ناقصة فعلين يفعلهما الخادم — قسمة السعر الشامل على
 * (1 + النسبة)، وخصم النسبة `discount_percent` — فكانت فاتورة «شامل الضريبة»
 * تعرض 114.84 والخادم يخزّن 98.99، و«مدفوعة» تغطّي رقم الخادم فيبقى على
 * الشاشة «متبقٍّ» وهميّ يقرؤه المستخدم فشلاً.
 */

import { isFixedSnapshotMethod, round2 } from "./cogsCostMethod.ts";

export type LineInput = {
  quantity: string | number;
  unit_price: string | number;
  line_discount: string | number;
  tax_rate_id: number | null;
};

export type LineComputed = {
  lineNetRaw: number;
  lineNetAdjusted: number;
  lineTax: number;
  lineTotal: number;
};

export type InvoiceTotalsOptions = {
  /** «شامل الضريبة» — السعر المُدخل يحوي الضريبة فيُستخرج الصافي بالقسمة. */
  pricesIncludeTax?: boolean;
  /** خصم نسبي على مستوى الفاتورة — يُطبَّق بعد الخصم المقطوع كما في الخادم. */
  discountPercent?: string | number;
};

export function computeInvoiceTotals(
  lines: LineInput[],
  taxRatePercentById: Map<number, number>,
  invoiceDiscount: string | number,
  opts?: InvoiceTotalsOptions
): {
  subtotalExclTax: number;
  taxAmount: number;
  grandTotal: number;
  perLine: LineComputed[];
} {
  const inclusive = Boolean(opts?.pricesIncludeTax);
  const rawNets: number[] = [];
  let sub = 0;
  for (const line of lines) {
    let n = round2(
      Number(line.quantity || 0) * Number(line.unit_price || 0) - Number(line.line_discount || 0)
    );
    // الخادم يقسم متى وُجد سطرُ ضريبة على البند — ولو كانت نسبته صفراً.
    if (inclusive && line.tax_rate_id != null) {
      const pct = taxRatePercentById.get(line.tax_rate_id) ?? 0;
      n = round2(n / (1 + pct / 100));
    }
    rawNets.push(n);
    sub += n;
  }
  let disc = Number(invoiceDiscount || 0);
  if (sub > 0 && disc > sub) disc = sub;
  let pctDisc = Number(opts?.discountPercent || 0);
  if (pctDisc < 0) pctDisc = 0;
  if (pctDisc > 100) pctDisc = 100;
  const effective = sub > 0 ? ((sub - disc) * (100 - pctDisc)) / 100 : 0;
  const ratio = sub > 0 ? effective / sub : 0;

  // الترويسة مجموعُ الأسطر بالقرش — كما يفعل الخادم، فلا انحراف تقريب بينهما.
  let exclSum = 0;
  let taxSum = 0;
  const perLine: LineComputed[] = [];
  for (let i = 0; i < lines.length; i++) {
    const adjNet = sub > 0 ? round2(rawNets[i] * ratio) : 0;
    exclSum += adjNet;
    const tid = lines[i].tax_rate_id;
    const pct = tid != null ? taxRatePercentById.get(tid) ?? 0 : 0;
    const lineTax = round2(adjNet * (pct / 100));
    taxSum += lineTax;
    perLine.push({
      lineNetRaw: rawNets[i],
      lineNetAdjusted: adjNet,
      lineTax,
      lineTotal: round2(adjNet + lineTax),
    });
  }
  exclSum = round2(exclSum);
  taxSum = round2(taxSum);
  return {
    subtotalExclTax: exclSum,
    taxAmount: taxSum,
    grandTotal: round2(exclSum + taxSum),
    perLine,
  };
}

export type ExpectedCostProduct = {
  avg_cost?: string | number | null;
  cogs_method_unit_cost?: string | number | null;
  is_service?: boolean;
};

/**
 * التكلفة المتوقَّعة للوحدة في محرّر الفاتورة — مرآة `_loss_lines` في
 * `sales/services/calc.py` حرفياً:
 * لـ `standard`/`last_purchase` ومع وجود `cogs_method_unit_cost` غير فارغ
 * يُعاد هذا الرقم (بما في ذلك الصفر الصريح)، وإلا السقوط إلى `avg_cost`
 * (أو 0 عند غيابه).
 */
export function expectedUnitCost(
  product: ExpectedCostProduct | null | undefined,
  method?: string | null,
): number {
  if (!product) return 0;
  if (
    isFixedSnapshotMethod(method)
    && product.cogs_method_unit_cost != null
    && product.cogs_method_unit_cost !== ""
  ) {
    const n = Number(product.cogs_method_unit_cost);
    if (Number.isFinite(n)) return n;
  }
  const avg = Number(product.avg_cost ?? 0);
  return Number.isFinite(avg) ? avg : 0;
}

/**
 * قاعدة واحدة لتكلفة الوحدة المتوقَّعة على سطر الفاتورة: المرتجع والخدمة يقارَنان
 * بمتوسط التكلفة (سلوك ما قبل M2)، وغيرهما بتكلفة الطريقة (`expectedUnitCost`).
 */
export function lineExpectedUnitCost(
  product: ExpectedCostProduct | null | undefined,
  method: string | null | undefined,
  isReturn: boolean,
): number {
  if (!product) return 0;
  if (isReturn || product.is_service) {
    const avg = Number(product.avg_cost ?? 0);
    return Number.isFinite(avg) ? avg : 0;
  }
  return expectedUnitCost(product, method);
}

/**
 * حالة §3.3 (منتج مخزني في `standard`/`last_purchase` بلا سعر ثابت ولا شراء
 * سابق): يُقيَّد بالتكلفة الفعلية بلا فرق مع تنبيه غير حاجب في معاينة القيد.
 */
export function missingMethodCost(
  product: ExpectedCostProduct | null | undefined,
  method?: string | null,
): boolean {
  if (!product || product.is_service) return false;
  if (!isFixedSnapshotMethod(method)) return false;
  return product.cogs_method_unit_cost == null || product.cogs_method_unit_cost === "";
}

export type EstimateInvoiceCogsLine = {
  product: ExpectedCostProduct | null | undefined;
  qty: number;
};

export type InvoiceCogsEstimate = {
  cogsTotal: number;
  invTotal: number;
  hasFixedMethodLine: boolean;
  variance: number;
};

/**
 * تقدير تكلفة المبيعات ودائن المخزون والفروقات لمعاينة قيد فاتورة البيع.
 * على المرتجع أو غير الطرق الثابتة أو الخدمات أو غياب كلفة الطريقة تُستخدَم
 * التكلفة الفعلية التقديرية (`avg_cost`) بلا فرق.
 */
export function estimateInvoiceCogs(
  lines: readonly EstimateInvoiceCogsLine[],
  method: string | null | undefined,
  isReturn: boolean,
): InvoiceCogsEstimate {
  let cogsTotal = 0;
  let invTotal = 0;
  let hasFixedMethodLine = false;
  for (const { product: p, qty } of lines) {
    if (!p || qty <= 0) continue;
    const actualEst = Math.max(0, Number(p.avg_cost || 0));
    const hasMethodCost =
      !isReturn &&
      isFixedSnapshotMethod(method) &&
      !p.is_service &&
      !missingMethodCost(p, method);
    if (hasMethodCost) hasFixedMethodLine = true;
    const unitCogs = hasMethodCost
      ? Math.max(0, expectedUnitCost(p, method))
      : actualEst;
    cogsTotal += unitCogs * qty;
    invTotal += actualEst * qty;
  }
  return {
    cogsTotal,
    invTotal,
    hasFixedMethodLine,
    variance: invTotal - cogsTotal,
  };
}
