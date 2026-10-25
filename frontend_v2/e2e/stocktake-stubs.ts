import { Page, type Route } from '@playwright/test';

/**
 * K2 — محاكي الجرد: نفس عقد `inventory/serializers.py` (بنود بلا أسعار ولا
 * تكاليف)، ويرفض ما يرفضه الخادم فعلاً:
 *   - `scope` و`lines` معاً ⇒ 400، ونطاقٌ فارغ ⇒ 400، وتصنيفٌ خارج الشركة ⇒ 400.
 *   - `scope.products` (ST-1) بحرفها: قائمةٌ وأعدادٌ صحيحة وسقفٌ ووجودٌ وأهلية، ثم
 *     **إسقاطٌ لا رفض** لما يغطّيه تصنيفٌ مؤشَّر أو «بدون تصنيف» (و`all` يُسقطها
 *     كلها)، ولا يُخزَّن المفتاح إلا غيرَ فارغ — والتوليد اتحادُ التصنيفات
 *     والمنتجات الصريحة و«بدون تصنيف» فوق قاعدة الأهلية نفسها.
 *   - `stocktakes/scope-products/` بقائمة سماحها `{id, name, sku, is_active}` وترتيبها
 *     (`name_ar` ثم `id`) ورسائل رفضها: 400 على `category` الغائب/غير الصحيح/غير
 *     الموجود وعلى `include_inactive` غير الصالح.
 *   - نطاقٌ بلا منتجات مطابقة ⇒ 400 «لا منتجات في هذا الاختيار».
 *   - `If-Match` بائت ⇒ 412 `stale_document` قبل أي كتابة.
 *   - ترحيلٌ وكلُّ بنوده غير معدودة بلا العلم ⇒ 400 قبل أي كتابة.
 *
 * ويُسجّل كلَّ طلبِ قائمة منتجات **بلا `search`** — الحالة الثالثة في التذكرة:
 * الشاشة يجب ألا تنزّل الكتالوج لا عند الفتح ولا عند فتح جرد.
 */

export type StubWarehouse = { id: number; name: string };
export type StubCategory = { id: number; name: string; parent: number | null };
export type StubProduct = {
  id: number; sku: string; name_ar: string; name_en: string; display_name: string;
  brand: string; category: number | null; quantity_on_hand: string;
  is_active: boolean; is_service: boolean;
};

export const STUB_CATEGORIES: StubCategory[] = [
  { id: 11, name: 'قطع غيار', parent: null },
  { id: 12, name: 'محركات', parent: 11 },
  { id: 14, name: 'إطارات', parent: null },
  { id: 15, name: 'زيوت', parent: null },
];

const CATEGORY_NAMES = new Map(STUB_CATEGORIES.map((row) => [row.id, row.name]));

export const STUB_PRODUCTS: StubProduct[] = [
  {
    id: 101, sku: 'SP-101', name_ar: 'فلتر زيت', name_en: 'Oil filter',
    display_name: 'فلتر زيت — مان', brand: 'مان', category: 11,
    quantity_on_hand: '10.0000', is_active: true, is_service: false,
  },
  {
    id: 102, sku: 'SP-102', name_ar: 'فلتر هواء', name_en: 'Air filter',
    display_name: 'فلتر هواء — مان', brand: 'مان', category: 11,
    quantity_on_hand: '6.0000', is_active: true, is_service: false,
  },
  {
    id: 103, sku: 'SP-103', name_ar: 'فلتر قديم', name_en: 'Old filter',
    display_name: 'فلتر قديم — مان', brand: 'مان', category: 11,
    quantity_on_hand: '2.0000', is_active: false, is_service: false,
  },
  {
    id: 104, sku: 'SP-104', name_ar: 'طرمبة ماء', name_en: 'Water pump',
    display_name: 'طرمبة ماء — بوش', brand: 'بوش', category: 12,
    quantity_on_hand: '3.0000', is_active: true, is_service: false,
  },
  {
    id: 105, sku: 'SP-105', name_ar: 'إطار ميشلان', name_en: 'Michelin tyre',
    display_name: 'إطار 205/55 — ميشلان', brand: 'ميشلان', category: 14,
    quantity_on_hand: '8.0000', is_active: true, is_service: false,
  },
  {
    id: 106, sku: 'SP-106', name_ar: 'إطار بريدجستون', name_en: 'Bridgestone tyre',
    display_name: 'إطار 195/65 — بريدجستون', brand: 'بريدجستون', category: 14,
    quantity_on_hand: '5.0000', is_active: true, is_service: false,
  },
  {
    id: 107, sku: 'SP-107', name_ar: 'إطار بيريللي', name_en: 'Pirelli tyre',
    display_name: 'إطار 215/60 — بيريللي', brand: 'بيريللي', category: 14,
    quantity_on_hand: '1.0000', is_active: true, is_service: false,
  },
  {
    id: 108, sku: 'SP-108', name_ar: 'زيت محرك', name_en: 'Engine oil',
    display_name: 'زيت محرك — موبيل', brand: 'موبيل', category: null,
    quantity_on_hand: '12.0000', is_active: true, is_service: false,
  },
  {
    id: 109, sku: 'SP-109', name_ar: 'خدمة تركيب', name_en: 'Fitting service',
    display_name: 'خدمة تركيب', brand: '', category: 11,
    quantity_on_hand: '0.0000', is_active: true, is_service: true,
  },
  // ST-2: منتجٌ ثانٍ بلا تصنيف وغير فعّال — يُظهر شارةَ «غير فعّال» في اللوحة،
  // ويُبقي لـ«بدون تصنيف» أكثر من صفٍّ واحد فلا يُرقّى اختيارُ منتجٍ واحدٍ إلى
  // العلم (ترقية ST-2A). ولا يمسّ عدّادات العلم المطفأ (7 منتجات، 4 تصنيفات).
  {
    id: 110, sku: 'SP-110', name_ar: 'شحم فرامل', name_en: 'Brake grease',
    display_name: 'شحم فرامل — شل', brand: 'شل', category: null,
    quantity_on_hand: '3.0000', is_active: false, is_service: false,
  },
];

const WAREHOUSES: StubWarehouse[] = [
  { id: 1, name: 'المستودع الرئيسي' },
  { id: 2, name: 'مستودع الفرع' },
];

type InternalLine = {
  id: number;
  product: number;
  counted: string | null;
  by: string;
  at: string | null;
  system_quantity: string | null;
  variance: string | null;
};

type InternalStocktake = {
  id: number;
  number: string;
  date: string;
  warehouse: number | null;
  notes: string;
  scope: Record<string, unknown> | null;
  is_posted: boolean;
  journal: number | null;
  lines: InternalLine[];
  created_by: number;
  created_by_name: string;
  created_at: string;
  updated_at: string;
};

export type StocktakeSaveRequest = {
  ifMatch: string | null;
  body: Record<string, unknown>;
};

/** K4 — رابط عدٍّ في المحاكي: الحالة كلها كما في `StocktakeCountLink` + `DocumentShare`. */
export type StubCountLink = {
  id: number;
  stocktakeId: number;
  token: string;
  counter_name: string;
  categories: number[] | null;
  expires_at: string | null;
  finished_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

export type PublicCountWrite = {
  entries: Array<{ line_id: number; counted_quantity: string | null }>;
  finished: boolean;
};

/**
 * الحالة المشتركة بين صفحة المدير (المصادَقة) والصفحة العامة في سياقِ متصفّحٍ
 * آخر: نفس «الخادم» في الذاكرة، فيرى الموظفُ ما كتبه المديرُ والعكس.
 */
export type CountApiBackend = {
  stocktakes: InternalStocktake[];
  links: StubCountLink[];
  /** الكتابات الناجحة وحدها — يشهد بها اختبار «دفعة واحدة». */
  publicWrites: PublicCountWrite[];
  /** كل محاولة كتابةٍ وصلت (ومنها المرفوضة بالشبكة) — للتشخيص. */
  publicAttempts: PublicCountWrite[];
  /** عدد ردود 400 لأسطرٍ في `rejectLineIds` — دليلٌ حتميّ على وصول الرفض. */
  publicRejects: number;
  publicReads: number;
  /** قراءات قائمة الروابط الإدارية — يشهد بها اختبار إعادة الجلب التلقائية. */
  adminReads: number;
  publicWriteFailure: number | null;
  publicReadFailure: number | null;
  /** أسطرٌ يرفضها المحاكي 400 كأنها خرجت من النطاق — لاختبار رسالةٍ قديمة. */
  rejectLineIds: number[];
  /** تأخير ردّ الكتابة — لاختبار تعديلٍ يقع أثناء الطيران. */
  delayWritesMs: number;
  /** يضيف حقولاً مالية إلى الحمولة العامة — يثبت أن الصفحة ترسم قائمةً ثابتة. */
  leakMoneyFields: boolean;
  /** كم حمولةً عامة خرجت بالحقول المالية — دليلٌ على أن التسريب وقع فعلاً. */
  publicLeaks: number;
  nextLinkId: number;
  nextTokenSeq: number;
  /** كتابةُ عدٍّ تحرّك `updated_at` والتوكن كما في الخادم (عقد K1/K2). */
  touchStocktake: (stocktakeId: number) => void;
};

export type StocktakeStubHandle = {
  /** طلبات قائمة المنتجات بلا `search` — يجب أن تبقى صفراً. */
  productListCallsWithoutSearch: string[];
  productListCallsWithSearch: string[];
  /** ST-2: طلبات `stocktakes/scope-products/` — يشهد بها اختبار «طلبٌ واحد لكل لوحة». */
  scopeProductRequests: string[];
  /** ST-2: يُفشل قراءة منتجات التصنيف التالية (500 مثلاً) — لاختبار «إعادة المحاولة». */
  setScopeProductFailure: (status: number | null) => void;
  createdBodies: Record<string, unknown>[];
  saveRequests: StocktakeSaveRequest[];
  postRequests: Record<string, unknown>[];
  /** يحرّك توكن المستند كأن مديراً آخر حفظه — لصنع 412 حتمياً. */
  bumpEtag: () => void;
  /** يجعل طلب عدّادات النطاق التالي يتباطأ — لاختبار وصول الردود بغير ترتيبها. */
  delayNextScopeCounts: (ms: number) => void;
  /** يجعل قراءة بطاقة الجرد التالية تتباطأ — لاختبار تعطيل العدّ أثناء «تحديث». */
  delayNextStocktakeGet: (ms: number) => void;
  /** يجعل عدّادات النطاق تفشل (500) — لاختبار مسار «إعادة المحاولة». */
  setScopeCountsFailure: (fail: boolean) => void;
  /** عدد طلبات العدّادات المتأخّرة التي أُجيب عنها — انتظارٌ بحسب الترتيب لا بالمهلة. */
  scopeCountsDelayedAnswered: number;
  /** يغيّر كمية بندٍ على «الخادم» — ويمسّ `updated_at` والتوكن كما يفعل الخادم. */
  setServerCounted: (product: number, quantity: string | null, by?: string) => void;
  /** يغيّر ملاحظات المستند على «الخادم» — ويمسّ `updated_at` والتوكن كما يفعل الخادم. */
  setServerNotes: (notes: string) => void;
  /** توكن الجرد الحالي في «الخادم» — الأول (900) ما لم يُمرَّر معرّفٌ آخر. */
  currentEtag: (stocktakeId?: number) => string;
  /** K4: الحالة المشتركة لروابط العدّ — تمرَّر إلى `installPublicCountStubs`. */
  countBackend: CountApiBackend;
  /** K4: طلبات `GET stocktakes/<id>/` — يشهد بها اختبار التحديث كل 30 ث. */
  stocktakeGetCount: number;
  /** K4: يُفشل كتابات العدّ العامة القادمة (503 مثلاً) — لاختبار النسخة المحلية. */
  setPublicWriteFailure: (status: number | null) => void;
  /** K4: يُفشل قراءات العدّ العامة (429 مثلاً) — لشاشة «حاول بعد قليل». */
  setPublicReadFailure: (status: number | null) => void;
  /** K4: يُخرج سطراً من نطاق كل رابطٍ لا يشمل تصنيف «محركات» (12). */
  moveLineOutOfScope: (lineId: number) => void;
};

const nowIso = () => new Date().toISOString();

/** كميةٌ كما يقبلها `CountedQuantityField`: null، أو رقمٌ غير سالب بأربع منازل. */
const QUANTITY_TEXT = /^(?:\d+(?:\.\d*)?|\.\d+)$/;

/** رسالة `CountedQuantityField` نفسها — لا نسخةً ثانية في المحاكي. */
const INVALID_QUANTITY_MESSAGE =
  'كمية غير صالحة — رقمٌ غير سالب بأربع منازل عشرية على الأكثر.';

const parseQuantity = (raw: unknown): { ok: true; value: string | null } | { ok: false } => {
  if (raw == null) return { ok: true, value: null };
  const text = String(raw).trim();
  if (!QUANTITY_TEXT.test(text)) return { ok: false };
  const decimals = text.includes('.') ? text.split('.')[1].length : 0;
  const number = Number(text);
  if (!Number.isFinite(number) || number < 0 || decimals > 4) return { ok: false };
  // الخادم يردّ `DecimalField(decimal_places=4)` ⇒ «7» تعود «7.0000».
  return { ok: true, value: number.toFixed(4) };
};

/**
 * مقارنة النطاق بالقيمة لا بترتيب المفاتيح (الخادم يقارن القاموس المخزَّن).
 *
 * و`products` تُقارَن كغياب == فراغ: الخادم لا يخزّن المفتاح إلا غيرَ فارغ، و
 * `stocktake_scope_signature` تقرأ الغياب كما تقرأ `[]` — فصدى عميلٍ يحمل
 * `products: []` بعد أن أُسقطت كلُّها ليس اختلافاً.
 */
const scopeEquals = (a: unknown, b: unknown): boolean => {
  if (a == null || b == null || typeof a !== 'object' || typeof b !== 'object') {
    return a === b;
  }
  const left = a as Record<string, unknown>;
  const right = b as Record<string, unknown>;
  const categories = (value: unknown) => (
    Array.isArray(value) ? [...value].map(Number).sort((x, y) => x - y) : value
  );
  const products = (value: unknown) => categories(value ?? []);
  return left.all === right.all
    && left.uncategorized === right.uncategorized
    && left.include_inactive === right.include_inactive
    && JSON.stringify(categories(left.categories))
      === JSON.stringify(categories(right.categories))
    && JSON.stringify(products(left.products)) === JSON.stringify(products(right.products));
};

/** الرسالة نفسها التي ترفعها `_normalize_stocktake_scope` عند تجاوز السقف. */
const STOCKTAKE_SCOPE_MAX_PRODUCTS = 5000;

const productOf = (id: number): StubProduct | undefined =>
  STUB_PRODUCTS.find((row) => row.id === id);

const categoryName = (id: number | null): string =>
  (id == null ? '' : CATEGORY_NAMES.get(id) ?? '');

const lineView = (line: InternalLine) => {
  const product = productOf(line.product);
  return {
    id: line.id,
    product: line.product,
    product_name: product?.display_name ?? '',
    counted_quantity: line.counted,
    counted_by_name: line.by,
    counted_at: line.at,
    product_sku: product?.sku ?? '',
    product_category: product?.category ?? null,
    product_quantity_on_hand: product?.quantity_on_hand ?? '0.0000',
    product_is_active: product?.is_active ?? true,
    system_quantity: line.system_quantity,
    variance: line.variance,
  };
};

const stocktakeView = (stocktake: InternalStocktake) => ({
  id: stocktake.id,
  stocktake_number: stocktake.number,
  stocktake_date: stocktake.date,
  warehouse: stocktake.warehouse,
  warehouse_name: stocktake.warehouse == null
    ? null
    : WAREHOUSES.find((row) => row.id === stocktake.warehouse)?.name ?? null,
  notes: stocktake.notes,
  is_posted: stocktake.is_posted,
  journal: stocktake.journal,
  scope: stocktake.scope,
  created_by: stocktake.created_by,
  created_by_name: stocktake.created_by_name,
  created_at: stocktake.created_at,
  updated_at: stocktake.updated_at,
  lines: stocktake.lines.map(lineView),
  line_count: stocktake.lines.length,
  counted_count: stocktake.lines.filter((line) => line.counted != null).length,
});

/**
 * صفّ القائمة بعقد `StocktakeListSerializer.Meta.fields` بالحرف — اختيارٌ
 * صريحٌ لكل حقل، لا «احذف ما ليس هنا»: الحذف من قائمةٍ يُبقي أيَّ حقلٍ جديدٍ
 * يضيفه `stocktakeView` (مثل `created_by`) متسرّباً إلى القائمة بلا قرار.
 */
const stocktakeSummary = (stocktake: InternalStocktake) => {
  const view = stocktakeView(stocktake);
  return {
    id: view.id,
    stocktake_number: view.stocktake_number,
    stocktake_date: view.stocktake_date,
    warehouse: view.warehouse,
    warehouse_name: view.warehouse_name,
    notes: view.notes,
    is_posted: view.is_posted,
    journal: view.journal,
    created_at: view.created_at,
    updated_at: view.updated_at,
    created_by_name: view.created_by_name,
    line_count: view.line_count,
    counted_count: view.counted_count,
  };
};

const countsFor = (includeInactive: boolean) => {
  const eligible = STUB_PRODUCTS.filter(
    (product) => !product.is_service && (includeInactive || product.is_active),
  );
  const categories: Record<string, number> = {};
  let uncategorized = 0;
  for (const product of eligible) {
    if (product.category == null) uncategorized += 1;
    else categories[String(product.category)] = (categories[String(product.category)] ?? 0) + 1;
  }
  return { categories, uncategorized, all: eligible.length };
};

/**
 * `GET stocktakes/scope-products/` — قاعدة الأهلية نفسها، ثم تصنيفٌ واحد، بترتيب
 * الخادم (`name_ar` ثم `id`) وبقائمة السماح الأربعة حرفاً.
 */
const scopeProductsFor = (category: number | null, includeInactive: boolean) =>
  STUB_PRODUCTS
    .filter((product) => !product.is_service && (includeInactive || product.is_active))
    .filter((product) => (category === null
      ? product.category == null
      : product.category === category))
    .sort((a, b) => a.name_ar.localeCompare(b.name_ar, 'ar') || a.id - b.id)
    .map((product) => ({
      id: product.id,
      name: product.display_name,
      sku: product.sku,
      is_active: product.is_active,
    }));

const json = (
  route: Route, status: number, body: unknown, headers: Record<string, string> = {},
) => route.fulfill({
    status,
    contentType: 'application/json',
    headers: {
      // `ETag` ترويسةٌ غير بسيطة: بلا `Expose` يحجبها المتصفح عن JS في طلبٍ
      // متقاطع الأصل — وواجهةُ الإنتاج تضبطها في `CORS_EXPOSE_HEADERS`.
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Expose-Headers': 'ETag',
      // طلباتُ الكتابة تحمل `Content-Type: application/json` و`If-Match`،
      // فالمتصفح يسبقها بـOPTIONS؛ محاكيٌ لا يجيب عنه يُفشل الطلب قبل وصوله.
      'Access-Control-Allow-Headers': 'content-type, if-match, x-tenant-id, x-branch-id',
      'Access-Control-Allow-Methods': 'GET, POST, PATCH, DELETE, OPTIONS',
      ...headers,
    },
    body: JSON.stringify(body),
  });

// ── K4: روابط العدّ — منطق المحاكي المشترك ────────────────────────────────

const categoryPathText = (categoryId: number | null): string => {
  if (categoryId == null) return '';
  const parts: string[] = [];
  const seen = new Set<number>();
  let current = STUB_CATEGORIES.find((row) => row.id === categoryId);
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    parts.unshift(current.name);
    current = current.parent == null
      ? undefined
      : STUB_CATEGORIES.find((row) => row.id === current?.parent);
  }
  return parts.join(' ‹ ');
};

const lineCategoryOf = (line: InternalLine): number | null =>
  productOf(line.product)?.category ?? null;

const inCountScope = (line: InternalLine, categories: number[] | null): boolean => {
  if (categories == null) return true;
  const category = lineCategoryOf(line);
  return category != null && categories.includes(category);
};

/** `_count_link_status`: ميّت ← منتهٍ ← مكتمل ← حيّ. */
const countLinkStatusOf = (
  link: StubCountLink, stocktake: InternalStocktake,
): 'active' | 'finished' | 'expired' | 'revoked' => {
  if (link.revoked_at || stocktake.is_posted) return 'revoked';
  if (link.expires_at && Date.parse(link.expires_at) <= Date.now()) return 'expired';
  if (link.finished_at) return 'finished';
  return 'active';
};

const countLinkProgressOf = (link: StubCountLink, stocktake: InternalStocktake) => {
  const scoped = stocktake.lines.filter((line) => inCountScope(line, link.categories));
  return {
    lines: scoped.length,
    counted: scoped.filter((line) => line.counted != null).length,
  };
};

/** `_count_link_row` — المفاتيح نفسها بالحرف. */
const countLinkRow = (link: StubCountLink, stocktake: InternalStocktake) => ({
  id: link.id,
  token: link.token,
  url_path: `/api/share/${link.token}/count/`,
  counter_name: link.counter_name,
  categories: link.categories,
  status: countLinkStatusOf(link, stocktake),
  expires_at: link.expires_at,
  finished_at: link.finished_at,
  progress: countLinkProgressOf(link, stocktake),
  created_at: link.created_at,
});

/** `GET /api/share/<token>/count/` — قائمة سماحٍ بلا حقلٍ ماليّ واحد. */
const publicCountPayload = (
  link: StubCountLink, stocktake: InternalStocktake, backend: CountApiBackend,
) => ({
  company_name: 'شركة الجرد',
  stocktake_number: stocktake.number,
  date: stocktake.date,
  warehouse: stocktake.warehouse == null
    ? ''
    : WAREHOUSES.find((row) => row.id === stocktake.warehouse)?.name ?? '',
  counter_name: link.counter_name,
  finished: link.finished_at != null,
  lines: stocktake.lines
    .filter((line) => inCountScope(line, link.categories))
    .map((line) => {
      const product = productOf(line.product);
      return {
        line_id: line.id,
        sku: product?.sku ?? '',
        name: product?.display_name ?? product?.name_ar ?? '',
        brand: product?.brand ?? '',
        category_path: categoryPathText(product?.category ?? null),
        uom: 'حبة',
        system_quantity: product?.quantity_on_hand ?? '0.0000',
        counted_quantity: line.counted,
        counted_by_name: line.by,
        // تسريبٌ متعمَّد يثبت أن الصفحة ترسم قائمةً ثابتة لا كل ما يصل.
        ...(backend.leakMoneyFields
          ? { cost_price: '9.99', unit_price: '19.50', total_value: '99.00' }
          : {}),
      };
    }),
});

const lineInStocktake = (stocktake: InternalStocktake, lineId: number): InternalLine | undefined =>
  stocktake.lines.find((line) => line.id === lineId);

/** يستجيب لطلبات سطح العدّ العامّ؛ `false` يعني «ليس طلبي» (يمرّر المستدعي). */
async function serveCountShare(route: Route, backend: CountApiBackend): Promise<boolean> {
  const url = new URL(route.request().url());
  const match = url.pathname.match(/\/api\/share\/([^/]+)\/count\/$/);
  if (!match) return false;
  const method = route.request().method();
  if (method === 'OPTIONS') {
    await json(route, 200, {});
    return true;
  }
  const token = decodeURIComponent(match[1]);
  const link = backend.links.find((row) => row.token === token);
  const stocktake = link
    ? backend.stocktakes.find((row) => row.id === link.stocktakeId)
    : undefined;
  if (!link || !stocktake) {
    await json(route, 404, { detail: 'الرابط غير صحيح.' });
    return true;
  }
  const status = countLinkStatusOf(link, stocktake);
  if (status === 'revoked' || status === 'expired') {
    await json(route, 410, {
      detail: 'انتهى هذا الرابط — الجرد رُحِّل أو انتهت صلاحية الرابط. راجع المسؤول.',
    });
    return true;
  }

  if (method === 'GET') {
    backend.publicReads += 1;
    if (backend.publicReadFailure) {
      await json(route, backend.publicReadFailure, { detail: 'حاول بعد قليل.' });
      return true;
    }
    if (backend.leakMoneyFields) backend.publicLeaks += 1;
    await json(route, 200, publicCountPayload(link, stocktake, backend));
    return true;
  }

  if (method !== 'POST') {
    await json(route, 405, { detail: 'الطريقة غير مدعومة.' });
    return true;
  }

  const body = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
  const rawEntries = body.entries ?? [];
  const finished = body.finished ?? false;
  if (!Array.isArray(rawEntries)) {
    await json(route, 400, { entries: ['قائمة العدّ يجب أن تكون مصفوفة.'] });
    return true;
  }
  if (rawEntries.length > 500) {
    await json(route, 400, { entries: ['الحدّ الأقصى 500 سطراً في الطلب الواحد.'] });
    return true;
  }
  if (typeof finished !== 'boolean') {
    await json(route, 400, { finished: ['قيمة finished يجب أن تكون true أو false.'] });
    return true;
  }

  const errors: Record<string, unknown> = {};
  const parsed: Array<{ lineId: number; sent: string | null; stored: string | null }> = [];
  rawEntries.forEach((raw, index) => {
    if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) {
      // `_parse_count_entries`: رسالةُ سطرٍ ليس كائناً **قائمةٌ** لا خريطة حقل.
      errors[String(index)] = ['سطر العدّ غير صالح.'];
      return;
    }
    const entry = raw as Record<string, unknown>;
    const rawId = entry.line_id;
    const lineId = typeof rawId === 'number'
      ? rawId
      : typeof rawId === 'string' && /^[0-9]{1,18}$/.test(rawId.trim())
        ? Number(rawId.trim())
        : NaN;
    if (!Number.isInteger(lineId) || lineId < 1) {
      errors[String(index)] = { line_id: ['معرّف البند غير صالح.'] };
      return;
    }
    if (!('counted_quantity' in entry)) {
      errors[String(index)] = { counted_quantity: ['الكمية مطلوبة — استعمل null للمسح.'] };
      return;
    }
    const quantity = parseQuantity(entry.counted_quantity);
    if (!quantity.ok) {
      errors[String(index)] = {
        counted_quantity: [INVALID_QUANTITY_MESSAGE],
      };
      return;
    }
    parsed.push({
      lineId,
      sent: entry.counted_quantity == null ? null : String(entry.counted_quantity),
      stored: quantity.value,
    });
  });
  if (Object.keys(errors).length) {
    await json(route, 400, { entries: errors });
    return true;
  }

  const attempt: PublicCountWrite = {
    entries: parsed.map((row) => ({
      line_id: row.lineId,
      counted_quantity: row.sent,
    })),
    finished,
  };
  backend.publicAttempts.push(attempt);
  // لقطة الرفض عند **وصول** الطلب: الخادم يقرّر في زمن المعالجة، لا في زمن
  // الردّ المتأخّر — وبها يستطيع الاختبار إزالة الرفض فور تعديل القيمة.
  const rejectedIds = [...backend.rejectLineIds];
  if (backend.delayWritesMs > 0) {
    // الردّ يتأخّر بعد وصول الطلب — تعديلٌ يقع في هذه النافذة هو محلّ الاختبار.
    await new Promise((resolve) => { setTimeout(resolve, backend.delayWritesMs); });
  }
  if (backend.publicWriteFailure) {
    await json(route, backend.publicWriteFailure, { detail: 'تعذّر الحفظ الآن.' });
    return true;
  }
  if (rejectedIds.length) {
    const rejected: Record<string, unknown> = {};
    rawEntries.forEach((raw, index) => {
      const entry = raw as Record<string, unknown>;
      const lineId = Number(entry.line_id);
      if (rejectedIds.includes(lineId)) {
        rejected[String(index)] = { counted_quantity: [INVALID_QUANTITY_MESSAGE] };
      }
    });
    if (Object.keys(rejected).length) {
      backend.publicRejects += 1;
      await json(route, 400, { entries: rejected });
      return true;
    }
  }

  let written = 0;
  let ignored = 0;
  for (const row of parsed) {
    const line = lineInStocktake(stocktake, row.lineId);
    if (!line || !inCountScope(line, link.categories)) {
      ignored += 1;
      continue;
    }
    line.counted = row.stored;
    line.by = row.stored == null ? '' : link.counter_name;
    line.at = row.stored == null ? null : nowIso();
    written += 1;
  }
  if (finished && link.finished_at == null) link.finished_at = nowIso();
  if (written) {
    stocktake.updated_at = nowIso();
    // الخادم يحرّك ختم الجرد فيتقادم ETag المدير — والمحاكي يفعلها كي يبقى
    // اختبار «عدّ موظف لا يُمحى بحفظٍ قديم» صادقاً. و`finished` وحده **لا**
    // يحرّك الختم (`write_stocktake_count`: `if changed:` حول `locked.save`).
    backend.touchStocktake(stocktake.id);
  }
  backend.publicWrites.push(attempt);
  await json(route, 200, {
    written,
    ignored,
    finished: link.finished_at != null,
  });
  return true;
}

/** مسارات المدير: قائمة/إنشاء/إبطال تحت `stocktakes/<id>/count-links/`. */
async function serveAdminCount(
  route: Route, backend: CountApiBackend, path: string, method: string,
): Promise<boolean> {
  const revokeMatch = path.match(
    /\/inventory\/stocktakes\/(\d+)\/count-links\/(\d+)\/revoke\/$/,
  );
  if (revokeMatch && method === 'POST') {
    const stocktake = backend.stocktakes.find((row) => row.id === Number(revokeMatch[1]));
    const link = backend.links.find(
      (row) => row.id === Number(revokeMatch[2]) && row.stocktakeId === stocktake?.id,
    );
    if (!stocktake || !link) {
      await json(route, 404, { detail: 'الرابط غير موجود.' });
      return true;
    }
    link.revoked_at = nowIso();
    await json(route, 200, countLinkRow(link, stocktake));
    return true;
  }

  const listMatch = path.match(/\/inventory\/stocktakes\/(\d+)\/count-links\/$/);
  if (!listMatch || (method !== 'GET' && method !== 'POST')) return false;
  const stocktake = backend.stocktakes.find((row) => row.id === Number(listMatch[1]));
  if (!stocktake) {
    await json(route, 404, { detail: 'No Stocktake matches the given query.' });
    return true;
  }

  if (method === 'GET') {
    backend.adminReads += 1;
    const rows = backend.links
      .filter((row) => row.stocktakeId === stocktake.id)
      .sort((a, b) => b.id - a.id)
      .map((row) => countLinkRow(row, stocktake));
    await json(route, 200, rows);
    return true;
  }

  if (stocktake.is_posted) {
    await json(route, 400, { error: 'لا يمكن إنشاء رابط عدّ لجرد مُرحَّل.' });
    return true;
  }
  const body = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
  const counterName = String(body.counter_name ?? '').trim();
  if (!counterName) {
    await json(route, 400, { counter_name: ['اسم الموظف مطلوب.'] });
    return true;
  }
  if (counterName.length > 80) {
    await json(route, 400, { counter_name: ['اسم الموظف 80 محرفاً كحدّ أقصى.'] });
    return true;
  }
  const rawDays = body.days ?? 3;
  if (typeof rawDays === 'boolean' || !['1', '3', '7'].includes(String(rawDays).trim())) {
    await json(route, 400, { days: ['مدة الصلاحية يجب أن تكون 1 أو 3 أو 7 أيام.'] });
    return true;
  }
  const days = Number(String(rawDays).trim());

  let categories: number[] | null = null;
  const rawCategories = body.categories;
  if (rawCategories !== undefined && rawCategories !== null) {
    if (!Array.isArray(rawCategories) || !rawCategories.length) {
      await json(route, 400, {
        categories: ['اختر تصنيفاً واحداً على الأقل، أو اتركه فارغاً للجرد كلّه.'],
      });
      return true;
    }
    if (rawCategories.some((value) => typeof value !== 'number' || !Number.isInteger(value))) {
      await json(route, 400, { categories: ['معرّف التصنيف غير صالح.'] });
      return true;
    }
    const tenantCategoryIds = new Set(STUB_CATEGORIES.map((row) => row.id));
    const missing = (rawCategories as number[]).filter((id) => !tenantCategoryIds.has(id));
    if (missing.length) {
      await json(route, 400, {
        categories: [`تصنيفات غير موجودة لهذه الشركة: ${missing.join('، ')}`],
      });
      return true;
    }
    const lineCategoryIds = new Set(
      stocktake.lines
        .map((line) => lineCategoryOf(line))
        .filter((id): id is number => id != null),
    );
    const outside = (rawCategories as number[]).filter((id) => !lineCategoryIds.has(id));
    if (outside.length) {
      await json(route, 400, {
        categories: [`تصنيفات لا بنود لها في هذا الجرد: ${outside.join('، ')}`],
      });
      return true;
    }
    categories = [...new Set(rawCategories as number[])].sort((a, b) => a - b);
  }

  backend.nextTokenSeq += 1;
  const link: StubCountLink = {
    id: backend.nextLinkId++,
    stocktakeId: stocktake.id,
    token: `count-token-${backend.nextTokenSeq}`,
    counter_name: counterName,
    categories,
    expires_at: new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString(),
    finished_at: null,
    revoked_at: null,
    created_at: nowIso(),
  };
  backend.links.push(link);
  await json(route, 201, countLinkRow(link, stocktake));
  return true;
}

export async function installStocktakeApiStubs(
  page: Page,
): Promise<StocktakeStubHandle> {
  const initial: InternalStocktake = {
    id: 900,
    number: 'JRD-0001',
    date: '2026-10-20',
    warehouse: null,
    notes: 'جرد افتتاحي',
    scope: { all: false, categories: [11, 14], uncategorized: false, include_inactive: false },
    is_posted: false,
    journal: null,
    lines: [
      {
        id: 1, product: 101, counted: null, by: '', at: null,
        system_quantity: null, variance: null,
      },
      {
        id: 2, product: 105, counted: '4.0000', by: 'مدير الجرد', at: '2026-10-20T09:15:00Z',
        system_quantity: null, variance: null,
      },
      {
        id: 3, product: 106, counted: null, by: '', at: null,
        system_quantity: null, variance: null,
      },
    ],
    created_by: 1,
    created_by_name: 'مدير الجرد',
    created_at: '2026-10-20T08:00:00Z',
    updated_at: '2026-10-20T09:15:00Z',
  };
  const stocktakes: InternalStocktake[] = [
    initial,
    // جردٌ ثانٍ: فتحُه بينما الأول مفتوح هو حالة «مستندٌ آخر» في اختبارات المسودّة.
    {
      id: 950,
      number: 'JRD-0002',
      date: '2026-10-21',
      warehouse: 2,
      notes: '',
      scope: { all: false, categories: [14], uncategorized: false, include_inactive: false },
      is_posted: false,
      journal: null,
      lines: [
        {
          id: 4, product: 107, counted: '2.0000', by: 'مدير آخر', at: '2026-10-21T10:00:00Z',
          system_quantity: null, variance: null,
        },
        {
          id: 5, product: 108, counted: null, by: '', at: null,
          system_quantity: null, variance: null,
        },
      ],
      created_by: 1,
      created_by_name: 'مدير الجرد',
      created_at: '2026-10-21T08:00:00Z',
      updated_at: '2026-10-21T10:00:00Z',
    },
    // جردٌ بلا أيّ عدٍّ بعد — «لم يبدأ» في K4 حالةٌ حقيقية لا تُصنع بجردٍ
    // فيه سطرٌ معدودٌ سلفاً (JRD-0001 فيه عدُّ مدير).
    {
      id: 960,
      number: 'JRD-0003',
      date: '2026-10-22',
      warehouse: 1,
      notes: 'جرد رابط الموظف',
      scope: { all: false, categories: [11, 14], uncategorized: false, include_inactive: false },
      is_posted: false,
      journal: null,
      lines: [
        {
          id: 6, product: 101, counted: null, by: '', at: null,
          system_quantity: null, variance: null,
        },
        {
          id: 7, product: 102, counted: null, by: '', at: null,
          system_quantity: null, variance: null,
        },
        {
          id: 8, product: 106, counted: null, by: '', at: null,
          system_quantity: null, variance: null,
        },
      ],
      created_by: 1,
      created_by_name: 'مدير الجرد',
      created_at: '2026-10-22T08:00:00Z',
      updated_at: '2026-10-22T08:00:00Z',
    },
  ];
  const countBackend: CountApiBackend = {
    stocktakes,
    links: [],
    publicWrites: [],
    publicAttempts: [],
    publicRejects: 0,
    publicReads: 0,
    adminReads: 0,
    publicWriteFailure: null,
    publicReadFailure: null,
    rejectLineIds: [],
    delayWritesMs: 0,
    leakMoneyFields: false,
    publicLeaks: 0,
    nextLinkId: 1,
    nextTokenSeq: 0,
    touchStocktake: (id) => bumpEtag(id),
  };
  let stocktakeGetCount = 0;
  let nextStocktakeId = 901;
  let nextLineId = 10;
  // توكنٌ لكل مستند — لا عدّادٌ عالميّ: تعديل جردٍ لا يجوز أن يُبطل توكن آخر.
  const etags = new Map<number, string>();
  let etagCounter = 0;
  const issueEtag = (stocktakeId: number): string => {
    etagCounter += 1;
    const value = `"${stocktakeId}-${etagCounter}"`;
    etags.set(stocktakeId, value);
    return value;
  };
  issueEtag(initial.id);
  issueEtag(950);
  issueEtag(960);
  const bumpEtag = (stocktakeId = initial.id) => { issueEtag(stocktakeId); };
  const currentEtag = (stocktakeId = initial.id) => {
    const value = etags.get(stocktakeId);
    return value ?? issueEtag(stocktakeId);
  };
  const scopeCountsDelays: number[] = [];
  const stocktakeGetDelays: number[] = [];
  let scopeCountsFailure = false;
  let scopeProductFailure: number | null = null;

  const handle: StocktakeStubHandle = {
    productListCallsWithoutSearch: [],
    productListCallsWithSearch: [],
    scopeProductRequests: [],
    createdBodies: [],
    saveRequests: [],
    postRequests: [],
    bumpEtag,
    delayNextScopeCounts: (ms) => { scopeCountsDelays.push(ms); },
    delayNextStocktakeGet: (ms) => { stocktakeGetDelays.push(ms); },
    setScopeCountsFailure: (fail) => { scopeCountsFailure = fail; },
    setScopeProductFailure: (status) => { scopeProductFailure = status; },
    scopeCountsDelayedAnswered: 0,
    setServerCounted: (product, quantity, by = 'مدير آخر') => {
      const line = initial.lines.find((row) => row.product === product);
      if (line) {
        const parsed = quantity == null ? null : parseQuantity(quantity);
        line.counted = parsed == null ? null : (parsed.ok ? parsed.value : null);
        line.by = quantity == null ? '' : by;
        line.at = quantity == null ? null : nowIso();
      }
      // الخادم يحرّك ختم المستند وتوكنه مع أي تعديل بند (ETag من `updated_at`)،
      // فمسودّةٌ كُتبت قبله تصير «قديمة» — وتُعرض في شريط «تغيّر المستند» لا
      // تُستعاد صامتة. محاكيٌ لا يحرّكهما يختبر مساراً لا وجود له في الإنتاج.
      initial.updated_at = nowIso();
      issueEtag(initial.id);
    },
    setServerNotes: (notes) => {
      // تغييرُ الرأس تعديلُ مستندٌ كامل: يحرّك `updated_at` والتوكن كذلك.
      initial.notes = notes;
      initial.updated_at = nowIso();
      issueEtag(initial.id);
    },
    currentEtag: (stocktakeId) => currentEtag(stocktakeId),
    countBackend,
    get stocktakeGetCount() { return stocktakeGetCount; },
    setPublicWriteFailure: (status) => { countBackend.publicWriteFailure = status; },
    setPublicReadFailure: (status) => { countBackend.publicReadFailure = status; },
    moveLineOutOfScope: (lineId) => {
      for (const stocktake of countBackend.stocktakes) {
        const line = stocktake.lines.find((row) => row.id === lineId);
        if (!line) continue;
        // تصنيف «محركات» (12) خارج نطاقَي JRD-0003 (11/14): السطر يخرج من كل
        // رابطٍ مقيَّد بهذين التصنيفين، ويبقى في «كل الجرد» كما يفعل الخادم.
        line.product = 104;
        stocktake.updated_at = nowIso();
      }
    },
  };

  await page.addInitScript(() => {
    localStorage.setItem('token', 'stocktake-e2e-token');
    localStorage.setItem('userId', 'stocktake-e2e-user');
    localStorage.setItem('tenantId', '1');
  });

  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();

    const path = url.pathname;
    const method = route.request().method();
    const search = url.searchParams.get('search');

    // K4 — سطح العدّ العامّ وروابط العدّ الإدارية قبل أيّ مسارٍ آخر.
    if (await serveCountShare(route, countBackend)) return;
    if (await serveAdminCount(route, countBackend, path, method)) return;

    // 3) كل طلب كتالوج بلا استعلام بحثٍ يُسجَّل — وجوده يعني تنزيل كتالوج.
    if (method === 'GET' && path.endsWith('/inventory/products/')) {
      if (search) handle.productListCallsWithSearch.push(route.request().url());
      else handle.productListCallsWithoutSearch.push(route.request().url());
      const rows = STUB_PRODUCTS.filter((product) => {
        if (!search) return true;
        const needle = search.toLocaleLowerCase('ar');
        return [
          product.sku, product.name_ar, product.name_en, product.display_name, product.brand,
          categoryName(product.category),
        ].some((value) => value.toLocaleLowerCase('ar').includes(needle));
      });
      await json(route, 200, {
        count: rows.length,
        next: null,
        previous: null,
        results: rows,
      });
      return;
    }

    // عدّادات النطاق — نفس قاعدة توليد البنود.
    if (method === 'GET' && path.endsWith('/inventory/stocktakes/scope-counts/')) {
      if (scopeCountsDelays.length) {
        const wait = scopeCountsDelays.shift() ?? 0;
        if (wait) {
          await new Promise((resolve) => { setTimeout(resolve, wait); });
          handle.scopeCountsDelayedAnswered += 1;
        }
      }
      if (scopeCountsFailure) {
        await json(route, 500, { detail: 'تعذّر حساب عدد المنتجات' });
        return;
      }
      const raw = url.searchParams.get('include_inactive');
      if (raw !== null && raw !== 'true' && raw !== 'false') {
        await json(route, 400, {
          error: 'قيمة include_inactive يجب أن تكون true أو false',
        });
        return;
      }
      await json(route, 200, countsFor(raw === 'true'));
      return;
    }

    // ST-2: المنتجات المباشرة لتصنيفٍ واحد — الرسائل والترتيب كما في ST-1.
    if (method === 'GET' && path.endsWith('/inventory/stocktakes/scope-products/')) {
      handle.scopeProductRequests.push(route.request().url());
      if (scopeProductFailure) {
        await json(route, scopeProductFailure, { detail: 'تعذّر تحميل منتجات التصنيف' });
        return;
      }
      const rawCategory = url.searchParams.get('category');
      const rawInactive = url.searchParams.get('include_inactive');
      const text = (rawCategory ?? '').trim();
      const category = rawCategory === 'none'
        ? null
        : (/^[+-]?\d+$/.test(text) ? Number(text) : undefined);
      if (category === undefined) {
        await json(route, 400, {
          category: ['معرّف التصنيف يجب أن يكون عدداً صحيحاً أو none'],
        });
        return;
      }
      if (rawInactive !== null && rawInactive !== 'true' && rawInactive !== 'false') {
        await json(route, 400, {
          error: 'قيمة include_inactive يجب أن تكون true أو false',
        });
        return;
      }
      if (category !== null && !STUB_CATEGORIES.some((row) => row.id === category)) {
        await json(route, 400, { category: ['تصنيف غير موجود لهذه الشركة'] });
        return;
      }
      await json(route, 200, scopeProductsFor(category, rawInactive === 'true'));
      return;
    }

    // إنشاء جرد من نطاق (أو يدوي بلا بنود).
    if (method === 'POST' && path.endsWith('/inventory/stocktakes/')) {
      const body = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      handle.createdBodies.push(body);
      if ('scope' in body && 'lines' in body) {
        await json(route, 400, {
          non_field_errors: ['اختر نطاقاً أو بنوداً لا الاثنين'],
        });
        return;
      }
      if (body.scope == null) {
        if (Array.isArray(body.lines) && body.lines.length) {
          await json(route, 400, { error: 'إنشاء يدوي ببنود غير مدعوم في هذا المحاكي' });
          return;
        }
        const created: InternalStocktake = {
          id: nextStocktakeId++, number: '', date: String(body.stocktake_date ?? ''),
          warehouse: body.warehouse == null ? null : Number(body.warehouse),
          notes: String(body.notes ?? ''), scope: null, is_posted: false, journal: null,
          lines: [], created_by: 1, created_by_name: 'مدير الجرد',
          created_at: nowIso(), updated_at: nowIso(),
        };
        stocktakes.push(created);
        await json(route, 201, stocktakeView(created), {
          ETag: currentEtag(created.id),
        });
        return;
      }

      const scope = body.scope as Record<string, unknown>;
      if (typeof scope !== 'object' || Array.isArray(scope)) {
        await json(route, 400, { scope: ['نطاق الجرد غير صالح'] });
        return;
      }
      const keys = Object.keys(scope);
      if (keys.some((key) => !['all', 'categories', 'uncategorized', 'include_inactive', 'products'].includes(key))) {
        await json(route, 400, { scope: ['مفتاح غير معروف في نطاق الجرد'] });
        return;
      }
      for (const key of ['all', 'uncategorized', 'include_inactive']) {
        if (key in scope && typeof scope[key] !== 'boolean') {
          await json(route, 400, { scope: [`قيمة «${key}» في نطاق الجرد يجب أن تكون صحيحاً أو خطأً`] });
          return;
        }
      }
      const categories = scope.categories ?? [];
      if (!Array.isArray(categories) || categories.some((id) => typeof id !== 'number')) {
        await json(route, 400, { scope: ['قائمة التصنيفات في نطاق الجرد غير صالحة'] });
        return;
      }
      const known = new Set(STUB_CATEGORIES.map((row) => row.id));
      const missing = (categories as number[]).filter((id) => !known.has(id));
      if (missing.length) {
        await json(route, 400, {
          scope: [`تصنيفات غير موجودة لهذه الشركة: ${missing.join('، ')}`],
        });
        return;
      }
      // ST-1: `products` — قائمةٌ ثم أعداداً صحيحةً ثم السقف ثم الوجود ثم الأهلية،
      // بالترتيب نفسه والرسائل نفسها.
      const rawProducts = scope.products ?? [];
      if (!Array.isArray(rawProducts)) {
        await json(route, 400, { scope: ['قائمة المنتجات في نطاق الجرد غير صالحة'] });
        return;
      }
      if (rawProducts.some((id) => typeof id !== 'number' || !Number.isInteger(id))) {
        await json(route, 400, { scope: ['معرّفات المنتجات يجب أن تكون أعداداً صحيحة'] });
        return;
      }
      if (rawProducts.length > STOCKTAKE_SCOPE_MAX_PRODUCTS) {
        await json(route, 400, {
          scope: [`الحد الأقصى ${STOCKTAKE_SCOPE_MAX_PRODUCTS} منتج في الجرد الواحد`],
        });
        return;
      }
      const products = [...new Set(rawProducts as number[])].sort((a, b) => a - b);
      const missingProducts = products.filter((id) => !productOf(id));
      if (missingProducts.length) {
        await json(route, 400, {
          scope: [`منتجات غير موجودة لهذه الشركة: ${missingProducts.join('، ')}`],
        });
        return;
      }
      const includeInactive = scope.include_inactive === true;
      const rejectedProducts = products.filter((id) => {
        const product = productOf(id);
        return product?.is_service || (!product?.is_active && !includeInactive);
      });
      if (rejectedProducts.length) {
        await json(route, 400, {
          scope: [`منتجات لا تدخل هذا الجرد (خدمة أو غير فعّال): ${rejectedProducts.join('، ')}`],
        });
        return;
      }
      const all = scope.all === true;
      const uncategorized = scope.uncategorized === true;
      const selected = new Set(categories as number[]);
      // الإسقاط لا الرفض: `all` يُسقطها، وما يغطّيه تصنيفٌ مؤشَّر أو «بدون تصنيف» يُسقَط.
      const explicit = new Set(all ? [] : products.filter((id) => {
        const category = productOf(id)?.category ?? null;
        return !(selected.has(category as number) || (category == null && uncategorized));
      }));
      if (!all && !categories.length && !uncategorized && !explicit.size) {
        await json(route, 400, { scope: ['اختر تصنيفاً واحداً على الأقل'] });
        return;
      }
      const eligible = STUB_PRODUCTS.filter((product) => {
        if (product.is_service) return false;
        if (!includeInactive && !product.is_active) return false;
        if (all) return true;
        if (explicit.has(product.id)) return true;
        if (product.category == null) return uncategorized;
        return selected.has(product.category);
      });
      if (!eligible.length) {
        await json(route, 400, { scope: ['لا منتجات في هذا الاختيار'] });
        return;
      }
      // التخزين عند عدم الفراغ وحده — و`products: []` ضجيجٌ لا يُخزَّن.
      const storedScope: Record<string, unknown> = {
        all,
        categories: [...selected].sort((a, b) => a - b),
        uncategorized,
        include_inactive: includeInactive,
      };
      if (explicit.size) storedScope.products = [...explicit].sort((a, b) => a - b);
      const created: InternalStocktake = {
        id: nextStocktakeId++,
        number: '',
        date: String(body.stocktake_date ?? ''),
        warehouse: body.warehouse == null ? null : Number(body.warehouse),
        notes: String(body.notes ?? ''),
        scope: storedScope,
        is_posted: false,
        journal: null,
        lines: eligible.map((product) => ({
          id: nextLineId++, product: product.id, counted: null, by: '', at: null,
          system_quantity: null, variance: null,
        })),
        created_by: 1,
        created_by_name: 'مدير الجرد',
        created_at: nowIso(),
        updated_at: nowIso(),
      };
      stocktakes.push(created);
      await json(route, 201, stocktakeView(created), {
        ETag: currentEtag(created.id),
      });
      return;
    }

    // قائمة الجرد — ملخّص بلا بنود.
    if (method === 'GET' && path.endsWith('/inventory/stocktakes/')) {
      await json(route, 200, stocktakes.map(stocktakeSummary));
      return;
    }

    const postMatch = path.match(/\/inventory\/stocktakes\/(\d+)\/post\/$/);
    if (postMatch && method === 'POST') {
      const stocktake = stocktakes.find((row) => row.id === Number(postMatch[1]));
      if (!stocktake) {
        await json(route, 404, { detail: 'No Stocktake matches the given query.' });
        return;
      }
      const body = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      handle.postRequests.push(body);
      const flag = body.uncounted_as_zero ?? false;
      if (typeof flag !== 'boolean') {
        await json(route, 400, { error: 'قيمة uncounted_as_zero يجب أن تكون true أو false' });
        return;
      }
      const uncounted = stocktake.lines.filter((line) => line.counted == null);
      if (stocktake.lines.length && uncounted.length === stocktake.lines.length && !flag) {
        await json(route, 400, {
          error: 'لم يُعدّ أيّ بند — أدخل الكميات أو اختر «اعتبرها صفراً»',
        });
        return;
      }
      if (!stocktake.lines.length) {
        await json(route, 400, { error: 'أضف بنداً واحداً على الأقل.' });
        return;
      }
      if (flag) {
        for (const line of uncounted) {
          line.counted = '0.0000';
          line.by = 'مدير الجرد';
          line.at = nowIso();
        }
      }
      // لقطة رصيد النظام والفرق كما في `post_stocktake`: المستثنى غير المعدود
      // يأخذ رصيده وفرقاً صفراً، والمعدود فرقه = المعدود − رصيد اللحظة.
      for (const line of stocktake.lines) {
        const parsedBalance = parseQuantity(
          productOf(line.product)?.quantity_on_hand ?? '0',
        );
        const system = parsedBalance.ok ? parsedBalance.value : '0.0000';
        line.system_quantity = system;
        line.variance = line.counted == null
          ? '0.0000'
          : (Number(line.counted) - Number(system)).toFixed(4);
      }
      stocktake.is_posted = true;
      stocktake.journal = 77;
      stocktake.number = stocktake.number || 'JRD-0007';
      stocktake.updated_at = nowIso();
      // `post_stocktake` يُبطل كل روابط الجرد في المعاملة نفسها.
      for (const link of countBackend.links) {
        if (link.stocktakeId === stocktake.id && !link.revoked_at) {
          link.revoked_at = nowIso();
        }
      }
      bumpEtag(stocktake.id);
      await json(route, 200, stocktakeView(stocktake), {
        ETag: currentEtag(stocktake.id),
      });
      return;
    }

    const detailMatch = path.match(/\/inventory\/stocktakes\/(\d+)\/$/);
    if (detailMatch && (method === 'GET' || method === 'PATCH')) {
      const stocktake = stocktakes.find((row) => row.id === Number(detailMatch[1]));
      if (!stocktake) {
        await json(route, 404, { detail: 'No Stocktake matches the given query.' });
        return;
      }
      if (method === 'GET') {
        stocktakeGetCount += 1;
        if (stocktakeGetDelays.length) {
          const wait = stocktakeGetDelays.shift() ?? 0;
          if (wait) await new Promise((resolve) => { setTimeout(resolve, wait); });
        }
        await json(route, 200, stocktakeView(stocktake), {
          ETag: currentEtag(stocktake.id),
        });
        return;
      }

      const ifMatch = route.request().headers()['if-match'] ?? null;
      const body = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      // كل محاولةٍ تُسجَّل حتى المرفوضة بـ412 — الاختبار يقيس ما أُرسل فعلاً.
      handle.saveRequests.push({ ifMatch, body });
      const documentEtag = currentEtag(stocktake.id);
      if (ifMatch && ifMatch !== '*' && ifMatch !== documentEtag) {
        await json(route, 412, {
          error: 'المستند عُدّل منذ قراءتك — أعد قراءته ثم أعد التعديل',
          code: 'stale_document',
          current_etag: documentEtag,
          updated_at: stocktake.updated_at,
        }, { ETag: documentEtag });
        return;
      }
      if (stocktake.is_posted) {
        await json(route, 400, { error: 'لا يمكن تعديل جرد مُرحَّل.' });
        return;
      }
      if ('scope' in body && !scopeEquals(body.scope, stocktake.scope)) {
        await json(route, 400, { scope: ['النطاق يُحدَّد عند إنشاء الجرد فقط'] });
        return;
      }

      const replaceLines = body.replace_lines === true;
      const rows = body.lines;
      if (rows != null) {
        if (!Array.isArray(rows)) {
          await json(route, 400, { lines: ['Expected a list of items.'] });
          return;
        }
        const seen = new Set<number>();
        const parsedRows: Array<{ productId: number; quantity: string | null }> = [];
        for (const row of rows as Array<Record<string, unknown>>) {
          if (!('counted_quantity' in row)) {
            await json(route, 400, {
              lines: [{ counted_quantity: ['هذا الحقل مطلوب.'] }],
            });
            return;
          }
          const productId = Number(row.product);
          if (seen.has(productId)) {
            // `StocktakeSerializer.validate_lines` يرفع الخطأ على حقل `lines` نفسه.
            await json(route, 400, {
              lines: [
                `المنتج «${productOf(productId)?.display_name ?? productId}» مكرَّر في بنود `
                + 'الجرد — ادمج كمياته في بند واحد.',
              ],
            });
            return;
          }
          seen.add(productId);
          if (!productOf(productId)) {
            await json(route, 400, {
              lines: [{ product: [`Invalid pk "${productId}" - object does not exist.`] }],
            });
            return;
          }
          const parsed = parseQuantity(row.counted_quantity);
          if (!parsed.ok) {
            await json(route, 400, {
              lines: [{
                counted_quantity: [
                  'كمية غير صالحة — رقمٌ غير سالب بأربع منازل عشرية على الأكثر.',
                ],
              }],
            });
            return;
          }
          parsedRows.push({ productId, quantity: parsed.value });
        }
        const kept: InternalLine[] = [];
        for (const row of parsedRows) {
          let line = stocktake.lines.find((item) => item.product === row.productId);
          if (!line) {
            line = {
              id: nextLineId++, product: row.productId, counted: null, by: '', at: null,
              system_quantity: null, variance: null,
            };
          }
          // المقارنة عددية: «5» و«5.0000» كميةٌ واحدة — لا خاتمَ جديداً لقيمةٍ لم تتغيّر.
          if (line.counted !== row.quantity) {
            line.counted = row.quantity;
            line.by = row.quantity == null ? '' : 'مدير الجرد';
            line.at = row.quantity == null ? null : nowIso();
          }
          kept.push(line);
        }
        stocktake.lines = replaceLines
          ? kept
          : [
            ...stocktake.lines.filter((line) => !seen.has(line.product)),
            ...kept,
          ];
      }
      // `replace_lines` بلا `lines` يُهمَل — الخادم: `if lines is not None` وحدها.
      if (typeof body.stocktake_date === 'string') stocktake.date = body.stocktake_date;
      if ('warehouse' in body) {
        stocktake.warehouse = body.warehouse == null ? null : Number(body.warehouse);
      }
      if (typeof body.notes === 'string') stocktake.notes = body.notes;
      stocktake.updated_at = nowIso();
      bumpEtag(stocktake.id);
      await json(route, 200, stocktakeView(stocktake), {
        ETag: currentEtag(stocktake.id),
      });
      return;
    }

    // جلسة التطبيق — نفس عقد `items-tree-stubs`.
    let body: unknown = [];
    if (path.endsWith('/hr/users/stocktake-e2e-user/')) {
      body = {
        id: 'stocktake-e2e-user', name: 'مدير الجرد', role: 'manager',
        email: 'stocktake@example.test', employmentStatus: 'active',
        isApproved: true, isEmailVerified: true,
      };
    } else if (path.endsWith('/tenants/companies/my-companies/')) {
      body = [{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الجرد', SubscriptionPlan: 'Enterprise',
          Status: 'Active', CreatedAt: '2026-07-22T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true, created_at: '2026-07-22T00:00:00Z',
        can_access_import: false,
      }];
    } else if (path.endsWith('/permissions/me/')) {
      body = {
        role: 'manager', is_manager: true, ui_mode: 'advanced',
        permissions: [
          'inventory.item.view', 'inventory.item.manage',
          'inventory.doc.post', 'inventory.doc.unpost',
        ],
      };
    } else if (path.endsWith('/inventory/categories/')) {
      body = STUB_CATEGORIES;
    } else if (path.endsWith('/inventory/warehouses/')) {
      body = WAREHOUSES;
    }
    await json(route, 200, body);
  });

  return handle;
}

/**
 * K4 — محاكي الصفحة العامة وحدها، في سياق متصفّحٍ **بلا جلسة**: لا
 * `addInitScript` ولا توكن. الحالةُ مشتركة مع محاكي المدير عبر `countBackend`,
 * فما يكتبه الموظف هنا يقرأه المدير هناك.
 */
export async function installPublicCountStubs(
  page: Page,
  backend: CountApiBackend,
): Promise<void> {
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    if (await serveCountShare(route, backend)) return;
    return route.continue();
  });
}
