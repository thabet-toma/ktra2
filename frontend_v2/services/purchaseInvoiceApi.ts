import type {
  PurchaseInvoiceDto,
  PurchaseInvoiceListDto,
} from "../types/purchaseInvoice";
import type { SerialEntryMode } from "../types/inventory";
import { resolveTenantId } from "../utils/tenantContext";
import { apiFetch } from "./restApi";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
const BASE = `${API_BASE}/logistics/purchase-invoices`;

const NETWORK_HINT =
  "تعذر الاتصال بالخادم (غالباً الخادم غير شغّال). شغّل Django على المنفذ 8000 " +
  "(مثلاً: python manage.py runserver 0.0.0.0:8000) وتأكد أن VITE_API_URL يطابق العنوان " +
  `(الحالي: ${String(API_BASE).replace(/\/+$/, "")})`;

/** إعدادات الشراء لكل شركة (التسعير + الصندوق + الاستلام مع الترحيل). */
export interface PurchaseSettingsDto {
  purchase_default_price_strategy: string;
  default_cash_account: number | null;
  receive_on_post: boolean;
  /** تسمية مستند الاستلام المرتبط بفاتورة (يحرّرها المستخدم). */
  receipt_doc_label: string;
  /** تسمية المستند بلا فاتورة مرتبطة. */
  standalone_receipt_label: string;
  allow_standalone_receipt: boolean;
  allow_edit_receipt: boolean;
  /** T-SERIAL: نمط إدخال الرقم التسلسلي في بنود فاتورة الشراء (الافتراضي «معطّل»). */
  serial_entry_mode: SerialEntryMode;
}

/** سند صرف مورد كما يعيده الخادم (مع التوزيع والمتبقّي «على الحساب»). */
export interface SupplierPaymentDto {
  id: number;
  partner: number;
  partner_name?: string;
  purchase_invoice?: number | null;
  payment_date: string;
  amount: string;
  currency?: number | null;
  currency_code?: string | null;
  exchange_rate?: string;
  cash_or_bank_account: number;
  cash_account_name?: string | null;
  is_posted: boolean;
  journal?: number | null;
  notes?: string | null;
  allocations?: Array<{
    id: number;
    invoice: number;
    invoice_number?: string;
    amount: string;
  }>;
  allocated_amount?: string;
  unallocated_amount?: string;
  auto_post_error?: string;
}

export interface ClearanceImportOptionDeal {
  deal_id: number;
  deal_ref: string;
  is_converted: boolean;
  invoice_id: number | null;
  invoice_number: string | null;
}

async function safeFetch(
  input: string,
  init?: RequestInit
): Promise<Response> {
  try {
    return await apiFetch(input, init);
  } catch (e) {
    const name = e instanceof Error ? e.name : "";
    if (name === "TypeError" || String(e).toLowerCase().includes("fetch")) {
      throw new Error(NETWORK_HINT);
    }
    throw e;
  }
}

const headers = (): HeadersInit => {
  const token = localStorage.getItem("token");
  return {
    "Content-Type": "application/json",
    "X-Tenant-Id": String(resolveTenantId()),
    ...(token ? { Authorization: `Token ${token}` } : {}),
  };
};

function formatDrfErrors(j: Record<string, unknown>): string | null {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(j)) {
    if (k === "detail" || k === "error") continue;
    if (Array.isArray(v) && v.every((x) => typeof x === "string"))
      parts.push(`${k}: ${(v as string[]).join(" — ")}`);
    else if (typeof v === "object" && v !== null)
      parts.push(`${k}: ${JSON.stringify(v).slice(0, 200)}`);
  }
  return parts.length ? parts.join("\n") : null;
}

async function handle(res: Response, ctx: string): Promise<void> {
  if (res.ok) return;
  let msg = `${ctx}: ${res.status}`;
  try {
    const j = (await res.json()) as Record<string, unknown>;
    if (typeof j.error === "string") msg = j.error;
    else if (typeof j.detail === "string") msg = j.detail;
    else {
      const joined = formatDrfErrors(j);
      if (joined) msg = joined;
    }
  } catch {
    const t = await res.text();
    if (t) msg = t.slice(0, 400);
  }
  throw new Error(msg);
}

async function asList(res: Response): Promise<PurchaseInvoiceListDto[]> {
  await handle(res, "purchaseInvoice");
  const data = await res.json();
  return Array.isArray(data) ? data : (data.results ?? []);
}

async function asPage(res: Response): Promise<{
  results: PurchaseInvoiceListDto[];
  count: number;
  hasNext: boolean;
}> {
  await handle(res, "purchaseInvoice");
  const data = await res.json();
  if (Array.isArray(data)) {
    return { results: data, count: data.length, hasNext: false };
  }
  const results = Array.isArray(data?.results) ? data.results : [];
  return {
    results,
    count: Number(data?.count ?? results.length) || results.length,
    hasNext: data?.next != null,
  };
}

export const purchaseInvoiceApi = {
  list: (params?: Record<string, string>) => {
    const q =
      params && Object.keys(params).length
        ? `?${new URLSearchParams(params)}`
        : "";
    return safeFetch(`${BASE}/${q}`, { headers: headers() }).then(asList);
  },

  listPage: (params: Record<string, string | number | undefined>) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    return safeFetch(`${BASE}/?${query}`, { headers: headers() }).then(asPage);
  },

  get: async (id: number): Promise<PurchaseInvoiceDto> => {
    const res = await safeFetch(`${BASE}/${id}/`, { headers: headers() });
    await handle(res, "getInvoice");
    return res.json();
  },

  // W6: بنود الفاتورة الأصلية القابلة للإرجاع (المفوتر/المرتجع/المتبقّي) لمنتقي المرجع.
  getReturnableLines: async (
    id: number
  ): Promise<{
    original_invoice: number;
    invoice_number: string;
    partner: number | null;
    partner_name: string | null;
    lines: {
      product: number;
      name: string;
      unit_price: string;
      invoiced_qty: string;
      returned_qty: string;
      remaining_qty: string;
    }[];
  }> => {
    const res = await safeFetch(`${BASE}/${id}/returnable-lines/`, { headers: headers() });
    await handle(res, "getReturnableLines");
    return res.json();
  },

  create: async (
    body: Partial<PurchaseInvoiceDto>
  ): Promise<PurchaseInvoiceDto> => {
    const res = await safeFetch(`${BASE}/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createInvoice");
    return res.json();
  },

  update: async (
    id: number,
    body: Partial<PurchaseInvoiceDto>
  ): Promise<PurchaseInvoiceDto> => {
    const res = await safeFetch(`${BASE}/${id}/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "updateInvoice");
    return res.json();
  },

  delete: async (id: number): Promise<void> => {
    const res = await safeFetch(`${BASE}/${id}/`, {
      method: "DELETE",
      headers: headers(),
    });
    if (!res.ok && res.status !== 204) {
      await handle(res, "deleteInvoice");
    }
  },

  postToAccounting: async (
    id: number
  ): Promise<{ journal_id: number; message: string }> => {
    const res = await safeFetch(`${BASE}/${id}/post-to-accounting/`, {
      method: "POST",
      headers: headers(),
    });
    await handle(res, "postToAccounting");
    return res.json();
  },

  unpost: async (id: number): Promise<{ message: string }> => {
    const res = await safeFetch(`${BASE}/${id}/unpost/`, {
      method: "POST",
      headers: headers(),
    });
    await handle(res, "unpost");
    return res.json();
  },

  /**
   * وصل دفع للمورد (Feature 2): يُنشئ SupplierPayment ويرحّله (Dr ذمم المورد / Cr صندوق).
   * T-AUTOPOST: الترحيل صار في الخادم ضمن نفس الطلب — `auto_post` يسمو على إعداد
   * الشركة (`auto_post_payments`): true = حفظ وترحيل، false = حفظ كمسودة.
   */
  addSupplierPayment: async (body: {
    partner: number;
    purchase_invoice?: number;
    payment_date: string;
    amount: string;
    currency?: number | null;
    cash_or_bank_account: number;
    notes?: string;
    /** T-ONEPAY: شيكات صادرة — مبالغها جزء من `amount` لا إضافة عليه. */
    cheques?: Array<{
      cheque_number: string;
      amount: string | number;
      bank_name?: string;
      account_number?: string;
      bank_branch?: string;
      payee_name?: string;
      due_date?: string | null;
      issue_date?: string | null;
    }>;
    auto_post?: boolean;
  }): Promise<{ id: number; journal: number | null; is_posted: boolean; auto_post_error?: string }> => {
    const SP = `${API_BASE}/logistics/supplier-payments`;
    const createRes = await safeFetch(`${SP}/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(createRes, "addSupplierPayment");
    return createRes.json();
  },

  /**
   * T-ONACC: سندات صرف مورد معيّن (لعرض الرصيد «على الحساب» وتوزيعه).
   * `partner` فلتر خادم — لا تُسحب سندات الشركة كلها.
   */
  listSupplierPayments: async (partnerId?: number | string): Promise<SupplierPaymentDto[]> => {
    // P0-5: القائمة مُرقَّمة إلزامياً — سقف 200 صريح (المفلتر بمورد صغير عملياً).
    const qs = partnerId ? `?partner=${partnerId}&page=1&page_size=200` : "?page=1&page_size=200";
    const res = await safeFetch(`${API_BASE}/logistics/supplier-payments/${qs}`, {
      headers: headers(),
    });
    await handle(res, "listSupplierPayments");
    const data = await res.json();
    return Array.isArray(data) ? data : (data?.results ?? []);
  },

  /**
   * T-ONACC: توزيع سند صرف على فواتير شراء — بعد الترحيل ربط فقط بلا قيد جديد
   * (ذمم المورد دُينت وقت الترحيل). مرآة `allocateCustomerPayment`.
   */
  allocateSupplierPayment: async (
    id: number,
    allocations: Array<{ invoice: number; amount: string | number }>,
  ): Promise<SupplierPaymentDto> => {
    const res = await safeFetch(`${API_BASE}/logistics/supplier-payments/${id}/allocate/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ allocations }),
    });
    await handle(res, "allocateSupplierPayment");
    return res.json();
  },

  /** ترحيل سند صرف مسودة (زر «ترحيل» في قائمة سندات الصرف). */
  postSupplierPayment: async (id: number): Promise<{ id: number; is_posted: boolean }> => {
    const res = await safeFetch(`${API_BASE}/logistics/supplier-payments/${id}/post/`, {
      method: "POST",
      headers: headers(),
    });
    await handle(res, "postSupplierPayment");
    return res.json();
  },

  previewClearanceImport: async (body: {
    clearance_id: number;
    deal_ids: number[];
    deal_remaining_rate?: number;
    shipment_remaining_rate?: number;
    use_cost_lines?: boolean;
  }): Promise<Record<string, unknown>> => {
    const res = await safeFetch(`${BASE}/preview-clearance-import/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "previewClearanceImport");
    return res.json();
  },

  importFromClearance: async (body: {
    clearance_id: number;
    deal_ids: number[];
    deal_remaining_rate?: number;
    shipment_remaining_rate?: number;
    use_cost_lines?: boolean;
    /** يتجاوز فحص الشحن غير المدفوع (افتراضي: ممنوع من الخادم) */
    allow_unpaid_freight?: boolean;
  }): Promise<{ preview: Record<string, unknown>; created: PurchaseInvoiceDto[] }> => {
    const res = await safeFetch(`${BASE}/import-from-clearance/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "importFromClearance");
    return res.json();
  },

  getClearanceImportOptions: async (clearanceId: number): Promise<{
    clearance_id: number;
    shipment_id: number;
    deals: ClearanceImportOptionDeal[];
  }> => {
    const query = new URLSearchParams({ clearance_id: String(clearanceId) });
    const res = await safeFetch(`${BASE}/clearance-import-options/?${query}`, {
      headers: headers(),
    });
    await handle(res, "getClearanceImportOptions");
    return res.json();
  },

  /** استلام بضاعة فاتورة محلية للمخزن — كل سطر: البند + الكمية + المستودع */
  receive: async (
    id: number,
    lines: { item_id: number; quantity: number; warehouse_id: number }[]
  ): Promise<{
    receipt_status: string;
    journal_id: number;
    movements_created: number;
  }> => {
    const res = await safeFetch(`${BASE}/${id}/receive/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ lines }),
    });
    await handle(res, "receiveGoods");
    return res.json();
  },

  recalculateLandedCost: async (body: {
    shipment_id?: number;
    clearance_id?: number;
    deal_remaining_rate?: number;
    shipment_remaining_rate?: number;
    use_cost_lines?: boolean;
    auto_repost?: boolean;
  }): Promise<{
    updated: number;
    skipped?: number;
    message?: string;
    reconciliation?: {
      previously_posted: number;
      reposted: number;
      left_draft: number;
      warnings: string[];
    };
  }> => {
    const res = await safeFetch(`${BASE}/recalculate-landed-cost/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "recalculateLandedCost");
    return res.json();
  },

  /**
   * FEAT-1: السعر المقترح لصنف عند إضافته لبند فاتورة شراء. يفوّض للـ PriceResolver
   * المشترك في الخادم (آخر/أقل سعر شراء حسب إعدادات الشراء، ثم تكلفة الصنف، ثم فارغ).
   */
  resolvePrice: async (params: {
    product: number;
    currency?: number | null;
    exchange_rate?: number | string | null;
    strategy?: string;
    /** مورد الفاتورة — يحصر «آخر شراء» به (يبقى «أقل شراء» عاماً). */
    supplier?: number | string | null;
  }): Promise<{
    unit_price: string | null;
    strategy_used: string | null;
    strategy_requested: string;
    source: { document_type: string; document_number?: string } | null;
  }> => {
    const q = new URLSearchParams();
    q.set("product", String(params.product));
    if (params.currency != null) q.set("currency", String(params.currency));
    if (params.exchange_rate != null) q.set("exchange_rate", String(params.exchange_rate));
    if (params.strategy) q.set("strategy", params.strategy);
    if (params.supplier) q.set("supplier", String(params.supplier));
    const res = await safeFetch(`${BASE}/resolve-price/?${q}`, { headers: headers() });
    await handle(res, "resolvePrice");
    return res.json();
  },

  /**
   * task24: سعر الشراء المقترح لكل المنتجات دفعة واحدة — لعرضه داخل خيارات منتقي
   * الأصناف بلا نقر (يتجنّب نداء resolve-price لكل صف).
   */
  priceList: async (supplierId?: number | string | null): Promise<Array<{
    product_id: number;
    unit_price: string | null;
    source_type: string;
    source_label: string;
    prices?: Array<{
      label: string;
      unit_price: string;
      source_type: string;
      source_label: string;
      document_id: number | null;
    }>;
  }>> => {
    const q = supplierId ? `?supplier=${encodeURIComponent(String(supplierId))}` : "";
    const res = await safeFetch(`${BASE}/price-list/${q}`, { headers: headers() });
    await handle(res, "purchasePriceList");
    return res.json();
  },

  /** FEAT-1: إعدادات الشراء (استراتيجية التسعير + T-A4: الصندوق الافتراضي). */
  getSettings: async (): Promise<PurchaseSettingsDto> => {
    const res = await safeFetch(`${API_BASE}/logistics/purchase-settings/current/`, {
      headers: headers(),
    });
    await handle(res, "getPurchaseSettings");
    return res.json();
  },

  updateSettings: async (
    body: Partial<PurchaseSettingsDto>,
  ): Promise<PurchaseSettingsDto> => {
    const res = await safeFetch(`${API_BASE}/logistics/purchase-settings/current/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "updatePurchaseSettings");
    return res.json();
  },
};
