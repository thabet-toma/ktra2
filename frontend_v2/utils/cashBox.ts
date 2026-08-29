/** T-CASHBOX — اختيار صندوق الدفع في الواجهة: مصدرٌ واحد لكل الشاشات.
 *
 * كانت كل شاشة تحلّ الصندوق بطريقتها، وأسوأها «أوّل حساب نقدي في الشجرة»
 * (`allAccounts.find(...)`): الحسابات تصل مرتَّبةً بالكود، فالأقلّ كوداً يفوز
 * دائماً — وهو صندوق الشيقل. من هنا جاءت شكوى «الدفع للمشتريات دائماً من صندوق
 * الشيقل»: القيمة تُملأ تلقائياً ثم تُرسَل، فتبدو اختياراً مقصوداً من المستخدم.
 *
 * القاعدة الآن: **ترتيبُ الشجرة ليس نيّةَ مستخدم**. السلّم:
 *   إعداد الشركة ← صندوق المستخدم الافتراضي ← صندوق مطابق للعملة ←
 *   افتراضي الشركة ← لا شيء (يحلّه الخادم بسلّمه نفسه).
 *
 * الرجوع بـ`null` مقصود: الخادم (`accounting/services.py` (`resolve_cash_account`))
 * يحلّ الفارغ بالسلّم ذاته ويرمي خطأً إرشادياً إن عجز — أفضل من تخمينٍ صامت.
 */
import type { CashBoxLedgerLink } from "../services/accountingApi";

export type CashAccountPick = {
  /** معرّف الحساب في شجرة الحسابات — هو ما تُرسله المستندات. */
  accountId: number | null;
  /** الصندوق الذي وقع عليه الاختيار، إن كان صندوقاً مسجَّلاً. */
  box: CashBoxLedgerLink | null;
  /** سبب الاختيار — للعرض والتشخيص، لا لمنطقٍ يُبنى عليه. */
  source: "settings" | "user-default" | "currency" | "company-default" | "none";
};

const sameCurrency = (box: CashBoxLedgerLink, currency?: string | null) =>
  !currency || (box.currency_code || "").toUpperCase() === currency.toUpperCase();

export const activeBoxes = (boxes: CashBoxLedgerLink[] | null | undefined) =>
  (boxes ?? []).filter((b) => b.is_active !== false);

/** الصناديق الصالحة لمستندٍ بعملةٍ ما — بلا عملة تُعاد كلها. */
export function boxesForCurrency(
  boxes: CashBoxLedgerLink[] | null | undefined,
  currency?: string | null,
): CashBoxLedgerLink[] {
  const live = activeBoxes(boxes);
  if (!currency) return live;
  const matching = live.filter((b) => sameCurrency(b, currency));
  // بلا صندوقٍ بالعملة لا تُفرَّغ القائمة: المستخدم قد يقصد الدفع بصندوقٍ آخر
  // ويتحمّل التحويل — الخادم هو من يحرس صناديق FIFO.
  return matching.length > 0 ? matching : live;
}

export function pickDefaultCashAccount(opts: {
  boxes: CashBoxLedgerLink[] | null | undefined;
  currency?: string | null;
  /** الصندوق الافتراضي من إعدادات المبيعات/المشتريات (معرّف حساب). */
  settingsAccountId?: number | null;
  /** صندوق المستخدم الافتراضي (معرّف صندوق لا حساب). */
  userDefaultBoxId?: number | null;
}): CashAccountPick {
  const live = activeBoxes(opts.boxes);

  if (opts.settingsAccountId) {
    const box = live.find((b) => b.account_id === opts.settingsAccountId) ?? null;
    // الإعداد يُحترم ولو لم يكن صندوقاً مسجَّلاً (قد يكون حساباً بنكياً).
    if (!box || sameCurrency(box, opts.currency)) {
      return { accountId: Number(opts.settingsAccountId), box, source: "settings" };
    }
  }

  if (opts.userDefaultBoxId) {
    const box = live.find((b) => b.id === opts.userDefaultBoxId);
    if (box && sameCurrency(box, opts.currency)) {
      return { accountId: box.account_id, box, source: "user-default" };
    }
  }

  const byCurrency = live.filter((b) => sameCurrency(b, opts.currency));
  const preferred = byCurrency.find((b) => b.is_default) ?? byCurrency[0];
  if (preferred) {
    return {
      accountId: preferred.account_id,
      box: preferred,
      source: opts.currency ? "currency" : "company-default",
    };
  }

  const companyDefault = live.find((b) => b.is_default);
  if (companyDefault) {
    return {
      accountId: companyDefault.account_id,
      box: companyDefault,
      source: "company-default",
    };
  }

  return { accountId: null, box: null, source: "none" };
}

/** تحذير عملة للعرض — الخادم هو الحارس، وهذا إشعارٌ مبكر لا منع. */
export function currencyMismatchWarning(
  box: CashBoxLedgerLink | null | undefined,
  currency?: string | null,
): string | null {
  if (!box || !currency) return null;
  if (sameCurrency(box, currency)) return null;
  return `عملة المستند ${currency} وعملة ${box.name} ${box.currency_code} — سيُحتسب بسعر الصرف.`;
}
