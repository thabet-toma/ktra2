/**
 * T-JQE (issue #133) — شريط القيد السريع بثلاث خانات في الوضع البسيط لقيد
 * المحاسبة اليدوي: مقبوضات · مدفوعات · عمليات ذمم، بدل خانة «المبلغ» الواحدة.
 *
 * القرار (مبتوت، لا يُعاد فتحه):
 *   مقبوضات    → تقترح المدين  = الصندوق الافتراضي
 *   مدفوعات    → تقترح الدائن  = الصندوق الافتراضي
 *   عمليات ذمم → طرفٌ لطرف، بلا صندوق وبلا اقتراح على أيّ جهة
 *
 * التمانع المتبادل: رقمٌ في خانة يُفرغ الخانتين الأخريين — لا قيدَ يزعم قبضاً
 * ودفعاً معاً. الاقتراح يُكتب في الحقل فعلاً لا كتلميح عائم، وحين يغيّر
 * المستخدم حساباً مُقترَحاً بيده لا يعود المبلغ التالي يدهسه — هذا ما يحمله
 * `touched` (حالة، لا مرجعاً يُقرأ داخل effect، كي لا يضيع تعديل مستخدمٍ عدّل
 * ثم غادر). بلا صندوق افتراضي مُعرَّف في إعدادات الشركة: الخانات الثلاث تبقى
 * تعمل بلا اقتراح، والجهتان تُختاران يدوياً — إخفاء الحقل لغياب إعداد هو
 * بالضبط كيف تُصدَّق ميزةٌ أنها غير موجودة.
 *
 * وحدة نقيّة (بلا تنسيق أرقام ولا حالة React) كي تُختبر بـ`node --test` —
 * تنسيق العرض عبر `formatNumber` في المكوّن وحده (قاعدة G1).
 */

export type QuickEntryKind = "receipts" | "payments" | "receivable";

export type QuickEntryAmounts = {
  receipts: string;
  payments: string;
  receivable: string;
};

export const emptyQuickEntryAmounts = (): QuickEntryAmounts => ({
  receipts: "",
  payments: "",
  receivable: "",
});

/**
 * كتابة رقم في خانة تُفرغ الخانتين الأخريين فوراً — لا قيدَ واحد يُدخَل من
 * خانتين معاً.
 */
export function applyQuickEntryAmount(
  prev: QuickEntryAmounts,
  kind: QuickEntryKind,
  value: string,
): QuickEntryAmounts {
  const next = emptyQuickEntryAmounts();
  next[kind] = value;
  return next;
}

/** أيّ جهة (مدين/دائن) عدّلها المستخدم بيده — فلا يعود الاقتراح التلقائي يدهسها. */
export type QuickEntryTouched = {
  debit: boolean;
  credit: boolean;
};

export const noQuickEntryTouch = (): QuickEntryTouched => ({
  debit: false,
  credit: false,
});

export type QuickEntrySides = {
  debitAccountId: number | null;
  creditAccountId: number | null;
};

/**
 * الاقتراح المحاسبي لخانة القيد السريع. `current` هو الجهتان الحاليّتان
 * (تُحفظان كما هما إن لم يكن ثمّة اقتراح جديد)، و`touched` يمنع الاقتراح من
 * الكتابة فوق جهةٍ عدّلها المستخدم بيده — لا مبلغَ صفراً أو سالباً يُقترَح له
 * شيء، ولا صندوقاً غائباً (`null`) يُستنتج من الشجرة بديلاً عنه.
 *
 * `previousKind` — التبديل بين الخانات (مثلاً مقبوضات ثم مدفوعات) لا يكتفي
 * بإفراغ نصوص المبالغ الثلاثة (`applyQuickEntryAmount`)؛ الجهة التي اقترحتها
 * الخانة السابقة **تُعاد إلى بلا حساب أوّلاً** ما لم يكن المستخدم قد لمسها —
 * وإلا بقي صندوقٌ واحد على الجهتين معاً (مقبوضات ثم مدفوعات)، أو صندوقٌ يتيّم
 * «عمليات ذمم» التي يجب ألّا تحمل صندوقاً على أيّ جهة إطلاقاً. اللمس يبقى
 * أقوى من التراجع كما هو أقوى من الاقتراح: جهةٌ لمسها المستخدم لا يمسّها هذا
 * التراجع، تماماً كما لا يمسّها الاقتراح الجديد.
 */
export function suggestQuickEntrySides(params: {
  kind: QuickEntryKind;
  /** الخانة التي كانت نشطة قبل هذه الكتابة — `null` إن لم تكن هناك خانة سابقة بعد. */
  previousKind: QuickEntryKind | null;
  amount: number;
  defaultCashAccountId: number | null;
  touched: QuickEntryTouched;
  current: QuickEntrySides;
}): QuickEntrySides {
  const { kind, previousKind, amount, defaultCashAccountId, touched, current } = params;

  // التراجع: الخانة تبدّلت — أيّ جهةٍ اقترحتها الخانة *السابقة* ولم يلمسها
  // المستخدم تعود بلا حساب، بصرف النظر عن قيمة المبلغ الحالي.
  let next = current;
  if (previousKind != null && previousKind !== kind) {
    if (previousKind === "receipts" && !touched.debit) {
      next = { ...next, debitAccountId: null };
    } else if (previousKind === "payments" && !touched.credit) {
      next = { ...next, creditAccountId: null };
    }
  }

  if (!(amount > 0)) return next;
  if (kind === "receivable" || defaultCashAccountId == null) return next;

  if (kind === "receipts") {
    if (touched.debit) return next;
    return { ...next, debitAccountId: defaultCashAccountId };
  }

  // payments
  if (touched.credit) return next;
  return { ...next, creditAccountId: defaultCashAccountId };
}
