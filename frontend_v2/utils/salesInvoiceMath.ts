/**
 * يطابق منطق recalculate_invoice_amounts في sales/services/calc.py حرفياً.
 *
 * T-TAXINCL: المرآة كانت ناقصة فعلين يفعلهما الخادم — قسمة السعر الشامل على
 * (1 + النسبة)، وخصم النسبة `discount_percent` — فكانت فاتورة «شامل الضريبة»
 * تعرض 114.84 والخادم يخزّن 98.99، و«مدفوعة» تغطّي رقم الخادم فيبقى على
 * الشاشة «متبقٍّ» وهميّ يقرؤه المستخدم فشلاً.
 */

const round2 = (n: number) => Math.round(n * 100) / 100;

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
