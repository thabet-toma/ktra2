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

export const inventoryApi = {
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
   * صفحة واحدة من الأصناف (المرحلة 5 / P0-12).
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
   * كل الأصناف عبر حلقة صفحات. **لا تستخدمها لعرض قائمة** — بقيت لعمليات
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
   * «غير مستخدم» يجب أن يقع على مصدر البيانات، لا على الأصناف المحمَّلة في الشاشة.
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
   * تُشغّل «إجباري» في البيع وكل مخزونها سابقٌ للميزة. السقف خادمي (رصيد الصنف).
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

  /** وحدات صنف واحد المُرقَّمة — `status` يفلتر «في المخزن»/«مُباع». */
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
  // تمرَّر معرّفات أعضاء المجموعة (تُحسب في الواجهة من group_key).
  getProductGroupProfile: async (ids: number[]) => {
    const res = await fetch(`${INV}/products/group-profile/?ids=${ids.join(",")}`, { headers: headers() });
    await handle(res, "getProductGroupProfile");
    return res.json();
  },
  getProductGroupLedger: async (ids: number[], limit = 50, offset = 0) => {
    const res = await fetch(
      `${INV}/products/group-ledger/?ids=${ids.join(",")}&limit=${limit}&offset=${offset}`,
      { headers: headers() });
    await handle(res, "getProductGroupLedger");
    return res.json();
  },
  getProductGroupInvoices: async (ids: number[]) => {
    const res = await fetch(`${INV}/products/group-invoices/?ids=${ids.join(",")}`, { headers: headers() });
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

  /** P0-5: تقييم المخزون التجميعي — صف واحد لكل صنف بدل كل الحركات. */
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
    return res.json();
  },

  updateProduct: async (id: number, body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/products/${id}/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "updateProduct");
    return res.json();
  },

  deleteProduct: async (id: number) => {
    const res = await fetch(`${INV}/products/${id}/`, {
      method: "DELETE",
      headers: headers(),
    });
    await handle(res, "deleteProduct");
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

/**
 * أصناف منتقي المستندات — العقد الضيّق (`?view=lookup`) لا كرت الصنف الكامل.
 *
 * العقد الكامل يحمل لكل صنف تحليلاتٍ وحقولَ كرتٍ لا تعرضها شاشة الفاتورة
 * (`purchased_qty`, `avg_monthly_sales`, `stock_status`, `group_key`, …):
 * قياس على 1490 صنفاً أعطى 1,145 كيلوبايت / 1,249 مِلّي ثانية عند **كل** فتح
 * للشاشة، مقابل 609 / 331 لعقد المنتقي. مصدر واحد لكل شاشات المستندات كي لا
 * ترتدّ إحداها للعقد الكامل بصمت.
 */
export const listPickerProducts = <T>(tenantId?: number) =>
  apiGetList<T>("inventory/products/", { tenantId, query: { view: "lookup" } });
