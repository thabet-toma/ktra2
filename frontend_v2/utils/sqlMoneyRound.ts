/** مطابقة Django Decimal(18,2) — منع رفض الحفظ بسبب 3+ منازل عشرية */
export function roundSqlMoney2(n: unknown): number {
  const x = Number(n);
  if (!Number.isFinite(x)) return 0;
  return Number.parseFloat(x.toFixed(2));
}

/** مطابقة Decimal(18,4) للكميات وأسعار الوحدة */
export function roundSqlMoney4(n: unknown): number {
  const x = Number(n);
  if (!Number.isFinite(x)) return 0;
  return Number.parseFloat(x.toFixed(4));
}

/**
 * نسبة ض.ق.م في الواجهة: تحويل "16.0000" أو Decimal طويل إلى رقم 16 (لا يغيّر 16.25).
 * الحفظ ما زال يستخدم roundSqlMoney4 لحدود SQL.
 */
export function normalizeTaxRatePercent(v: unknown): number {
  const x = Number(v);
  if (!Number.isFinite(x)) return 0;
  return Number.parseFloat(x.toFixed(4));
}

/** نص الملخص/الطباعة: 16 أو 16.5 بدون أصفار زائدة */
export function formatTaxPercentLabel(v: unknown): string {
  const n = normalizeTaxRatePercent(v);
  if (Number.isInteger(n)) return String(Math.trunc(n));
  return String(n);
}
