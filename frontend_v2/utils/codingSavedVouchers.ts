/**
 * بلاغ المالك: «لما بسجّل سند وبحطّ حفظ ما ببيّنو بنفس الصفحة — لازم أروح
 * أشوفهم بمكان تاني».
 *
 * الجذر: `handleSave` في شاشة الترميز الدفعي **يمسح الصفوف الناجحة من الشبكة**
 * ويكتفي بإشعارٍ عابر «تم حفظ ٣ سنداً». الإشعار يختفي بعد ثوانٍ، والشبكة تعود
 * فارغة — فلا أثر على الشاشة لما حُفظ: لا رقمُ سندٍ يُكتب على الورقة، ولا
 * تحقّقٌ من أن الحساب الذي اقترحه النظام هو ما أراده، ولا طريقٌ للتراجع عن
 * سطرٍ رُمِّز خطأً إلا مغادرةُ الشاشة.
 *
 * مسحُ الصفّ الناجح **صحيح** ويبقى: الشبكة قائمةُ عملٍ لِما لم يُحفظ بعد،
 * وبقاءُ المحفوظ فيها يدعو لحفظه مرّتين. الناقص كان سِجلَّ الجلسة بجانبها.
 *
 * المنطق هنا صرفٌ بلا React كي يُختبر وحده — نفس نهج `codingRowPaymentMethod.ts`.
 */
import type { VoucherBatchSaveRowResult } from "../types/accounting";

export type SavedVoucherDirection = "expense" | "revenue";

/** سندٌ حُفظ في هذه الجلسة — ما يكفي للتعرّف عليه وللتراجع عنه. */
export type SavedVoucher = {
  id: number;
  number: number | null;
  direction: SavedVoucherDirection;
  date: string;
  /** تسمية الحساب كما ظهرت في الصفّ — أو الاسم الحرّ الذي أنشأه الخادم. */
  accountLabel: string;
  partnerLabel: string;
  docNumber: string;
  amount: string;
  taxAmount: string;
  /** أُلغي ترحيله من هذا السِجلّ — يبقى ظاهراً مشطوباً لا يختفي. */
  undone: boolean;
};

/** ما تعرفه الشاشة عن الصفّ الذي أرسلته — يُدمج مع ما يعرفه الخادم. */
export type SubmittedRowFacts = {
  date: string;
  direction: SavedVoucherDirection;
  accountLabel: string;
  partnerLabel: string;
  docNumber: string;
  amount: string;
  taxAmount: string;
};

/**
 * يبني سطور السِجلّ من نتيجة الحفظ الدفعي.
 *
 * **الاتجاه من الخادم إن صرّح به، وإلا من الصفّ المُرسَل**: `direction` في ردّ
 * `batch-save` اختياريّ في العقد (`VoucherBatchSaveRowResult`)، وبناءُ زرّ
 * التراجع عليه وحده يعني استدعاء نقطة المصروف على سند إيراد حين يغيب —
 * والصفّ المُرسَل يعرف اتجاهه يقيناً لأنه هو من أرسله.
 *
 * الصفوف الفاشلة لا تدخل السِجلّ: مكانها الشبكة برسالة خطئها، وهي تبقى فيها.
 * وصفٌّ نجح بلا `id` يُهمَل كذلك — بلا معرّف لا تراجعَ ممكن، وسطرٌ لا يفعل
 * شيئاً أسوأ من غيابه.
 */
export function buildSavedVouchers(
  outcomes: readonly VoucherBatchSaveRowResult[],
  factsByOutcomeIndex: ReadonlyMap<number, SubmittedRowFacts>,
): SavedVoucher[] {
  const saved: SavedVoucher[] = [];
  for (const outcome of outcomes) {
    if (!outcome.success || outcome.id == null) continue;
    const facts = factsByOutcomeIndex.get(outcome.index);
    if (!facts) continue;
    const direction: SavedVoucherDirection =
      outcome.direction === "expense" || outcome.direction === "revenue"
        ? outcome.direction
        : facts.direction;
    saved.push({
      id: outcome.id,
      number: outcome.number ?? null,
      direction,
      date: facts.date,
      accountLabel: facts.accountLabel,
      partnerLabel: facts.partnerLabel,
      docNumber: facts.docNumber,
      amount: facts.amount,
      taxAmount: facts.taxAmount,
      undone: false,
    });
  }
  return saved;
}

/**
 * الأحدث أولاً، وحفظةٌ ثانية تُضاف فوق الأولى — السِجلّ يتراكم عبر الحفظات لا
 * يُستبدل: المحاسب يرمّز رزمةً على دفعات، وإخفاءُ الدفعة السابقة يعيد المشكلة.
 * ويُنقّى من المكرَّر بالمعرّف والاتجاه معاً (سند مصروف #7 وسند إيراد #7
 * رقمان مستقلّان في دفترين مختلفين).
 */
export function mergeSavedVouchers(
  previous: readonly SavedVoucher[],
  incoming: readonly SavedVoucher[],
): SavedVoucher[] {
  const merged = [...incoming, ...previous];
  const seen = new Set<string>();
  const unique: SavedVoucher[] = [];
  for (const voucher of merged) {
    const key = `${voucher.direction}:${voucher.id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(voucher);
  }
  return unique;
}

/** يشطب سطراً بعد إلغاء ترحيله — لا يحذفه: الاختفاء يُنسي المستخدمَ فعلَه. */
export function markVoucherUndone(
  list: readonly SavedVoucher[],
  direction: SavedVoucherDirection,
  id: number,
): SavedVoucher[] {
  return list.map((voucher) => (
    voucher.direction === direction && voucher.id === id
      ? { ...voucher, undone: true }
      : voucher
  ));
}

/** المجاميع تحت السِجلّ — المتراجَع عنه خارجها، فالرقم يقول ما استقرّ فعلاً. */
export function savedVouchersSummary(list: readonly SavedVoucher[]): {
  count: number;
  expense: number;
  revenue: number;
} {
  let expense = 0;
  let revenue = 0;
  let count = 0;
  for (const voucher of list) {
    if (voucher.undone) continue;
    count += 1;
    const amount = Number(voucher.amount) || 0;
    if (voucher.direction === "expense") expense += amount;
    else revenue += amount;
  }
  return { count, expense, revenue };
}
