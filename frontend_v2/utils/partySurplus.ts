/**
 * فائض الطرف «تحت الحساب» واستردادُه نقداً — طبقة نقيّة (بلا React) تُختبر بـNode.
 *
 * الفائض (`partners/{id}/surplus/` — `sales/services/party_surplus.py`) مصدرٌ مصدراً:
 * سند صرفٍ أو إشعارٌ مدين للدائن، سند قبضٍ أو إشعارٌ دائن للعميل. نافذة الاسترداد
 * تختار ما يُطفئه السند منها؛ والمبالغ بعملة المصدر = عملة السند.
 */

export type SurplusSource = "note" | "supplier_payment" | "customer_payment";

export type SurplusRow = {
  source: SurplusSource;
  id: number;
  label: string;
  date: string | null;
  amount: string;
  unallocated: string;
  currency: number | null;
  currency_code: string | null;
  exchange_rate: string;
};

/** مبلغٌ مختارٌ لكل مصدر — المفتاح `surplusKey`. */
export type RefundPicks = Record<string, string>;

const cents = (value: string | number | null | undefined): number =>
  Math.round((Number(value) || 0) * 100);

export const surplusKey = (row: Pick<SurplusRow, "source" | "id">): string => `${row.source}:${row.id}`;

/** مصدرٌ يُستردّ بسندٍ بهذه العملة — عملة المصدر نفسها وحدها. */
export const isEligible = (row: SurplusRow, currencyId: number | "" | null | undefined): boolean =>
  currencyId === "" || currencyId == null ? true : row.currency === currencyId;

/** مجموع المختار من المصادر المؤهَّلة وحدها. */
export function pickedTotal(rows: SurplusRow[], picks: RefundPicks, currencyId?: number | "" | null): number {
  return rows
    .filter((row) => isEligible(row, currencyId))
    .reduce((sum, row) => sum + cents(picks[surplusKey(row)]), 0) / 100;
}

/** مجموع الفائض المؤهَّل — ما يُعرض أعلى النافذة ويُقترح مبلغاً للسند. */
export function eligibleTotal(rows: SurplusRow[], currencyId?: number | "" | null): number {
  return rows.filter((row) => isEligible(row, currencyId)).reduce((sum, row) => sum + cents(row.unallocated), 0) / 100;
}

/**
 * يوزّع مبلغ السند على المصادر المؤهَّلة من الأقدم — «ملء تلقائي». لا يتجاوز مصدرٌ فائضه،
 * والمصدر بلا تاريخ أخيراً. بالأغورات فلا يتسرّب كسر.
 */
export function fillRefundPicks(rows: SurplusRow[], amount: number, currencyId?: number | "" | null): RefundPicks {
  let left = cents(amount);
  const out: RefundPicks = {};
  const ordered = rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => isEligible(row, currencyId))
    .sort((a, b) => {
      const da = a.row.date || "9999-12-31";
      const db = b.row.date || "9999-12-31";
      return da === db ? a.index - b.index : da < db ? -1 : 1;
    });
  for (const { row } of ordered) {
    if (left <= 0) break;
    const take = Math.min(cents(row.unallocated), left);
    if (take > 0) {
      out[surplusKey(row)] = (take / 100).toFixed(2);
      left -= take;
    }
  }
  return out;
}

/** حمولة `refund_sources` لإنشاء السند — المصادر المؤهَّلة بمبلغٍ موجبٍ وحدها. */
export function refundSourcesPayload(
  rows: SurplusRow[],
  picks: RefundPicks,
  currencyId?: number | "" | null,
): Array<{ source: SurplusSource; id: number; amount: string }> {
  return rows
    .filter((row) => isEligible(row, currencyId) && cents(picks[surplusKey(row)]) > 0)
    .map((row) => ({ source: row.source, id: row.id, amount: (cents(picks[surplusKey(row)]) / 100).toFixed(2) }));
}

/** سببُ رفض الاختيار قبل الإرسال، أو `null` — مصدرٌ فوق فائضه، أو المجموع فوق مبلغ السند. */
export function refundPicksError(
  rows: SurplusRow[],
  picks: RefundPicks,
  voucherAmount: number,
  currencyId?: number | "" | null,
): string | null {
  for (const row of rows) {
    if (!isEligible(row, currencyId)) continue;
    if (cents(picks[surplusKey(row)]) > cents(row.unallocated)) {
      return `المسترَدّ من ${row.label} يتجاوز فائضه`;
    }
  }
  if (cents(pickedTotal(rows, picks, currencyId)) > cents(voucherAmount)) {
    return "مجموع ما يُطفئه السند من الفائض يتجاوز مبلغه";
  }
  return null;
}

/** مستندٌ تحت إحدى خانتَي رأس كشف الدائن (`party_accruals.party_on_account_summary`). */
export type BucketItem = {
  source: "voucher" | "note" | "clearance" | "freight" | "local";
  id: number;
  label: string;
  date: string | null;
  /** ما يخصّ هذه الخانة منه — بعملته (`currency_code`)، أو بالأساس للمستحقّ. */
  amount: string;
  currency_code: string | null;
  base: string;
  shipment_id?: number | null;
};

/** تبويب ملف الاستيراد الذي يعرض المستحقّ اللوجستي. */
const ACCRUAL_TAB: Record<string, string> = { clearance: "clearance", local: "local", freight: "deals" };

/** مسار فتح مستند الخانة — السند والإشعار بشاشتيهما، والمستحقّ بتبويبه في ملف شحنته. */
export function bucketItemPath(item: Pick<BucketItem, "source" | "id" | "shipment_id">): string | null {
  if (item.source === "voucher") return `/supplier-payments?payment_id=${item.id}`;
  if (item.source === "note") return `/accounting/credit-debit-notes?note_id=${item.id}`;
  if (!item.shipment_id) return null;
  return `/import-flow/${item.shipment_id}?tab=${ACCRUAL_TAB[item.source]}`;
}
