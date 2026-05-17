/**
 * يطابق منطق recalculate_invoice_amounts في sales/services.py (نسبة خصم على مستوى الفاتورة).
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

export function computeInvoiceTotals(
  lines: LineInput[],
  taxRatePercentById: Map<number, number>,
  invoiceDiscount: string | number
): {
  subtotalExclTax: number;
  taxAmount: number;
  grandTotal: number;
  perLine: LineComputed[];
} {
  const rawNets: number[] = [];
  let sub = 0;
  for (const line of lines) {
    const n = round2(
      Number(line.quantity || 0) * Number(line.unit_price || 0) - Number(line.line_discount || 0)
    );
    rawNets.push(n);
    sub += n;
  }
  let disc = Number(invoiceDiscount || 0);
  if (sub > 0 && disc > sub) disc = sub;
  const ratio = sub > 0 ? (sub - disc) / sub : 0;
  const exclAfter = round2(sub - disc);

  let taxSum = 0;
  const perLine: LineComputed[] = [];
  for (let i = 0; i < lines.length; i++) {
    const adjNet = sub > 0 ? round2(rawNets[i] * ratio) : 0;
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
  taxSum = round2(taxSum);
  return {
    subtotalExclTax: exclAfter,
    taxAmount: taxSum,
    grandTotal: round2(exclAfter + taxSum),
    perLine,
  };
}
