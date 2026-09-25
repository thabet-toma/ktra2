/**
 * توزيع السند على مستندات مفتوحة — طبقة نقيّة (بلا React) تُختبر بـNode.
 *
 * سند الصرف يُوزَّع على فواتير شراء **ومستحقّات لوجستية** (تخليص للمخلّص، شحن
 * لوكيل الشحن، إرسالية للناقل). المعرّف وحده لا يكفي مفتاحاً: تخليص #3 وفاتورة #3
 * مستندان مختلفان، فالمفتاح يحمل الصنف.
 */

export type AccrualKind = "clearance" | "freight" | "local";

const cents = (value: string | number | null | undefined): number =>
  Math.round((Number(value) || 0) * 100);

/** مستند مفتوح قابل لاستقبال التوزيع. */
export type AllocatableDoc = {
  id: number;
  label: string;
  /** المتبقّي على المستند (نص أو رقم). */
  remaining: string | number;
  /** تاريخ الاستحقاق — ترتيب FIFO (الأقدم أولاً). */
  date?: string | null;
  /** مستحقٌّ لوجستي؛ غيابه = فاتورة (شراء أو بيع). */
  target?: { kind: AccrualKind; id: number };
};

/** حالة مستحقٍّ لوجستي — من `supplier-payments/accrual-status/`. */
export type AccrualStatus = {
  kind: AccrualKind;
  id: number;
  label: string;
  accrual_posted: boolean;
  due: string;
  paid: string;
  allocated: string;
  remaining: string;
  overpaid: string;
};

/**
 * ما سيُفصل «دفعة تحت الحساب» من دفعةٍ على مستحقّ — مرآة `split_incoming` في
 * الخادم (`logistics/domain/overpayment_split.py`). صفرٌ إن لم يُرحَّل الاستحقاق:
 * الدفعة المقدّمة قبل الإفراج تبقى على مستندها.
 */
export function overpaymentExcess(
  amount: string | number,
  status: Pick<AccrualStatus, "accrual_posted" | "remaining">,
): number {
  if (!status.accrual_posted) return 0;
  const excess = cents(amount) - cents(status.remaining);
  return excess > 0 ? excess / 100 : 0;
}

/** أرقام المستند كما يرسلها مسلسله (`party_accruals.document_settlement`). */
export type ServerSettlement = {
  amount_paid?: string | number | null;
  remaining_balance?: string | number | null;
  advance_balance?: string | number | null;
};

/**
 * المدفوع/المتبقّي/المقدَّم لمستحقٍّ في الشاشة. بعد ترحيل الاستحقاق أرقامُ الخادم —
 * القيود ومعها سندات الصرف الموزَّعة، وهي ما يفصل به الزائد. قبله لا قيد يُقرأ،
 * فالتقدير من النموذج نفسه (بنودٌ قد لا تكون حُفظت بعد) ناقص دفعاته.
 */
export function docSettlement(
  accrualPosted: boolean,
  server: ServerSettlement | null | undefined,
  draft: { due: number; paid: number },
): { paid: number; remaining: number; advance: number } {
  if (accrualPosted && server) {
    return {
      paid: cents(server.amount_paid) / 100,
      remaining: cents(server.remaining_balance) / 100,
      advance: cents(server.advance_balance) / 100,
    };
  }
  const due = cents(draft.due);
  const paid = cents(draft.paid);
  return { paid: paid / 100, remaining: Math.max(0, due - paid) / 100, advance: Math.max(0, paid - due) / 100 };
}

export function docKey(doc: Pick<AllocatableDoc, "id" | "target">): string {
  return doc.target ? `${doc.target.kind}:${doc.target.id}` : `invoice:${doc.id}`;
}

/**
 * يملأ المبلغ المتاح على المستندات من الأقدم استحقاقاً — «توزيع تلقائي». المستند
 * بلا تاريخ يأتي أخيراً، والتعادل يحفظ ترتيب القائمة. الحساب بالأغورات فلا
 * يتسرّب كسرٌ عشري.
 */
export function fifoFill(
  docs: AllocatableDoc[],
  available: number,
): Array<{ doc: AllocatableDoc; amount: string }> {
  const ordered = docs
    .map((doc, index) => ({ doc, index }))
    .sort((a, b) => {
      const da = a.doc.date || "9999-12-31";
      const db = b.doc.date || "9999-12-31";
      return da === db ? a.index - b.index : da < db ? -1 : 1;
    });
  let left = cents(available);
  const out: Array<{ doc: AllocatableDoc; amount: string }> = [];
  for (const { doc } of ordered) {
    if (left <= 0) break;
    const take = Math.min(cents(doc.remaining), left);
    if (take <= 0) continue;
    out.push({ doc, amount: (take / 100).toFixed(2) });
    left -= take;
  }
  return out;
}
