import { humanizeDrfError } from "../utils/drfError";
import { resolveBranchId, resolveTenantId } from "../utils/tenantContext";
import { apiFetch, apiGetList, toPagedList } from "./restApi";

// أبقِ عقد الخدمة كما هو، مع مهلة/إلغاء موحّدين لكل طلباتها.
const fetch = apiFetch;

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
const INV = `${API_BASE}/inventory`;

export interface ProductCostInvoiceRow {
  invoice_id: number;
  invoice_number: string;
  date: string | null;
  party: string | null;
  is_posted: boolean;
  quantity: string;
  invoice_cost: string;
  unit_cost: string;
}

export interface ProductCostBreakdown {
  product_id: number;
  sku: string;
  name: string;
  invoices: ProductCostInvoiceRow[];
  invoice_count: number;
  total_purchased_qty: string;
  average_cost: string;
}

export interface WarehouseStockItem {
  product_id: number;
  sku: string;
  name: string;
  quantity: string;
  avg_cost: string;
  stock_value: string;
}

export interface WarehouseStockDetail {
  warehouse: {
    id: number;
    name: string;
    code?: string;
    location?: string;
    is_default?: boolean;
    is_active?: boolean;
  };
  items: WarehouseStockItem[];
  item_count: number;
  total_value: string;
  valuation_method: "moving_average_cost";
}

/**
 * وحدة مُرقَّمة كما يعيدها الخادم (`inventory/serials.py::_serial_row`) —
 * من أين جاءت الوحدة (فاتورة الشراء ومورّدها) وإلى أين ذهبت (فاتورة البيع وزبونها).
 */
export interface ProductSerialRow {
  id: number;
  serial: string;
  status: "in_stock" | "sold";
  status_display: string;
  product: number;
  product_name: string;
  product_sku: string;
  purchase_invoice: number | null;
  purchase_invoice_number: string | null;
  supplier_name: string | null;
  sales_invoice: number | null;
  sales_invoice_number: string | null;
  customer_name: string | null;
  created_at: string | null;
}

/**
 * محدِّد أعضاء الكرت المجمّع: تصنيفٌ يشتقّه الخادم (`category` — يشمل الأحفاد)،
 * أو منتجٌ (أب) بعينه يشتقّ الخادم كل برانداته (`family` — #23)، أو تعدادٌ
 * صريح (`ids` — مجموعات `group_key`، أو أسطر جردٍ بعينها).
 */
export type ProductGroupSelector = { ids?: number[]; category?: number; family?: number };

/** #21: منتجٌ (عائلة) قائم يطابق الاسم المطبَّع — نتيجة `check-name`. */
export interface ProductNameMatch {
  id: number;
  name_ar: string | null;
  name_en: string | null;
}

/** #21: ردّ `products/add-brand/` — `created` يفرّق بين تسمية الضمنيّ وصفٍّ جديد. */
export interface AddBrandResult {
  id: number;
  sku: string;
  brand: string;
  family_id: number;
  name_ar: string | null;
  name_en: string | null;
  created: boolean;
}

/** #24: ردّ `products/merge/` — المنتجات التي انتقلت فعلاً تحت الهدف (الرفوضة لم تُرسَل أصلاً). */
export interface MergeProductsResult {
  merge_id: number;
  target_family_id: number;
  target_product_id: number;
  merged_product_ids: number[];
}

/** #24: ردّ `products/merge-undo/` — كل ما عاد لأبيه واسمه وبراندِه كما كانوا. */
export interface UndoMergeResult {
  merge_id: number;
  restored_product_ids: number[];
}

/** جسم طلب الكرت المجمّع — يقبل مصفوفة معرّفات كما يقبل المحدِّد الكامل. */
const groupBody = (
  sel: ProductGroupSelector | number[],
  extra: Record<string, unknown> = {},
): string => JSON.stringify(Array.isArray(sel) ? { ids: sel, ...extra } : { ...sel, ...extra });

const headers = (): HeadersInit => {
  const token = localStorage.getItem("token");
  // task11 R2: الشركة النشطة + الفرع النشط مع كل طلب مخزون
  const branchId = resolveBranchId();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Token ${token}` } : {}),
    "X-Tenant-Id": String(resolveTenantId()),
    ...(branchId ? { "X-Branch-Id": String(branchId) } : {}),
  };
};

async function handle(res: Response, ctx: string): Promise<void> {
  if (res.ok) return;
  let msg = `${ctx}: ${res.status}`;
  try {
    // G2: خطأ حقل من DRF ({"barcode": ["…"]}) كان يسقط هنا فيصل للمستخدم «‎: 400»
    // بلا أي سبب — يمرّ الآن على نفس المحوّل الذي يستعمله restApi.
    const humanized = humanizeDrfError(await res.json());
    if (humanized) msg = humanized;
  } catch {
    const t = await res.text();
    if (t) msg = t.slice(0, 400);
  }
  throw new Error(msg);
}

async function asList(res: Response): Promise<any[]> {
  await handle(res, "inventory");
  const data = await res.json();
  return Array.isArray(data) ? data : (data.results ?? []);
}

/** T-SUPSKU: رقم المنتج في كتالوج المورّد (מק"ט) — بياناتٌ رئيسية محايدة مالياً. */
export interface SupplierProductDto {
  id: number;
  supplier: number;
  supplier_display_name?: string;
  product: number;
  product_sku?: string;
  product_display_name?: string;
  supplier_sku: string;
  supplier_name?: string;
  notes?: string;
}

export const inventoryApi = {
  // ─── أرقام المنتجات عند الموردين (T-SUPSKU) ───

  /** أرقام منتجٍ عند مورّديه — لكرت المنتج. */
  listSupplierCodes: (productId: number): Promise<SupplierProductDto[]> =>
    fetch(`${INV}/supplier-products/?product=${productId}`, { headers: headers() })
      .then(asList),

  /** «هذا الرقم — أيّ منتج؟» — مطابقة فاتورة المورّد عكسياً. */
  lookupBySupplierCode: (
    sku: string, supplierId?: number,
  ): Promise<SupplierProductDto[]> => {
    const q = new URLSearchParams({ sku });
    if (supplierId) q.set("supplier", String(supplierId));
    return fetch(`${INV}/supplier-products/?${q}`, { headers: headers() }).then(asList);
  },

  createSupplierCode: async (
    body: Pick<SupplierProductDto, "supplier" | "product" | "supplier_sku">
      & Partial<Pick<SupplierProductDto, "supplier_name" | "notes">>,
  ): Promise<SupplierProductDto> => {
    const res = await fetch(`${INV}/supplier-products/`, {
      method: "POST", headers: headers(), body: JSON.stringify(body),
    });
    // الرسالة الخادمية تسمّي المنتج المالك للرقم — لا تُبتلع.
    await handle(res, "createSupplierCode");
    return res.json();
  },

  deleteSupplierCode: async (id: number): Promise<void> => {
    const res = await fetch(`${INV}/supplier-products/${id}/`, {
      method: "DELETE", headers: headers(),
    });
    if (!res.ok && res.status !== 204) await handle(res, "deleteSupplierCode");
  },

  // ─── Products ───

  getProducts: (params?: Record<string, string | number>) => {
    const q = params && Object.keys(params).length
      ? `?${new URLSearchParams(params as Record<string, string>)}`
      : "";
    return fetch(`${INV}/products/${q}`, { headers: headers() }).then(async (res) => {
      await handle(res, "inventory");
      const data = await res.json();
      return data; // Return full response (might be paginated: {results: [], count: ...})
    });
  },

  /**
   * صفحة واحدة من المنتجات (المرحلة 5 / P0-12).
   * الخادم يدعم search/stock_status/ordering أصلاً (ProductViewSet)، فالبحث
   * والفرز خادميّان ولا حاجة لسحب الجدول كله لتصفيته في المتصفح.
   */
  getProductsPaged: async (params: Record<string, string | number>) => {
    const q = `?${new URLSearchParams(params as unknown as Record<string, string>)}`;
    const res = await fetch(`${INV}/products/${q}`, { headers: headers() });
    await handle(res, "getProductsPaged");
    return toPagedList<any>(await res.json());
  },

  /**
   * كل المنتجات عبر حلقة صفحات. **لا تستخدمها لعرض قائمة** — بقيت لعمليات
   * تحتاج المجموعة كاملةً بطبيعتها (التصدير للطباعة، والعرض الشجري الذي
   * يجمّع حسب التصنيف). العرض الجدولي يستخدم getProductsPaged.
   */
  getAllProducts: async (params?: Record<string, string | number>) => {
    const allRows: any[] = [];
    let pg = 1;
    for (;;) {
      const p = { ...params, page: pg, page_size: 200 };
      const q = `?${new URLSearchParams(p as unknown as Record<string, string>)}`;
      const res = await fetch(`${INV}/products/${q}`, { headers: headers() });
      await handle(res, "inventory");
      const data = await res.json();
      const rows = Array.isArray(data) ? data : (data.results ?? []);
      allRows.push(...rows);
      const count = Array.isArray(data) ? rows.length : (data.count ?? allRows.length);
      if (rows.length === 0 || allRows.length >= count) break;
      pg++;
    }
    return allRows;
  },

  /**
   * T-REORDER: تثبيت الحدّ الأدنى/الأقصى المقترَحين على منتجاتٍ محدَّدة.
   *
   * المحدِّد في **جسم** الطلب لا في عنوانه: تعداد مئات المعرّفات في سطر الطلب
   * ردّه nginx بـ414 في الإنتاج من قبل (كرت المجموعة). والخطأ الخادمي يُرفع
   * كما كتبه (`handle`) لا يُبتلع — الشاشة تقول ما رفضه الخادم بلفظه.
   */
  applyReplenishment: async (productIds: number[]): Promise<{
    applied: number;
    skipped: { product_id: number; sku?: string; reason: string }[];
    products: {
      product_id: number; sku: string; name: string;
      min_stock_level: number; max_stock_level: number;
    }[];
  }> => {
    const res = await fetch(`${INV}/products/apply-replenishment/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ product_ids: productIds }),
    });
    await handle(res, "applyReplenishment");
    return res.json();
  },

  /**
   * T-REORDER: تعيين «النوع» و/أو البراند على منتجاتٍ محدَّدة دفعةً واحدة.
   * الحقل غير المُمرَّر لا يُمَسّ؛ والفارغ يُمحى (تصحيح نوعٍ خاطئ كتعيينه).
   */
  bulkSetGroup: async (
    productIds: number[],
    fields: { variant_group?: string; brand?: string },
  ): Promise<{ updated: number; fields: Record<string, string> }> => {
    const res = await fetch(`${INV}/products/bulk-set-group/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ product_ids: productIds, ...fields }),
    });
    await handle(res, "bulkSetGroup");
    return res.json();
  },

  /**
   * #24: ضمٌّ جماعي — منتجاتٌ قائمة (براندات منتجٍ واحد فعلياً) تحت أبٍ واحد.
   * **بلا حركة مخزون ولا قيد محاسبي**، ومحدِّدها في **جسم** الطلب لا عنوانه
   * (نفس درس كرت المجموعة: تعداد ~1500 معرّف تجاوز حدّ nginx في الإنتاج).
   * الاسم يُطبَّع خادمياً على اسم الهدف — بلا اقتراحٍ آلي لأيّ شيء آخر هنا.
   *
   * `brands` (دلتا ٢): تعيينٌ اختياري `{product_id: اسم البراند}` — يشمل
   * الهدف نفسه كأي عضوٍ آخر (البراند وحده يميّز الصفوف بعد أن يتوحّد الاسم).
   * المفتاح الغائب لا يُمَسّ؛ القيمة الفارغة تُعامَل خادمياً كغائبة.
   */
  mergeProducts: async (
    targetProductId: number, productIds: number[], brands?: Record<number, string>,
  ): Promise<MergeProductsResult> => {
    const res = await fetch(`${INV}/products/merge/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        target_product_id: targetProductId, product_ids: productIds,
        ...(brands && Object.keys(brands).length ? { brands } : {}),
      }),
    });
    await handle(res, "mergeProducts");
    invalidatePickerProducts();
    return res.json();
  },

  /** #24: يتراجع عن ضمٍّ بالكامل — كل براند يعود لأبيه واسمه وبراندِه كما كانوا. */
  undoProductMerge: async (mergeId: number): Promise<UndoMergeResult> => {
    const res = await fetch(`${INV}/products/merge-undo/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ merge_id: mergeId }),
    });
    await handle(res, "undoProductMerge");
    invalidatePickerProducts();
    return res.json();
  },

  // ─── Units of measure ───

  /** وحدات القياس المفعّلة — قائمةٌ ثابتة تقريباً، يقرؤها كرت المنتج ونوافذه السريعة. */
  getUoms: () => fetch(`${INV}/uom/`, { headers: headers() }).then(asList),

  // ─── Categories ───

  getCategories: () =>
    fetch(`${INV}/categories/`, { headers: headers() }).then(asList),

  createCategory: async (body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/categories/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createCategory");
    return res.json();
  },

  updateCategory: async (id: number, body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/categories/${id}/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "updateCategory");
    return res.json();
  },

  deleteCategory: async (id: number) => {
    const res = await fetch(`${INV}/categories/${id}/`, {
      method: "DELETE",
      headers: headers(),
    });
    await handle(res, "deleteCategory");
  },

  // ─── Warehouses (المستودعات) ───

  getWarehouses: (params?: Record<string, string>) => {
    const q = params && Object.keys(params).length
      ? `?${new URLSearchParams(params)}`
      : "";
    return fetch(`${INV}/warehouses/${q}`, { headers: headers() }).then(asList);
  },

  getWarehouseStock: async (id: number): Promise<WarehouseStockDetail> => {
    const res = await fetch(`${INV}/warehouses/${id}/stock/`, { headers: headers() });
    await handle(res, "getWarehouseStock");
    return res.json();
  },

  createWarehouse: async (body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/warehouses/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createWarehouse");
    return res.json();
  },

  updateWarehouse: async (id: number, body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/warehouses/${id}/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "updateWarehouse");
    return res.json();
  },

  deleteWarehouse: async (id: number) => {
    const res = await fetch(`${INV}/warehouses/${id}/`, {
      method: "DELETE",
      headers: headers(),
    });
    await handle(res, "deleteWarehouse");
  },

  getProduct: async (id: number) => {
    const res = await fetch(`${INV}/products/${id}/`, { headers: headers() });
    await handle(res, "getProduct");
    return res.json();
  },

  getProductStockMovements: async (productId: number) => {
    const res = await fetch(`${INV}/products/${productId}/stock-movements/`, {
      headers: headers(),
    });
    await handle(res, "getProductStockMovements");
    return res.json();
  },

  // ─── الباركود والأرقام التسلسلية (T-SERIAL) ───
  /**
   * باركود EAN-13 داخلي غير مستخدم لهذه الشركة. التوليد خادمي عمداً: فحص
   * «غير مستخدم» يجب أن يقع على مصدر البيانات، لا على المنتجات المحمَّلة في الشاشة.
   */
  generateBarcode: async (): Promise<string> => {
    const res = await fetch(`${INV}/products/generate_barcode/`, {
      method: "POST",
      headers: headers(),
      body: "{}",
    });
    await handle(res, "generateBarcode");
    const data = await res.json();
    return String(data.barcode || "");
  },

  /**
   * سلسلة أرقام من رقم بداية وعدد وحدات — «SN-0098» + 3 ⇒ 0098/0099/0100.
   * قاعدة التزايد (البادئة وخانات الصفر) تبقى في الخادم وحده: نسخة ثانية منها
   * في TypeScript تعني قاعدتين تتباعدان بلا أن يلاحظ أحد.
   */
  generateSerials: async (start: string, count: number): Promise<string[]> => {
    const res = await fetch(`${INV}/products/generate_serials/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ start, count }),
    });
    await handle(res, "generateSerials");
    const data = await res.json();
    return Array.isArray(data.serials) ? data.serials.map(String) : [];
  },

  /**
   * ترقيم مخزون قائم: وحدات «في المخزن» بلا فاتورة شراء — مخرج الشركة التي
   * تُشغّل «إجباري» في البيع وكل مخزونها سابقٌ للميزة. السقف خادمي (رصيد المنتج).
   */
  registerProductSerials: async (
    productId: number,
    serials: string[],
  ): Promise<ProductSerialRow[]> => {
    const res = await fetch(`${INV}/products/${productId}/serials/register/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ serials }),
    });
    await handle(res, "registerProductSerials");
    const data = await res.json();
    return Array.isArray(data.serials) ? data.serials : [];
  },

  /** وحدات منتج واحد المُرقَّمة — `status` يفلتر «في المخزن»/«مُباع». */
  getProductSerials: async (
    productId: number,
    status?: "in_stock" | "sold",
  ): Promise<ProductSerialRow[]> => {
    const q = status ? `?status=${encodeURIComponent(status)}` : "";
    const res = await fetch(`${INV}/products/${productId}/serials/${q}`, {
      headers: headers(),
    });
    await handle(res, "getProductSerials");
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  },

  // ─── البراندات/المجموعات المستخدمة (مميّزة) — لمنتقيات اختر/أضف ───
  getBrands: async (): Promise<string[]> => {
    const res = await fetch(`${INV}/products/brands/`, { headers: headers() });
    await handle(res, "getBrands");
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  },
  getGroups: async (): Promise<string[]> => {
    const res = await fetch(`${INV}/products/groups/`, { headers: headers() });
    await handle(res, "getGroups");
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  },
  // أسماء المنتجات المميّزة — لمنتقي «اسم المنتج».
  getProductNames: async (): Promise<string[]> => {
    const res = await fetch(`${INV}/products/names/`, { headers: headers() });
    await handle(res, "getProductNames");
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  },

  // ─── الكرت المجمّع: مجموع كل البراندات لنفس المقاس/الأساس ───
  // المحدِّد يسافر في **جسم** الطلب (POST) لا في عنوانه: التعداد `?ids=1,2,3…`
  // لتصنيفٍ فيه ~1500 منتج يبلغ ~7.5KB في سطر الطلب فيردّه nginx بـ414/400
  // (والتطوير يمرّ). `category` أوجز وأدقّ — الخادم يشتقّ المنتجات وأحفادها.
  getProductGroupProfile: async (sel: ProductGroupSelector | number[]) => {
    const res = await fetch(`${INV}/products/group-profile/`, {
      method: "POST", headers: headers(), body: groupBody(sel), readOnly: true,
    });
    await handle(res, "getProductGroupProfile");
    return res.json();
  },
  getProductGroupLedger: async (sel: ProductGroupSelector | number[], limit = 50, offset = 0) => {
    const res = await fetch(`${INV}/products/group-ledger/`, {
      method: "POST", headers: headers(), body: groupBody(sel, { limit, offset }), readOnly: true,
    });
    await handle(res, "getProductGroupLedger");
    return res.json();
  },
  getProductGroupInvoices: async (sel: ProductGroupSelector | number[]) => {
    const res = await fetch(`${INV}/products/group-invoices/`, {
      method: "POST", headers: headers(), body: groupBody(sel), readOnly: true,
    });
    await handle(res, "getProductGroupInvoices");
    return res.json();
  },

  // ─── تكلفة المنتجات: تكلفة كل فاتورة + متوسط مرجّح بالكمية ───
  getProductCostBreakdown: async (productId: number) => {
    const res = await fetch(`${INV}/products/${productId}/cost-breakdown/`, {
      headers: headers(),
    });
    await handle(res, "getProductCostBreakdown");
    return res.json() as Promise<ProductCostBreakdown>;
  },

  // ─── Stock Movements ───

  getStockMovements: (params?: Record<string, string>) => {
    const q = params && Object.keys(params).length
      ? `?${new URLSearchParams(params)}`
      : "";
    return fetch(`${INV}/stock-movements/${q}`, { headers: headers() }).then(asList);
  },

  /** حركة المخزون مُرقَّمة — مرِّر page/page_size ضمن params (صيانة الأداء 2026-07). */
  getStockMovementsPaged: async (params: Record<string, string>) => {
    const res = await fetch(`${INV}/stock-movements/?${new URLSearchParams(params)}`, {
      headers: headers(),
    });
    await handle(res, "getStockMovementsPaged");
    return toPagedList(await res.json());
  },

  createStockMovement: async (body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/stock-movements/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createStockMovement");
    return res.json();
  },

  /** P0-5: تقييم المخزون التجميعي — صف واحد لكل منتج بدل كل الحركات. */
  getStockValuation: async (params?: Record<string, string>) => {
    const q = params && Object.keys(params).length
      ? `?${new URLSearchParams(params)}`
      : "";
    const res = await fetch(`${INV}/stock-movements/valuation/${q}`, {
      headers: headers(),
    });
    await handle(res, "getStockValuation");
    return res.json();
  },

  getStockSummary: async () => {
    const res = await fetch(`${INV}/stock-movements/summary/`, {
      headers: headers(),
    });
    await handle(res, "getStockSummary");
    return res.json();
  },

  // ─── Product CRUD helpers (N5) ───

  createProduct: async (body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/products/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createProduct");
    invalidatePickerProducts();
    return res.json();
  },

  updateProduct: async (id: number, body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/products/${id}/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "updateProduct");
    invalidatePickerProducts();
    return res.json();
  },

  deleteProduct: async (id: number) => {
    const res = await fetch(`${INV}/products/${id}/`, {
      method: "DELETE",
      headers: headers(),
    });
    await handle(res, "deleteProduct");
    invalidatePickerProducts();
  },

  // ─── #21: «هذا موجود — أضف براند» ───
  /** اقتراحٌ لا منع: هل يطابق هذا الاسم منتجاً مسجَّلاً بعد تطبيعٍ عربي (لا حرفياً)؟ */
  checkProductName: async (name: string): Promise<ProductNameMatch | null> => {
    const q = encodeURIComponent(name);
    const res = await fetch(`${INV}/product-families/check-name/?name=${q}`, {
      headers: headers(),
    });
    await handle(res, "checkProductName");
    const data = await res.json();
    return data?.match ?? null;
  },
  /**
   * يلحق براندًا بمنتجٍ قائم (`family_id`). الردّ يميّز صراحةً بين تسمية
   * البراند الضمنيّ (`created: false`) وإنشاء صفّ جديد (`created: true`) —
   * الفارق حقيقة يجب أن تصل المستخدم لا تفصيل تنفيذ يُطوى.
   */
  addBrand: async (body: { family_id: number; brand: string; sku?: string }): Promise<AddBrandResult> => {
    const res = await fetch(`${INV}/products/add-brand/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "addBrand");
    invalidatePickerProducts();
    return res.json();
  },

  // حذف مرفق داتا شيت محفوظ (SQL + Cloudinary أفضل-جهد على الخادم)
  removeDatasheet: async (productId: number, attachmentId: number) => {
    const res = await fetch(`${INV}/products/${productId}/datasheets/${attachmentId}/`, {
      method: "DELETE",
      headers: headers(),
    });
    await handle(res, "removeDatasheet");
  },

  // ── Phase 7 (T-I1): تحويل بين المستودعات ──────────────────────────
  getWarehouseTransfers: () =>
    fetch(`${INV}/warehouse-transfers/`, { headers: headers() }).then(asList),
  createWarehouseTransfer: async (body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/warehouse-transfers/`, {
      method: "POST", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "createWarehouseTransfer");
    return res.json();
  },
  postWarehouseTransfer: async (id: number) => {
    const res = await fetch(`${INV}/warehouse-transfers/${id}/post/`, {
      method: "POST", headers: headers(),
    });
    await handle(res, "postWarehouseTransfer");
    return res.json();
  },

  // ── Phase 7 (T-I2): جرد ───────────────────────────────────────────
  getStocktakes: () =>
    fetch(`${INV}/stocktakes/`, { headers: headers() }).then(asList),
  getStocktake: async (id: number) => {
    const res = await fetch(`${INV}/stocktakes/${id}/`, { headers: headers() });
    await handle(res, "getStocktake");
    return res.json();
  },
  createStocktake: async (body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/stocktakes/`, {
      method: "POST", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "createStocktake");
    return res.json();
  },
  updateStocktake: async (id: number, body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/stocktakes/${id}/`, {
      method: "PATCH", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "updateStocktake");
    return res.json();
  },
  postStocktake: async (id: number) => {
    const res = await fetch(`${INV}/stocktakes/${id}/post/`, {
      method: "POST", headers: headers(),
    });
    await handle(res, "postStocktake");
    return res.json();
  },
};

// P1-9: نافذة مشتركة قصيرة + دمج الطلبات الطائرة. الحمل الموثّق أدناه لم يكن
// يُدفع مرة واحدة بل مرة لكل فتح شاشة (9 شاشات مستندات، وبعضها يطلبها مرتين:
// القائمة ثم المحرّر) — والنافذة تُحوّل التكرار إلى إصابة ذاكرة بلا اقتطاع أي
// صف. مفتاحها الشركة كي لا تتسرّب قائمة شركةٍ إلى أخرى.
const PICKER_PRODUCTS_TTL_MS = 60_000;
const pickerProductsCache = new Map<string, { at: number; rows: unknown[] }>();
const pickerProductsInFlight = new Map<string, Promise<unknown[]>>();
// عدّاد أجيال: الإفراغ وحده لا يكفي — طلبٌ طائر لحظة الإفراغ كان يهبط بعده
// فيعيد ملء النافذة بصفوف ما قبل التعديل، فيغيب المنتج الجديد 60 ثانية كاملة.
// الجيل يُلتقط عند إطلاق الطلب، ولا يكتب في النافذة من هبط بجيلٍ أقدم.
let pickerProductsGeneration = 0;

// المفتاح يعكس ما أُرسِل فعلاً لا ما نظنّه: المستدعي الذي يترك الشركة فارغة
// لا يُرسل ترويسة X-Tenant-Id فيحسمها الخادم، فلا يجوز أن يتقاسم نتيجته مع
// مستدعٍ أرسل رقماً صريحاً قد يخالفها.
const pickerCacheKey = (tenantId?: number) =>
  tenantId === undefined ? "auto" : String(tenantId);

/**
 * تُفرَغ النافذة عند أي تعديل على المنتجات كي لا يختفي منتجٌ أُنشئ للتوّ من
 * منتقي الفاتورة التي أُنشئ من داخلها.
 */
export const invalidatePickerProducts = (): void => {
  pickerProductsGeneration += 1;
  pickerProductsCache.clear();
  // الطلب الطائر يبقى يخدم منتظريه، لكنه لن يُعبّئ النافذة (جيله أقدم)،
  // وحذفه هنا يجعل أول استدعاء تالٍ يطلق جلبة نظيفة بعد التعديل.
  pickerProductsInFlight.clear();
};

/**
 * منتجات منتقي المستندات — العقد الضيّق (`?view=lookup`) لا كرت المنتج الكامل.
 *
 * العقد الكامل يحمل لكل منتج تحليلاتٍ وحقولَ كرتٍ لا تعرضها شاشة الفاتورة
 * (`purchased_qty`, `avg_monthly_sales`, `stock_status`, `group_key`, …):
 * قياس على 1490 منتجاً أعطى 1,145 كيلوبايت / 1,249 مِلّي ثانية عند **كل** فتح
 * للشاشة، مقابل 609 / 331 لعقد المنتقي. مصدر واحد لكل شاشات المستندات كي لا
 * ترتدّ إحداها للعقد الكامل بصمت.
 */
export const listPickerProducts = <T>(tenantId?: number): Promise<T[]> => {
  const key = pickerCacheKey(tenantId);
  const cached = pickerProductsCache.get(key);
  // نسخة سطحية لكل مستدعٍ: الشاشات تضع المصفوفة في state وبعضها يفرزها
  // موضعياً، ومشاركة المرجع نفسه تجعل فرز شاشةٍ يعيد ترتيب أخرى.
  if (cached && Date.now() - cached.at < PICKER_PRODUCTS_TTL_MS) {
    return Promise.resolve((cached.rows as T[]).slice());
  }
  let req = pickerProductsInFlight.get(key);
  if (!req) {
    const generationAtLaunch = pickerProductsGeneration;
    req = apiGetList<T>("inventory/products/", { tenantId, query: { view: "lookup" } })
      .then((rows) => {
        if (generationAtLaunch === pickerProductsGeneration) {
          pickerProductsCache.set(key, { at: Date.now(), rows: rows as unknown[] });
        }
        return rows as unknown[];
      })
      .finally(() => {
        if (pickerProductsInFlight.get(key) === req) {
          pickerProductsInFlight.delete(key);
        }
      });
    pickerProductsInFlight.set(key, req);
  }
  return req.then((rows) => (rows as T[]).slice());
};
