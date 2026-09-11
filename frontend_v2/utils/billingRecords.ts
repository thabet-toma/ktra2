/**
 * دوالٌّ خالصةٌ لسجلّات الفوترة الشهرية (#207 م٨-ب).
 *
 * بلا شبكةٍ ولا متصفّح — تُختبَر بـ`node --test`، وهي بوّابةُ الواجهة الوحيدة هنا.
 * المبالغُ تصل نصوصاً عشريّةً ("290.00"): الجمعُ بتحويلها إلى سنتاتٍ صحيحة
 * ثمّ إعادتها كنصٍّ عشريٍّ بمنزلتين — منعاً لأخطاء الفاصلة العائمة (0.1 + 0.2 != 0.3).
 */

export interface BillingRecordFilterable {
  company_name?: string;
  invoice_number?: string | null;
}

/**
 * تحويل نصّ عشري إلى سنتات صحيحة بأمان.
 */
function parseDecimalToCents(value: string | null | undefined): bigint {
  if (!value) return 0n;
  const raw = String(value).trim();
  if (!raw) return 0n;

  const isNegative = raw.startsWith("-");
  const cleaned = isNegative ? raw.slice(1).trim() : raw;
  if (!cleaned) return 0n;

  const parts = cleaned.split(".");
  const wholeStr = parts[0].replace(/\D/g, "") || "0";
  let fracStr = (parts[1] || "").replace(/\D/g, "");

  if (fracStr.length === 0) {
    fracStr = "00";
  } else if (fracStr.length === 1) {
    fracStr = `${fracStr}0`;
  } else if (fracStr.length > 2) {
    fracStr = fracStr.slice(0, 2);
  }

  try {
    const cents = BigInt(wholeStr) * 100n + BigInt(fracStr);
    return isNegative ? -cents : cents;
  } catch {
    return 0n;
  }
}

/**
 * جمعُ مبالغ عشريّة نصوصاً عبر تحويلها لسنتات صحيحة ثمّ إعادتها كنصٍّ عشريٍّ ("123.45").
 */
export function sumDecimalAmounts(amounts: (string | null | undefined)[]): string {
  let totalCents = 0n;
  for (const amt of amounts) {
    totalCents += parseDecimalToCents(amt);
  }

  const isNegative = totalCents < 0n;
  const absCents = isNegative ? -totalCents : totalCents;
  const wholePart = absCents / 100n;
  const fracPart = absCents % 100n;
  const fracStr = fracPart < 10n ? `0${fracPart}` : `${fracPart}`;

  return `${isNegative ? "-" : ""}${wholePart}.${fracStr}`;
}

/**
 * تصفيةٌ محليّة لسجلّات الفوترة بالبحث في اسم الشركة أو رقم الفاتورة.
 */
export function filterBillingRecords<T extends BillingRecordFilterable>(
  records: T[],
  query: string,
): T[] {
  const q = (query || "").trim().toLowerCase();
  if (!q) return records;

  return records.filter((rec) => {
    const company = String(rec.company_name || "").toLowerCase();
    const invoice = String(rec.invoice_number || "").toLowerCase();
    return company.includes(q) || invoice.includes(q);
  });
}
