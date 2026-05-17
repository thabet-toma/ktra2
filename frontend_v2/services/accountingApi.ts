/**
 * محاسبة SQL عبر Django REST — نفس مسارات frontend v1 (MUI).
 */
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
const ACC = `${API_BASE}/accounting`;

const headers = (): HeadersInit => {
  const token = localStorage.getItem("token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Token ${token}` } : {}),
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

  getPartners: () =>
    fetch(`${API_BASE}/partners/`, { headers: headers() }).then(asList),

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
