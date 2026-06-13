/**
 * task16 D14: اختصارات وصول سريع في الشريط العلوي — قابلة للتهيئة من الإعدادات.
 *
 * المستخدم يختار من قائمة الشاشات المتاحة أيّها يظهر كزر اختصار. التخزين محلي
 * لكل متصفح (localStorage) ويُبثّ حدث `ktra:quick-shortcuts` عند التغيير ليُحدِّث
 * الشريط فوراً دون إعادة تحميل.
 */
import type { AppView } from "../types";

const LS_KEY = "ktra:quickShortcuts";
export const QUICK_SHORTCUTS_EVENT = "ktra:quick-shortcuts";

/** الشاشات المتاحة كاختصارات سريعة (مجموعة منتقاة من شاشات الشريط الجانبي). */
export const SHORTCUTABLE_VIEWS: { view: AppView; label: string }[] = [
  { view: "dashboard", label: "الرئيسية" },
  { view: "sales-invoices", label: "فواتير المبيعات" },
  { view: "purchase-invoices", label: "فواتير الشراء" },
  { view: "sales-quotations", label: "عروض الأسعار" },
  { view: "price-offers", label: "عروض الموردين" },
  { view: "items-management", label: "الأصناف" },
  { view: "supplier-management", label: "الموردون" },
  { view: "sales-customers", label: "العملاء" },
  { view: "stock-movements", label: "حركات المخزون" },
  { view: "accounting-journals", label: "دفتر اليومية" },
  { view: "cash-boxes", label: "الصناديق" },
  { view: "reports", label: "التقارير" },
];

const DEFAULT_SHORTCUTS: AppView[] = ["dashboard", "sales-invoices", "purchase-invoices"];

const VALID = new Set(SHORTCUTABLE_VIEWS.map((s) => s.view));

export function getQuickShortcuts(): AppView[] {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return DEFAULT_SHORTCUTS;
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return DEFAULT_SHORTCUTS;
    const filtered = parsed.filter((v): v is AppView => typeof v === "string" && VALID.has(v as AppView));
    return filtered;
  } catch {
    return DEFAULT_SHORTCUTS;
  }
}

export function setQuickShortcuts(views: AppView[]): void {
  try {
    const clean = views.filter((v) => VALID.has(v));
    localStorage.setItem(LS_KEY, JSON.stringify(clean));
    window.dispatchEvent(new CustomEvent(QUICK_SHORTCUTS_EVENT));
  } catch {
    /* تجاهل أخطاء التخزين */
  }
}

export function labelForShortcut(view: AppView): string {
  return SHORTCUTABLE_VIEWS.find((s) => s.view === view)?.label || view;
}
