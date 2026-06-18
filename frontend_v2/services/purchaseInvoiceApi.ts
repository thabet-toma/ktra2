import type {
  PurchaseInvoiceDto,
  PurchaseInvoiceListDto,
} from "../types/purchaseInvoice";
import { resolveTenantId } from "../utils/tenantContext";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
const BASE = `${API_BASE}/logistics/purchase-invoices`;

const NETWORK_HINT =
  "تعذر الاتصال بالخادم (غالباً الخادم غير شغّال). شغّل Django على المنفذ 8000 " +
  "(مثلاً: python manage.py runserver 0.0.0.0:8000) وتأكد أن VITE_API_URL يطابق العنوان " +
  `(الحالي: ${String(API_BASE).replace(/\/+$/, "")})`;

async function safeFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  try {
    return await fetch(input, init);
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

export const purchaseInvoiceApi = {
  list: (params?: Record<string, string>) => {
    const q =
      params && Object.keys(params).length
        ? `?${new URLSearchParams(params)}`
        : "";
    return safeFetch(`${BASE}/${q}`, { headers: headers() }).then(asList);
  },

  get: async (id: number): Promise<PurchaseInvoiceDto> => {
    const res = await safeFetch(`${BASE}/${id}/`, { headers: headers() });
    await handle(res, "getInvoice");
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
    const res = await fetch(`${BASE}/${id}/`, {
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

  /** وصل دفع للمورد (Feature 2): يُنشئ SupplierPayment ثم يرحّله (Dr ذمم المورد / Cr صندوق). */
  addSupplierPayment: async (body: {
    partner: number;
    payment_date: string;
    amount: string;
    currency?: number | null;
    cash_or_bank_account: number;
    notes?: string;
  }): Promise<{ id: number; journal: number | null }> => {
    const SP = `${API_BASE}/logistics/supplier-payments`;
    const createRes = await safeFetch(`${SP}/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(createRes, "addSupplierPayment");
    const created = (await createRes.json()) as { id: number; journal: number | null };
    const postRes = await safeFetch(`${SP}/${created.id}/post/`, {
      method: "POST",
      headers: headers(),
    });
    await handle(postRes, "postSupplierPayment");
    return postRes.json();
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
  }): Promise<{ updated: number; skipped?: number; message?: string }> => {
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
    const res = await safeFetch(`${BASE}/resolve-price/?${q}`, { headers: headers() });
    await handle(res, "resolvePrice");
    return res.json();
  },

  /** FEAT-1: إعدادات الشراء (استراتيجية التسعير التلقائي). */
  getSettings: async (): Promise<{ purchase_default_price_strategy: string }> => {
    const res = await safeFetch(`${API_BASE}/logistics/purchase-settings/current/`, {
      headers: headers(),
    });
    await handle(res, "getPurchaseSettings");
    return res.json();
  },

  updateSettings: async (body: {
    purchase_default_price_strategy: string;
  }): Promise<{ purchase_default_price_strategy: string }> => {
    const res = await safeFetch(`${API_BASE}/logistics/purchase-settings/current/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "updatePurchaseSettings");
    return res.json();
  },
};
