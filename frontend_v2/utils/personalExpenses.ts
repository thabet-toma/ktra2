/**
 * مصاريف شخصية — منطق صرف (بلا React) تستهلكه شاشة «مصاريفي الشخصية».
 *
 * التنقّل بين الشهور والتحقق من المسودة منطقٌ يستحق اختباراً وحده؛ أما الجمع
 * والتصنيف فمن الخادم (hr.PersonalExpenseViewSet.summary) — مصدر حقيقة واحد.
 */
// متصفّح الشهور صار مشتركاً مع شاشة الرواتب — مصدره الآن `utils/monthKey`،
// ويُعاد تصديره هنا كي لا يتغيّر ما تستورده الشاشة.
// الامتداد صريح عمداً: `node --test` لا يحلّ الاستيراد بدونه.
export { monthKeyOf, shiftMonthKey, monthKeyLabel } from "./monthKey.ts";

export interface ExpenseDraft {
  date: string;
  title: string;
  amount: string;
}

/** رسالة الخطأ الأولى إن كانت المسودة غير صالحة، وإلا null. */
export function validateExpenseDraft(draft: ExpenseDraft): string | null {
  if (!draft.date) return "التاريخ مطلوب.";
  if (!draft.title.trim()) return "البيان مطلوب.";
  const amount = Number(draft.amount);
  if (!Number.isFinite(amount) || amount <= 0) return "المبلغ يجب أن يكون أكبر من صفر.";
  return null;
}
