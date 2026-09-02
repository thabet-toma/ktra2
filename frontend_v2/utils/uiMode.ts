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
  'items-management',
  'stock-levels',
  'supplier-management',
  'sales-customers',
  'settings',
] as const;

const SIMPLE_VIEW_SET: ReadonlySet<string> = new Set(SIMPLE_VIEWS);

export function viewVisibleInSimpleMode(view: string): boolean {
  return SIMPLE_VIEW_SET.has(view);
}

/* ══════════════════════════════════════════════════════════════════════════
   T-SIMPL2 — قناع **العناصر داخل الشاشات** (لا القائمة وحدها)

   القناع الأول (`SIMPLE_VIEWS` أعلاه) يقرّر أيّ شاشةٍ تُعرَض. وهذا يقرّر ماذا
   يُعرَض **داخلها**: تاريخ الاستحقاق، الضريبة، خصم السطر، أعمدة الجداول…

   ثلاث قواعد، وكلها هنا في مكانٍ واحد كي لا تُكتب ثانيةً في كل شاشة:

   1. **سِجلٌّ واحد يُقرأ منه «ماذا يُخفي الوضع السهل»** — لا شرطٌ متناثر في
      عشرين ملفاً. المفاتيح **مفاهيمُ لا مواضع**: `doc.tax` واحدةٌ لفاتورة البيع
      وفاتورة الشراء معاً، فلا يفترق الوضعان على شاشتين. هذا بالضبط نموذج Odoo
      (`groups="sale.group_discount_per_so_line"`): صفةٌ تصريحية واحدة على الحقل
      وقائمةٌ واحدة تُقرأ، لا شرطٌ مكتوبٌ في كل قالب.
   2. **قاعدة السقوط للظهور** (`keepIfSet`) — عنصرٌ يحمل قيمةً فعلية **يظهر رغم
      الوضع**: ضريبةٌ محسوبة، أو استحقاقٌ مُدخَل، أو كميةٌ محجوزة. الإخفاء يقلّم
      ما هو صفرٌ أو فارغ؛ ولا يُخفي أبداً رقماً يغيّر مالاً. هنا نتجاوز المرجع:
      في Odoo إطفاءُ المجموعة يُخفي الحقل ولو كانت قيمته غير صفرية.
   3. **الإخفاء عرضٌ لا حذف** — العنصر المخفيّ يحتفظ بقيمته وحالته، فحمولةُ
      الحفظ من الوضعين واحدة ⇒ **نفس القيد المحاسبي بالضبط** (قانون قناع
      THA-110 نفسه، يسمّره `sales/tests/test_simple_mode_journal_parity.py`).

   دوال صرفة بلا React كي تُختبر وحدها، وغلافها التفاعلي الوحيد
   `hooks/useSimpleUi.ts` — **آليةٌ واحدة لا ثانية لها**: آليتان متنازعتان فوق
   عنصرٍ واحد هما كيف يختفي حقلٌ بصمت.
   ══════════════════════════════════════════════════════════════════════════ */

/**
 * ما يطويه الوضع السهل، ولماذا. القيمة نصُّ السبب — تُقرأ هنا ولا تُعرض على
 * المستخدم (نصوص المستخدم كلها في `constants/simpleHints.ts`).
 */
export const SIMPLE_MASK = {
  'doc.due-date':
    'تاريخ الاستحقاق — التاجر المبتدئ يبيع ويقبض، ومواعيد الآجل مفهومٌ ائتماني يأتي لاحقاً.',
  'doc.tax':
    'الضريبة (العمود والنسبة وسطور المجاميع) — أكثر الصغار غير مسجَّلين، والقيمة تبقى كما هي.',
  'doc.line-discount':
    'خصم السطر — خصم الفاتورة يكفي مبتدئاً؛ وهذا ما تُطفئه Odoo افتراضياً أيضاً.',
  'doc.currency':
    'العملة — حين تحسمها الإعدادات فعلاً؛ ومحدِّدٌ بخيارٍ واحد ليس قراراً.',
  'doc.licensed-dealer':
    'رقم المشتغل المرخّص — حقلٌ ضريبيٌّ صرف، يتبع «الضريبة» في الطيّ.',
  'doc.advanced-tabs':
    'تبويبات القيد والرسوم والأقساط والسجلّات — قراءةُ محاسبٍ لا إدخالُ بائع.',
  'doc.audit-strip':
    'رقم القيد ورقم الحركة وآخر مفتاح في شريط الحالة — أثرٌ للتشخيص لا للبيع.',
  'list.type-filter':
    'فلتر نوع المستند في القوائم — الحالة وحالة الدفع تكفيان.',
  'stock.bulk-group':
    'تعيين «النوع/البراند» جماعياً — إعدادُ كتالوجٍ لا عملٌ يومي.',
  'home.task-analytics':
    'رسمُ توزيع المهام وعدّاد المستخدمين في الرئيسية — مقاييس إدارةٍ لا مقاييس متجر.',
  'settings.local-cache':
    'إدارة التخزين المحلي (مسح الـcache) — زرٌّ تقنيّ يُشخَّص به عطل، لا إعدادُ متجر.',
  // issue #56 — سند المصروف: المستفيد اختياري أصلاً (شريكٌ أو اسمٌ حر أو لا شيء)،
  // والمبتدئ يسجّل «صرفت 500 كهرباء» بلا حاجة لتسمية مَن استلم.
  'doc.expense-beneficiary':
    'المستفيد في سند المصروف (شريك أو اسم حر) — مصروفٌ نقديٌّ بسيط لا يحتاج تسمية مستفيده.',
} as const;

export type MaskKey = keyof typeof SIMPLE_MASK;

/**
 * هل يُعرَض عنصرٌ متقدّم؟ نقطةُ القرار الوحيدة، وفيها قاعدة السقوط للظهور.
 *
 * @param key      مفتاح السِّجل — مفهومٌ لا موضع.
 * @param mode     وضع العرض الحالي.
 * @param keepIfSet حقيقةٌ من الشاشة تقول «هذا العنصر يحمل قيمةً فعلية».
 *
 * مفتاحٌ خارج السِّجل **يُعرض** — الفشل نحو الظهور لا نحو الإخفاء الصامت.
 */
export function showAdvanced(key: MaskKey, mode: UiMode, keepIfSet = false): boolean {
  if (mode !== 'simple') return true;
  return keepIfSet || !(key in SIMPLE_MASK);
}

/**
 * أعمدة الجداول المطويّة في الوضع السهل — مفاتيح الأعمدة كما تُعرّفها الشاشة.
 * مفاتيح الشاشات هي أسماء `AppView` نفسها فلا يُخترع اسمٌ ثانٍ للشاشة الواحدة.
 */
export const SIMPLE_HIDDEN_COLUMNS: Readonly<Record<string, readonly string[]>> = {
  // النوع (نقدي/آجل) والكشف الضريبي ورصيد العميل — قراءةُ محاسبٍ فوق قائمة بيع.
  'sales-invoices': ['invoice_type', 'customer_balance', 'vat_statement'],
  // المحجوز والمتاح يظهران متى وُجد حجزٌ فعلاً (`keep`)، والحدّ الأقصى والنوع إعدادُ كتالوج.
  'stock-levels': ['reserved', 'available', 'max', 'grp'],
  'items-management': ['purchased', 'reserved', 'available', 'avg_monthly', 'max', 'grp'],
  // النطاق (محلي/دولي) ورقم الحساب المحاسبي وحدّ الائتمان.
  'supplier-management': ['scope', 'acct', 'limit'],
  // الرقم الضريبي وفئة السعر وحدّ الائتمان.
  'sales-customers': ['tax_number', 'tier', 'credit_limit'],
};

/**
 * تقليم أعمدة جدولٍ حسب الوضع. صرفةٌ ولا تُغيّر المصفوفة الأصلية.
 *
 * @param keep أعمدةٌ تبقى رغم الوضع — قاعدة السقوط للظهور على مستوى العمود
 *             (عمود «محجوز» يعود متى حُجز شيءٌ فعلاً).
 */
export function visibleColumns<C extends { key: string }>(
  columns: readonly C[],
  screen: string,
  mode: UiMode,
  keep: readonly string[] = [],
): C[] {
  if (mode !== 'simple') return [...columns];
  const hidden = new Set<string>(SIMPLE_HIDDEN_COLUMNS[screen] ?? []);
  for (const k of keep) hidden.delete(k);
  return columns.filter((c) => !hidden.has(c.key));
}
