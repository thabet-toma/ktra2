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

  getJournals: () =>
    fetch(`${ACC}/journals/`, { headers: headers() }).then(asList),

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
};
