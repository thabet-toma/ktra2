/**
 * توزيع السند على مستندات مفتوحة — طبقة نقيّة (بلا React) تُختبر بـNode.
 *
 * سند الصرف يُوزَّع على فواتير شراء **ومستحقّات لوجستية** (تخليص للمخلّص، شحن
 * لوكيل الشحن، إرسالية للناقل). المعرّف وحده لا يكفي مفتاحاً: تخليص #3 وفاتورة #3
 * مستندان مختلفان، فالمفتاح يحمل الصنف.
 */

export type AccrualKind = "clearance" | "freight" | "local";

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

export function docKey(doc: Pick<AllocatableDoc, "id" | "target">): string {
  return doc.target ? `${doc.target.kind}:${doc.target.id}` : `invoice:${doc.id}`;
}

const cents = (value: string | number | null | undefined): number =>
  Math.round((Number(value) || 0) * 100);

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
