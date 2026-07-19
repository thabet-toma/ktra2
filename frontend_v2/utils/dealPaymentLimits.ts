import type { Deal, DealPayment } from "@/types";

export function sumDealPaymentAmounts(
  payments: DealPayment[] | undefined
): number {
  return (payments || []).reduce((s, p) => s + Number(p.amount || 0), 0);
}

/**
 * يزيل تكرار صفوف الدفع غير المرحّلة لنفس (رقم القسط + المبلغ) قبل PATCH.
 * إن وُجد صف مرحّل في المجموعة يُبقى المرحّل ويُسقِط غير المرحّلة (نفس مبلغ القسط الأول مرتين).
 * يسمح لـ logistics serializer بحذف الصفوف غير الظاهرة في القائمة (غير المرحّلة فقط).
 */
export function dedupeDealPaymentsForPatch(
  list: DealPayment[] | undefined
): DealPayment[] {
  const arr = list || [];
  if (arr.length < 2) return arr;

  const keyOf = (p: DealPayment) =>
    `${Number(p.installmentNumber) || 0}:${amountCents(p.amount)}`;

  const unpostedProgressScore = (p: DealPayment): number => {
    let s = 0;
    if (p.confirmedBySupplier) s += 4;
    if (p.bankSwiftImage && String(p.bankSwiftImage).trim()) s += 3;
    if (p.alibabaClaimImage && String(p.alibabaClaimImage).trim()) s += 2;
    return s;
  };

  const numericId = (p: DealPayment) => {
    const s = String(p.id ?? "");
    if (/^\d+$/.test(s)) return Number(s);
    const m = /\d+/.exec(s);
    return m ? Number(m[0]) : 0;
  };

  const groups = new Map<string, DealPayment[]>();
  for (const p of arr) {
    const k = keyOf(p);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k)!.push(p);
  }

  const keep = new Set<string>();
  for (const group of groups.values()) {
    if (group.length === 1) {
      keep.add(String(group[0].id));
      continue;
    }
    const posted = group.filter((p) => p.isPosted);
    if (posted.length > 0) {
      for (const p of posted) keep.add(String(p.id));
      continue;
    }
    const sorted = [...group].sort((a, b) => {
      const d = unpostedProgressScore(b) - unpostedProgressScore(a);
      if (d !== 0) return d;
      return numericId(a) - numericId(b);
    });
    keep.add(String(sorted[0].id));
  }

  return arr.filter((p) => keep.has(String(p.id)));
}

function toleranceForCap(cap: number): number {
  return Math.max(0.01, Math.abs(Number(cap) || 0) * 1e-9);
}

/** أقصى مبلغ أساسي يُسمح به لدفعة جديدة أو بعد استثناء دفعة أثناء التعديل */
export function maxPaymentPrincipalForDeal(
  deal: Partial<Deal> | undefined,
  excludePaymentId?: string
): number {
  const cap = Number(deal?.totalAmount || 0);
  const sumOthers = (deal?.payments || [])
    .filter((p) =>
      excludePaymentId == null
        ? true
        : String(p.id) !== String(excludePaymentId)
    )
    .reduce((s, p) => s + Number(p.amount || 0), 0);
  return Math.max(0, cap - sumOthers);
}

function amountCents(x: unknown): number {
  return Math.round((Number(x) || 0) * 100);
}

function amountsClose(a: number, b: number): boolean {
  return Math.abs(a - b) < 0.051;
}

/** نفس الدفعات (حسب المعرف) وبنفس المبالغ — تسامح تقريب بسيط */
function paymentAmountsUnchangedById(
  previous: DealPayment[],
  next: DealPayment[]
): boolean {
  if (previous.length !== next.length) return false;
  const prevMap = new Map(
    previous.map((p) => [String(p.id), Number(p.amount || 0)])
  );
  if (prevMap.size !== previous.length) return false;
  for (const p of next) {
    const id = String(p.id);
    if (!prevMap.has(id)) return false;
    if (!amountsClose(prevMap.get(id)!, Number(p.amount || 0))) return false;
  }
  return true;
}

/** نفس عدد الدفعات ونفس المبالغ كمجموعة (عند اختلاف شكل المعرف tmp مقابل SQL) */
function paymentAmountMultisetUnchanged(
  previous: DealPayment[],
  next: DealPayment[]
): boolean {
  if (previous.length !== next.length) return false;
  const tally = (arr: DealPayment[]) => {
    const m = new Map<number, number>();
    for (const p of arr) {
      const k = amountCents(p.amount);
      m.set(k, (m.get(k) || 0) + 1);
    }
    return m;
  };
  const a = tally(previous);
  const b = tally(next);
  if (a.size !== b.size) return false;
  for (const [k, v] of a) {
    if (b.get(k) !== v) return false;
  }
  return true;
}

/**
 * يمنع زيادة المبالغ فوق إجمالي الصفقة.
 * إن وُجد تجاوز قديم في البيانات ولم تتغير مبالغ الدفعات (مثل تأكيد المورد فقط) يُسمح بالحفظ.
 */
export type DealPaymentAssertLabels = {
  /** مثل "الصفقة" (افتراضي) أو "الشحنة" */
  valueEntityLabel?: string;
};

export function assertDealPaymentsNotOverTotal(
  deal: Partial<Deal>,
  previousPayments?: DealPayment[] | null,
  labels?: DealPaymentAssertLabels
): void {
  const cap = Number(deal.totalAmount || 0);
  const next = deal.payments || [];
  const sum = sumDealPaymentAmounts(next);
  const tol = toleranceForCap(cap);
  if (sum <= cap + tol) return;

  if (
    previousPayments &&
    previousPayments.length > 0 &&
    (paymentAmountsUnchangedById(previousPayments, next) ||
      paymentAmountMultisetUnchanged(previousPayments, next))
  ) {
    return;
  }

  const entity = labels?.valueEntityLabel ?? "الصفقة";
  throw new Error(
    `مجموع الدفعات ($${sum.toLocaleString()}) يتجاوز قيمة ${entity} ($${cap.toLocaleString()}). احذف دفعة زائدة أو خفّض المبلغ.`
  );
}
