/**
 * محاسبة SQL عبر Django REST — نفس مسارات frontend v1 (MUI).
 */
import { resolveBranchId, resolveTenantId } from "../utils/tenantContext";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
const ACC = `${API_BASE}/accounting`;

const headers = (): HeadersInit => {
  const token = localStorage.getItem("token");
  // task11 R2: بدون X-Tenant-Id كانت كل نداءات المحاسبة تعتمد على
  // auto-resolve أحادي الشركة — لحظة وجود شركة ثانية يتعطل ويرجع الباك-إند
  // قوائم فارغة (شجرة حسابات «صفر» التي رآها المالك).
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
    const j = await res.json();
    if (typeof j.error === "string") msg = j.error;
    else if (typeof j.detail === "string") msg = j.detail;
    else if (j.detail != null) msg = JSON.stringify(j.detail);
  } catch {
    const t = await res.text();
    if (t) msg = t.slice(0, 400);
  }
  throw new Error(msg);
}

async function asList(res: Response): Promise<any[]> {
  await handle(res, "accounting");
  const data = await res.json();
  return Array.isArray(data) ? data : (data.results ?? []);
}

/** ربط صندوق (معرّف Firestore) بحساب في شجرة المحاسبة */
export type CashBoxLedgerLink = {
  id: number;
  external_id: string;
  name: string;
  currency_code: string;
  account_id: number;
  account_code: string;
  /** task16 E16: رصيد دفتر الأستاذ الحقيقي (مدين − دائن، قيود مرحَّلة) */
  balance?: string;
};

export const accountingApi = {
  getAccounts: () =>
    fetch(`${ACC}/accounts/`, { headers: headers() }).then(asList),

  createAccount: async (body: Record<string, unknown>) => {
    const res = await fetch(`${ACC}/accounts/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createAccount");
    return res.json();
  },

  updateAccount: async (id: number, body: Record<string, unknown>) => {
    const res = await fetch(`${ACC}/accounts/${id}/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "updateAccount");
    return res.json();
  },

  deleteAccount: async (id: number) => {
    const res = await fetch(`${ACC}/accounts/${id}/`, {
      method: "DELETE",
      headers: headers(),
    });
    await handle(res, "deleteAccount");
  },

  getJournals: (params?: Record<string, string>) => {
    const q =
      params && Object.keys(params).length
        ? `?${new URLSearchParams(params)}`
        : "";
    return fetch(`${ACC}/journals/${q}`, { headers: headers() }).then(asList);
  },

  getJournal: async (id: number) => {
    const res = await fetch(`${ACC}/journals/${id}/`, { headers: headers() });
    await handle(res, "getJournal");
    return res.json();
  },

  createJournal: async (body: unknown) => {
    const res = await fetch(`${ACC}/journals/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createJournal");
    return res.json();
  },

  updateJournal: async (id: number, body: unknown) => {
    const res = await fetch(`${ACC}/journals/${id}/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "updateJournal");
    return res.json();
  },

  postJournal: async (id: number) => {
    const res = await fetch(`${ACC}/journals/${id}/post/`, {
      method: "POST",
      headers: headers(),
    });
    await handle(res, "postJournal");
    return res.json();
  },

  deleteJournal: async (id: number) => {
    const res = await fetch(`${ACC}/journals/${id}/`, {
      method: "DELETE",
      headers: headers(),
    });
    await handle(res, "deleteJournal");
  },

  // Phase 2-2-b wiring: master-data lookup with offline cache fallback.
  // When the network is up, we hit the server, mirror rows into Dexie + stamp
  // cache_meta. When it's down, we serve the last known snapshot so dropdowns
  // and pickers keep working offline. Read errors here are non-fatal — the
  // caller still gets [] if nothing has ever been cached.
  getPartners: async () => {
    const db = (await import("./offline/db")).default;
    try {
      const data = await fetch(`${API_BASE}/partners/`, { headers: headers() }).then(asList);
      try {
        const now = new Date().toISOString();
        for (const p of data as Array<Record<string, unknown>>) {
          const id = Number(p.id);
          if (!Number.isFinite(id)) continue;
          await db.partners.put({
            id,
            tenant_id: Number(p.tenant ?? 0),
            name: String(p.name ?? ""),
            partner_type: String(p.partner_type ?? ""),
            data: JSON.stringify(p),
            updated_at: now,
          });
        }
        await db.cache_meta.put({ key: "partners:list", updated_at: now });
      } catch { /* IndexedDB unavailable in private mode — non-fatal */ }
      return data;
    } catch {
      // Network failed — fall back to the last cached snapshot.
      try {
        const cached = await db.partners.toArray();
        return cached.map((c) => JSON.parse(c.data));
      } catch {
        return [];
      }
    }
  },

  getCostCenters: () =>
    fetch(`${ACC}/cost-centers/`, { headers: headers() }).then(asList),

  getCheques: () =>
    fetch(`${ACC}/cheques/`, { headers: headers() }).then(asList),

  createCheque: async (body: Record<string, unknown>) => {
    const res = await fetch(`${ACC}/cheques/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createCheque");
    return res.json();
  },

  /** task11 R2-A3: تحويل حالة الشيك عبر آلة الانتقالات + القيد المحاسبي */
  transferCheque: async (id: number, body: Record<string, unknown>) => {
    const res = await fetch(`${ACC}/cheques/${id}/transfer/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "transferCheque");
    return res.json();
  },

  updateCheque: async (id: number, body: Record<string, unknown>) => {
    const res = await fetch(`${ACC}/cheques/${id}/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "updateCheque");
    return res.json();
  },

  deleteCheque: async (id: number) => {
    const res = await fetch(`${ACC}/cheques/${id}/`, {
      method: "DELETE",
      headers: headers(),
    });
    await handle(res, "deleteCheque");
  },

  getGeneralLedger: async (params: Record<string, string>) => {
    const q = new URLSearchParams(params);
    const res = await fetch(`${ACC}/general-ledger/?${q}`, {
      headers: headers(),
    });
    await handle(res, "generalLedger");
    return res.json();
  },

  getTrialBalance: async (params: Record<string, string>) => {
    const q = new URLSearchParams(params);
    const res = await fetch(`${ACC}/trial-balance/?${q}`, {
      headers: headers(),
    });
    await handle(res, "trialBalance");
    return res.json();
  },

  getVatReport: async (params: Record<string, string>) => {
    const q = new URLSearchParams(params);
    const res = await fetch(`${ACC}/vat-report/?${q}`, {
      headers: headers(),
    });
    await handle(res, "vatReport");
    return res.json();
  },

  getLandedCostReport: async (params: Record<string, string> = {}) => {
    const q = new URLSearchParams(params);
    const LOG = `${API_BASE}/logistics`;
    const res = await fetch(`${LOG}/reports/landed-cost/?${q}`, {
      headers: headers(),
    });
    await handle(res, "landedCostReport");
    return res.json();
  },

  /** صندوق Firestore = نفس المعرف external_id؛ يُنشأ له حساب أصول في الشجرة بنفس الاسم */
  registerCashBoxLedger: async (body: {
    external_id: string;
    name: string;
    currency_code?: string;
  }) => {
    const res = await fetch(`${ACC}/cash-box-accounts/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "registerCashBoxLedger");
    return res.json();
  },

  getCashBoxLedgers: async (): Promise<CashBoxLedgerLink[]> => {
    const res = await fetch(`${ACC}/cash-box-accounts/`, { headers: headers() });
    await handle(res, "cashBoxLedgers");
    const data = await res.json();
    const arr = Array.isArray(data) ? data : (data.results ?? []);
    return arr as CashBoxLedgerLink[];
  },

  /** قيد إيداع: مدين صندوق GL | دائن رأس مال — بعد حفظ حركة Firestore */
  postCashBoxDepositJournal: async (body: {
    external_id: string;
    amount: number;
    transaction_date: string;
    description: string;
    firestore_transaction_id?: string;
  }) => {
    const res = await fetch(`${ACC}/cash-box-accounts/deposit-journal/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "postCashBoxDepositJournal");
    return res.json() as Promise<{ journal_id: number }>;
  },

  postPurchaseReceipt: async (body: Record<string, unknown>) => {
    const res = await fetch(`${ACC}/purchase-receipts/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "postPurchaseReceipt");
    return res.json();
  },

  reverseJournal: async (id: number, transaction_date?: string) => {
    const res = await fetch(`${ACC}/journals/${id}/reverse/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(transaction_date ? { transaction_date } : {}),
    });
    await handle(res, "reverseJournal");
    return res.json();
  },

  // ─── Exchange Rates ───

  getExchangeRates: (params?: Record<string, string>) => {
    const q = params && Object.keys(params).length ? `?${new URLSearchParams(params)}` : "";
    return fetch(`${ACC}/exchange-rates/${q}`, { headers: headers() }).then(asList);
  },

  createExchangeRate: async (body: Record<string, unknown>) => {
    const res = await fetch(`${ACC}/exchange-rates/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createExchangeRate");
    return res.json();
  },

  updateExchangeRate: async (id: number, body: Record<string, unknown>) => {
    const res = await fetch(`${ACC}/exchange-rates/${id}/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "updateExchangeRate");
    return res.json();
  },

  deleteExchangeRate: async (id: number) => {
    const res = await fetch(`${ACC}/exchange-rates/${id}/`, {
      method: "DELETE",
      headers: headers(),
    });
    await handle(res, "deleteExchangeRate");
  },

  getExchangeRate: async (params: { from_currency: string; to_currency: string; date: string }) => {
    const q = new URLSearchParams(params);
    const res = await fetch(`${ACC}/exchange-rates/get-rate/?${q}`, { headers: headers() });
    await handle(res, "getExchangeRate");
    return res.json();
  },

  // ─── Fiscal Periods ───

  getFiscalPeriods: () =>
    fetch(`${ACC}/fiscal-periods/`, { headers: headers() }).then(asList),

  createFiscalPeriod: async (body: Record<string, unknown>) => {
    const res = await fetch(`${ACC}/fiscal-periods/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createFiscalPeriod");
    return res.json();
  },

  createFiscalYear: async (year: number) => {
    const res = await fetch(`${ACC}/fiscal-periods/create-year/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ year }),
    });
    await handle(res, "createFiscalYear");
    return res.json();
  },

  closeFiscalPeriod: async (id: number) => {
    const res = await fetch(`${ACC}/fiscal-periods/${id}/close/`, {
      method: "POST",
      headers: headers(),
    });
    await handle(res, "closeFiscalPeriod");
    return res.json();
  },

  reopenFiscalPeriod: async (id: number) => {
    const res = await fetch(`${ACC}/fiscal-periods/${id}/reopen/`, {
      method: "POST",
      headers: headers(),
    });
    await handle(res, "reopenFiscalPeriod");
    return res.json();
  },

  yearEndClose: async (body: { year: number; retained_earnings_account_id: number }) => {
    const res = await fetch(`${ACC}/fiscal-periods/year-end-close/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "yearEndClose");
    return res.json();
  },

  // ─── Tax Rates ───

  getTaxRates: () =>
    fetch(`${ACC}/tax-rates/`, { headers: headers() }).then(asList),

  createTaxRate: async (body: Record<string, unknown>) => {
    const res = await fetch(`${ACC}/tax-rates/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createTaxRate");
    return res.json();
  },

  updateTaxRate: async (id: number, body: Record<string, unknown>) => {
    const res = await fetch(`${ACC}/tax-rates/${id}/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "updateTaxRate");
    return res.json();
  },

  deleteTaxRate: async (id: number) => {
    const res = await fetch(`${ACC}/tax-rates/${id}/`, {
      method: "DELETE",
      headers: headers(),
    });
    await handle(res, "deleteTaxRate");
  },

  // ─── Currencies ───

  getCurrencies: () =>
    fetch(`${ACC}/currencies/`, { headers: headers() }).then(asList),
};
