import { Page, type Route } from '@playwright/test';

/**
 * K2 — محاكي الجرد: نفس عقد `inventory/serializers.py` (بنود بلا أسعار ولا
 * تكاليف)، ويرفض ما يرفضه الخادم فعلاً:
 *   - `scope` و`lines` معاً ⇒ 400، ونطاقٌ فارغ ⇒ 400، وتصنيفٌ خارج الشركة ⇒ 400.
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

export type StocktakeStubHandle = {
  /** طلبات قائمة المنتجات بلا `search` — يجب أن تبقى صفراً. */
  productListCallsWithoutSearch: string[];
  productListCallsWithSearch: string[];
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
};

const nowIso = () => new Date().toISOString();

/** كميةٌ كما يقبلها `CountedQuantityField`: null، أو رقمٌ غير سالب بأربع منازل. */
const QUANTITY_TEXT = /^(?:\d+(?:\.\d*)?|\.\d+)$/;

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

/** مقارنة النطاق بالقيمة لا بترتيب المفاتيح (الخادم يقارن القاموس المخزَّن). */
const scopeEquals = (a: unknown, b: unknown): boolean => {
  if (a == null || b == null || typeof a !== 'object' || typeof b !== 'object') {
    return a === b;
  }
  const left = a as Record<string, unknown>;
  const right = b as Record<string, unknown>;
  const categories = (value: unknown) => (
    Array.isArray(value) ? [...value].map(Number).sort((x, y) => x - y) : value
  );
  return left.all === right.all
    && left.uncategorized === right.uncategorized
    && left.include_inactive === right.include_inactive
    && JSON.stringify(categories(left.categories))
      === JSON.stringify(categories(right.categories));
};

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
      ...headers,
    },
    body: JSON.stringify(body),
  });

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
  ];
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
  const bumpEtag = (stocktakeId = initial.id) => { issueEtag(stocktakeId); };
  const currentEtag = (stocktakeId = initial.id) => {
    const value = etags.get(stocktakeId);
    return value ?? issueEtag(stocktakeId);
  };
  const scopeCountsDelays: number[] = [];
  const stocktakeGetDelays: number[] = [];
  let scopeCountsFailure = false;

  const handle: StocktakeStubHandle = {
    productListCallsWithoutSearch: [],
    productListCallsWithSearch: [],
    createdBodies: [],
    saveRequests: [],
    postRequests: [],
    bumpEtag,
    delayNextScopeCounts: (ms) => { scopeCountsDelays.push(ms); },
    delayNextStocktakeGet: (ms) => { stocktakeGetDelays.push(ms); },
    setScopeCountsFailure: (fail) => { scopeCountsFailure = fail; },
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
      if (keys.some((key) => !['all', 'categories', 'uncategorized', 'include_inactive'].includes(key))) {
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
      const all = scope.all === true;
      const uncategorized = scope.uncategorized === true;
      if (!all && !categories.length && !uncategorized) {
        await json(route, 400, { scope: ['اختر تصنيفاً واحداً على الأقل'] });
        return;
      }
      const includeInactive = scope.include_inactive === true;
      const selected = new Set(categories as number[]);
      const eligible = STUB_PRODUCTS.filter((product) => {
        if (product.is_service) return false;
        if (!includeInactive && !product.is_active) return false;
        if (all) return true;
        if (product.category == null) return uncategorized;
        return selected.has(product.category);
      });
      if (!eligible.length) {
        await json(route, 400, { scope: ['لا منتجات في هذا الاختيار'] });
        return;
      }
      const created: InternalStocktake = {
        id: nextStocktakeId++,
        number: '',
        date: String(body.stocktake_date ?? ''),
        warehouse: body.warehouse == null ? null : Number(body.warehouse),
        notes: String(body.notes ?? ''),
        scope: {
          all,
          categories: [...new Set(categories as number[])].sort((a, b) => a - b),
          uncategorized,
          include_inactive: includeInactive,
        },
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
