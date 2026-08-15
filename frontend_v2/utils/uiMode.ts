/**
 * THA-110 — «الوضع السهل»: قناع عرضٍ فوق نفس البيانات، لا منتجٌ ثانٍ.
 *
 * **عرضٌ لا صلاحية**: يقلّم ما يُعرَض أولاً ولا يحجب مساراً ولا يمنح شيئاً.
 * الرابط المباشر لأي شاشة متقدمة يبقى يعمل في الوضع السهل — «مخفيّ لا محذوف»
 * — والحارس الوحيد يبقى الصلاحيات (`core/access.py`). فلا تتنازع آليتان فوق
 * قائمة واحدة: الصلاحية تحجب، والوضع يُرتّب.
 *
 * مصدر الحقيقة هو الخادم (`UserCompanyMembership.ui_mode`) ويصل ضمن حمولة
 * `/api/permissions/me/` المحمَّلة عند الإقلاع أصلاً. الـcache هنا لتطبيقٍ فوري
 * قبل رد الخادم، ومفتاحه رقم الشركة: المتصفح ≈ المستخدم والمفتاح ≈ الشركة،
 * فتُعطى (مستخدم × شركة) مجاناً — نفس عُرف `AppearanceContext`.
 *
 * دوال صرفة (لا React) كي تُختبر وحدها، ولا ترمي أبداً: متصفح يمنع التخزين
 * يبقى على «متقدم» بدل أن تنكسر القائمة كلها.
 */
export type UiMode = 'simple' | 'advanced';

export const UI_MODES = ['simple', 'advanced'] as const;

/** الافتراضي هو التجربة الكاملة — التبسيط اختيارٌ صريح لا سلوك صامت. */
export const DEFAULT_UI_MODE: UiMode = 'advanced';

const UI_MODE_KEY = 'ktra_ui_mode';

/** cache خاص بكل شركة: وضع شركةٍ لا يسري على أخرى. */
export const uiModeCacheKey = (tenantId: number): string => `${UI_MODE_KEY}::${tenantId}`;

/** أي قيمة غير معروفة (خادم أقدم، cache فاسد، حمولة ناقصة) ⇒ «متقدم». */
export function normalizeUiMode(value: unknown): UiMode {
  return UI_MODES.includes(value as UiMode) ? (value as UiMode) : DEFAULT_UI_MODE;
}

export function readUiModeCache(tenantId: number): UiMode {
  try {
    return normalizeUiMode(localStorage.getItem(uiModeCacheKey(tenantId)));
  } catch {
    return DEFAULT_UI_MODE;
  }
}

export function writeUiModeCache(tenantId: number, mode: UiMode): void {
  try {
    localStorage.setItem(uiModeCacheKey(tenantId), mode);
  } catch {
    /* تجاهل — الحالة في الذاكرة تكفي لهذه الجلسة */
  }
}

/**
 * الشاشات الظاهرة في الوضع السهل: الأساسيات التي طلبها المالك + الرئيسية
 * والإعدادات (وإلا صار الوضع بلا مخرج). لا شاشة جديدة تُبنى — هذه كلها قائمة.
 */
export const SIMPLE_VIEWS = [
  'dashboard',
  'sales-invoices',
  'purchase-invoices',
  'stock-levels',
  'items-management',
  'supplier-management',
  'sales-customers',
  'settings',
] as const;

const SIMPLE_VIEW_SET: ReadonlySet<string> = new Set(SIMPLE_VIEWS);

export function viewVisibleInSimpleMode(view: string): boolean {
  return SIMPLE_VIEW_SET.has(view);
}
