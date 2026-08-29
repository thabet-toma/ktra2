/**
 * محاسبة SQL عبر Django REST — نفس مسارات frontend v1 (MUI).
 */
import { resolveBranchId, resolveTenantId } from "../utils/tenantContext";
import { apiFetch, toPagedList } from "./restApi";
import { humanizeDrfError } from "../utils/drfError";
import { tenantScopedOfflineKey } from "../utils/offlineTenantScope";
import type {
  BankAccountDto,
  BankBranchDto,
  BankDto,
  BankReconciliationSummaryDto,
  BankStatementDto,
  ChequeDepositBatchResult,
  ChequeDto,
  OpeningBalanceDto,
  OpeningBalanceLinesInput,
} from "../types/accounting";

// كل نداءات هذا العميل القديمة تمر الآن من دورة الطلب المحدودة والموحّدة.
const fetch = apiFetch;

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
  let body: unknown = null;
  try {
    const j = await res.json();
    body = j;
    // T-CHQ3: أخطاء الحقول ({"tenant":["مطلوب"]}) كانت تسقط هنا فيرى المستخدم
    // «createCheque: 400» بلا سبب — تمرّ الآن على الطبقة الموحّدة.
    msg = humanizeDrfError(j) || msg;
  } catch {
    const t = await res.text();
    if (t) msg = t.slice(0, 400);
  }
  // CHQ-4: جسم الاستجابة يبقى مُلحقاً بالخطأ — نفس عقد `restApi`. رفضُ دفعة
  // الإيداع مثلاً يحمل `rejected` مربوطاً بأرقام الشيكات، وسطرُ نصٍّ وحده
  // يُضيّعه فتعود الشاشة إلى رسالة عامة لا تقول أي ورقة أبطلت الدفعة.
  const err = new Error(msg) as Error & { status?: number; data?: unknown };
  err.status = res.status;
  err.data = body;
  throw err;
}

async function asList(res: Response): Promise<any[]> {
  await handle(res, "accounting");
  const data = await res.json();
  return Array.isArray(data) ? data : (data.results ?? []);
}

/** صندوق نقدي — كيانٌ خادميّ وحسابُه في الشجرة وجهُه المحاسبي (T-CASHBOX). */
export type CashBoxLedgerLink = {
  id: number;
  /** مفتاح توافق مع قرّاء المرآة القدامى — يولّده الخادم ولا يُعدَّل. */
  external_id: string;
  name: string;
  currency_code: string;
  account_id: number;
  account_code: string;
  /** task16 E16: رصيد دفتر الأستاذ الحقيقي (مدين − دائن، قيود مرحَّلة) */
  balance?: string;
  is_default?: boolean;
  is_active?: boolean;
  notes?: string | null;
};

/** سطر في كشف الصندوق الخادمي — الرصيد فيه جارٍ حقيقي لا مجموع ترتيبٍ مُلفَّق. */
export type CashBoxStatementRow = {
  journal_line_id: number;
  journal_id: number;
  date: string;
  reference_type: string | null;
  reference_id: number | null;
  description: string;
  partner: string | null;
  debit: string;
  credit: string;
  balance: string;
};

export type CashBoxStatement = {
  cash_box_id: number;
  account_id: number;
  currency_code: string;
  name?: string;
  opening_balance: string;
  closing_balance: string;
  rows: CashBoxStatementRow[];
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

  /**
   * رسوم الفواتير الدولية: يُرجع حساب المصروف المطابق للاسم تحت «53 مصاريف الاستيراد»
   * أو يُنشئه هناك إن لم يكن موجوداً.
   */
  resolveImportExpenseAccount: async (name: string) => {
    const res = await fetch(`${ACC}/accounts/resolve-import-expense/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ name }),
    });
    await handle(res, "resolveImportExpenseAccount");
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

  /** قائمة القيود مُرقَّمة — مرِّر page/page_size ضمن params (صيانة الأداء 2026-07). */
  getJournalsPaged: async (params: Record<string, string>) => {
    const res = await fetch(`${ACC}/journals/?${new URLSearchParams(params)}`, {
      headers: headers(),
    });
    await handle(res, "getJournalsPaged");
    return toPagedList(await res.json());
  },

  /** A3: مستخدمو دفتر اليومية — خيارات فلتر «المستخدم» في الشركة الحالية. */
  getJournalUsers: () =>
    fetch(`${ACC}/journals/users/`, { headers: headers() }).then(asList) as Promise<
      Array<{ id: number; name: string }>
    >,

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
  //
  // T-PARTYPURE: `partnerType` يفلتر على الخادم — شاشة الزبائن لا تعرض موردين
  // وبالعكس. الفلترة هنا لا في كل شاشة، فلا تتكرر القاعدة ولا تُنسى في واحدة.
  getPartners: async (partnerType?: string) => {
    const db = (await import("./offline/db")).default;
    const tenantId = resolveTenantId();
    const cacheMetaKey = tenantScopedOfflineKey(
      tenantId, partnerType ? `partners:list:${partnerType}` : "partners:list");
    try {
      const query = partnerType
        ? `?limit=500&partner_type=${encodeURIComponent(partnerType)}`
        : "?limit=500";
      const data = await fetch(`${API_BASE}/partners/lookup/${query}`, { headers: headers() }).then(asList);
      try {
        const now = new Date().toISOString();
        for (const p of data as Array<Record<string, unknown>>) {
          const id = Number(p.id);
          if (!Number.isFinite(id)) continue;
          await db.partners.put({
            id,
            tenant_id: tenantId,
            name: String(p.name ?? ""),
            partner_type: String(p.partner_type ?? ""),
            data: JSON.stringify(p),
            updated_at: now,
          });
        }
        await db.cache_meta.put({ key: cacheMetaKey, updated_at: now });
      } catch { /* IndexedDB unavailable in private mode — non-fatal */ }
      return data;
    } catch {
      // Network failed — fall back to the last cached snapshot.
      try {
        const cached = await db.partners.where("tenant_id").equals(tenantId).toArray();
        return cached
          .filter((c) => !partnerType || c.partner_type === partnerType)
          .map((c) => JSON.parse(c.data));
      } catch {
        return [];
      }
    }
  },

  getCostCenters: () =>
    fetch(`${ACC}/cost-centers/`, { headers: headers() }).then(asList),

  /* ── T-BANKS: البنوك وفروعها وحساباتها والمطابقة البنكية ── */

  getBanks: (activeOnly = false) =>
    fetch(`${ACC}/banks/${activeOnly ? "?active_only=1" : ""}`, { headers: headers() }).then(asList),

  createBank: async (body: Record<string, unknown>): Promise<BankDto> => {
    const res = await fetch(`${ACC}/banks/`, {
      method: "POST", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "createBank");
    return res.json();
  },

  updateBank: async (id: number, body: Record<string, unknown>): Promise<BankDto> => {
    const res = await fetch(`${ACC}/banks/${id}/`, {
      method: "PATCH", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "updateBank");
    return res.json();
  },

  deleteBank: async (id: number) => {
    const res = await fetch(`${ACC}/banks/${id}/`, { method: "DELETE", headers: headers() });
    await handle(res, "deleteBank");
  },

  getBankBranches: (bankId?: number) =>
    fetch(`${ACC}/bank-branches/${bankId ? `?bank=${bankId}` : ""}`, { headers: headers() }).then(asList),

  createBankBranch: async (body: Record<string, unknown>): Promise<BankBranchDto> => {
    const res = await fetch(`${ACC}/bank-branches/`, {
      method: "POST", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "createBankBranch");
    return res.json();
  },

  updateBankBranch: async (id: number, body: Record<string, unknown>): Promise<BankBranchDto> => {
    const res = await fetch(`${ACC}/bank-branches/${id}/`, {
      method: "PATCH", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "updateBankBranch");
    return res.json();
  },

  deleteBankBranch: async (id: number) => {
    const res = await fetch(`${ACC}/bank-branches/${id}/`, { method: "DELETE", headers: headers() });
    await handle(res, "deleteBankBranch");
  },

  getBankAccounts: (params: { bank?: number; activeOnly?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (params.bank) q.set("bank", String(params.bank));
    if (params.activeOnly) q.set("active_only", "1");
    const qs = q.toString();
    return fetch(`${ACC}/bank-accounts/${qs ? `?${qs}` : ""}`, { headers: headers() }).then(asList);
  },

  createBankAccount: async (body: Record<string, unknown>): Promise<BankAccountDto> => {
    const res = await fetch(`${ACC}/bank-accounts/`, {
      method: "POST", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "createBankAccount");
    return res.json();
  },

  updateBankAccount: async (id: number, body: Record<string, unknown>): Promise<BankAccountDto> => {
    const res = await fetch(`${ACC}/bank-accounts/${id}/`, {
      method: "PATCH", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "updateBankAccount");
    return res.json();
  },

  deleteBankAccount: async (id: number) => {
    const res = await fetch(`${ACC}/bank-accounts/${id}/`, { method: "DELETE", headers: headers() });
    await handle(res, "deleteBankAccount");
  },

  getBankStatement: async (
    id: number,
    params: { start_date?: string; end_date?: string } = {},
  ): Promise<BankStatementDto> => {
    const q = new URLSearchParams();
    if (params.start_date) q.set("start_date", params.start_date);
    if (params.end_date) q.set("end_date", params.end_date);
    const qs = q.toString();
    const res = await fetch(`${ACC}/bank-accounts/${id}/statement/${qs ? `?${qs}` : ""}`, {
      headers: headers(),
    });
    await handle(res, "bankStatement");
    return res.json();
  },

  getBankReconciliations: (bankAccountId?: number) =>
    fetch(`${ACC}/bank-reconciliations/${bankAccountId ? `?bank_account=${bankAccountId}` : ""}`, {
      headers: headers(),
    }).then(asList),

  createBankReconciliation: async (body: Record<string, unknown>) => {
    const res = await fetch(`${ACC}/bank-reconciliations/`, {
      method: "POST", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "createBankReconciliation");
    return res.json();
  },

  getBankReconciliationSummary: async (id: number): Promise<BankReconciliationSummaryDto> => {
    const res = await fetch(`${ACC}/bank-reconciliations/${id}/summary/`, { headers: headers() });
    await handle(res, "bankReconciliationSummary");
    return res.json();
  },

  toggleBankReconciliationLine: async (
    id: number, journalLine: number, cleared: boolean,
  ): Promise<BankReconciliationSummaryDto> => {
    const res = await fetch(`${ACC}/bank-reconciliations/${id}/toggle-line/`, {
      method: "POST", headers: headers(),
      body: JSON.stringify({ journal_line: journalLine, cleared }),
    });
    await handle(res, "toggleBankReconciliationLine");
    return res.json();
  },

  closeBankReconciliation: async (id: number): Promise<BankReconciliationSummaryDto> => {
    const res = await fetch(`${ACC}/bank-reconciliations/${id}/close/`, {
      method: "POST", headers: headers(), body: "{}",
    });
    await handle(res, "closeBankReconciliation");
    return res.json();
  },

  reopenBankReconciliation: async (id: number): Promise<BankReconciliationSummaryDto> => {
    const res = await fetch(`${ACC}/bank-reconciliations/${id}/reopen/`, {
      method: "POST", headers: headers(), body: "{}",
    });
    await handle(res, "reopenBankReconciliation");
    return res.json();
  },

  deleteBankReconciliation: async (id: number) => {
    const res = await fetch(`${ACC}/bank-reconciliations/${id}/`, {
      method: "DELETE", headers: headers(),
    });
    await handle(res, "deleteBankReconciliation");
  },

  /**
   * CHQ-4: قائمة الشيكات مفلترةً في الخادم ومُرقَّمة. كانت تُسحب كاملةً ثم
   * تُفلتر في المتصفح — جدولٌ ينمو بلا حدّ يُبثّ في كل فتح للشاشة. بلا
   * `page` تعود مصفوفة خام (الترقيم opt-in) فلا ينكسر مستهلك قائم.
   */
  getChequesPage: async (params: {
    search?: string;
    status?: string;
    direction?: string;
    partner?: string;
    due_from?: string;
    due_to?: string;
    ordering?: string;
    page?: number;
    page_size?: number;
  } = {}): Promise<{ results: ChequeDto[]; count: number }> => {
    const qs = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        qs.set(key, String(value));
      }
    }
    const res = await fetch(`${ACC}/cheques/?${qs.toString()}`, { headers: headers() });
    await handle(res, "getCheques");
    const data = await res.json();
    return Array.isArray(data)
      ? { results: data as ChequeDto[], count: data.length }
      : { results: (data.results ?? []) as ChequeDto[], count: data.count ?? 0 };
  },

  getCheques: () =>
    fetch(`${ACC}/cheques/`, { headers: headers() }).then(asList),

  /** T-CHQ2: محفظة الشيكات — الأوراق المفتوحة بالحالة وبآجال الاستحقاق. */
  getChequeWallet: async () => {
    const res = await fetch(`${ACC}/cheques/wallet/`, { headers: headers() });
    await handle(res, "getChequeWallet");
    return res.json();
  },

  /** T-CHQ2: مسار الشيك — حركاته بالترتيب. */
  getChequeMovements: (id: number) =>
    fetch(`${ACC}/cheques/${id}/movements/`, { headers: headers() }).then(asList),

  createCheque: async (body: Record<string, unknown>) => {
    const res = await fetch(`${ACC}/cheques/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createCheque");
    return res.json();
  },

  /**
   * CHQ-4: إيداع حزمة شيكات دفعةً واحدة — ذرّي في الخادم (الكلّ أو لا شيء).
   * الرفض يعود 400 بجسمٍ فيه `rejected: [{cheque_id, cheque_number, reason}]`
   * فتُسمّي الشاشة الأوراق المخالفة بدل رسالة عامة.
   */
  depositChequesBatch: async (body: {
    cheque_ids: number[];
    bank_account?: number | null;
    movement_date?: string;
    notes?: string;
  }): Promise<ChequeDepositBatchResult> => {
    const res = await fetch(`${ACC}/cheques/deposit-batch/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "depositChequesBatch");
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

  /** ينشئ صندوقاً: الخادم يكتب الحساب في الشجرة ووثيقة المرآة في معاملة واحدة.
   *
   * T-CASHBOX M2: كان الإنشاء نداءين من المتصفح (المرآة ثم الحساب) فيبقى
   * صندوقٌ بلا حساب متى فشل الثاني. `external_id` صار اختيارياً — يولّده الخادم.
   */
  createCashBox: async (body: {
    name: string;
    currency_code?: string;
    external_id?: string;
    is_default?: boolean;
    notes?: string;
  }): Promise<CashBoxLedgerLink> => {
    const res = await fetch(`${ACC}/cash-box-accounts/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createCashBox");
    return res.json();
  },

  /** تعديل صندوق — الاسم يزامن حسابه في الشجرة، والتعطيل يخفيه من المنتقيات. */
  updateCashBox: async (
    id: number,
    body: { name?: string; is_active?: boolean; notes?: string; currency_code?: string },
  ): Promise<CashBoxLedgerLink> => {
    const res = await fetch(`${ACC}/cash-box-accounts/${id}/`, {
      method: "PATCH", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "updateCashBox");
    return res.json();
  },

  setDefaultCashBox: async (id: number): Promise<CashBoxLedgerLink> => {
    const res = await fetch(`${ACC}/cash-box-accounts/${id}/set-default/`, {
      method: "POST", headers: headers(), body: "{}",
    });
    await handle(res, "setDefaultCashBox");
    return res.json();
  },

  getMyDefaultCashBox: async (): Promise<{ cash_box: number | null; cash_box_name: string | null }> => {
    const res = await fetch(`${ACC}/cash-box-accounts/my-default/`, { headers: headers() });
    await handle(res, "getMyDefaultCashBox");
    return res.json();
  },

  setMyDefaultCashBox: async (cashBoxId: number | null) => {
    const res = await fetch(`${ACC}/cash-box-accounts/my-default/`, {
      method: "PUT", headers: headers(), body: JSON.stringify({ cash_box: cashBoxId }),
    });
    await handle(res, "setMyDefaultCashBox");
    return res.json();
  },

  /** كشف الصندوق برصيد جارٍ خادمي — بديل دمج المصدرين في المتصفح. */
  getCashBoxStatement: async (
    id: number,
    params: { start_date?: string; end_date?: string; include_unposted?: boolean } = {},
  ): Promise<CashBoxStatement> => {
    const qs = new URLSearchParams();
    if (params.start_date) qs.set("start_date", params.start_date);
    if (params.end_date) qs.set("end_date", params.end_date);
    if (params.include_unposted) qs.set("include_unposted", "true");
    const suffix = qs.toString() ? `?${qs}` : "";
    const res = await fetch(`${ACC}/cash-box-accounts/${id}/statement/${suffix}`, {
      headers: headers(),
    });
    await handle(res, "getCashBoxStatement");
    return res.json();
  },

  /** إيداع في الصندوق أو سحب منه — قيدٌ واحد، بلا خطوة مرآة منفصلة. */
  adjustCashBox: async (
    id: number,
    body: {
      direction: "in" | "out";
      amount: string | number;
      date?: string;
      memo?: string;
      contra_account?: number;
    },
  ) => {
    const res = await fetch(`${ACC}/cash-box-accounts/${id}/adjust/`, {
      method: "POST", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "adjustCashBox");
    return res.json() as Promise<{ journal_id: number }>;
  },

  /** تحويل بين الخزائن — مستندٌ واحد بقيدٍ واحد. */
  createCashTransfer: async (body: {
    transfer_date: string;
    amount: string | number;
    from_cash_box?: number;
    from_bank_account?: number;
    to_cash_box?: number;
    to_bank_account?: number;
    rate?: string | number;
    notes?: string;
  }) => {
    const res = await fetch(`${ACC}/cash-transfers/`, {
      method: "POST", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "createCashTransfer");
    return res.json();
  },

  listCashTransfers: () =>
    fetch(`${ACC}/cash-transfers/`, { headers: headers() }).then(asList),

  /** جرد صندوق: يُفتح بالمعدود ثم يُرحَّل فرقه. */
  createCashCount: async (body: {
    cash_box: number;
    count_date: string;
    counted_total: string | number;
    denominations?: Record<string, number>;
    notes?: string;
  }) => {
    const res = await fetch(`${ACC}/cash-counts/`, {
      method: "POST", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "createCashCount");
    return res.json();
  },

  postCashCount: async (id: number) => {
    const res = await fetch(`${ACC}/cash-counts/${id}/post/`, {
      method: "POST", headers: headers(), body: "{}",
    });
    await handle(res, "postCashCount");
    return res.json();
  },

  listCashCounts: () =>
    fetch(`${ACC}/cash-counts/`, { headers: headers() }).then(asList),

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

  // ── صندوق العملة الأجنبية FIFO (صندوق الدولار) ──
  fundFxBoxFromCapital: async (
    id: number,
    body: { amount: string | number; rate: string | number; date?: string },
  ) => {
    const res = await fetch(`${ACC}/cash-box-accounts/${id}/fund-capital/`, {
      method: "POST", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "fundFxBoxFromCapital");
    return res.json();
  },

  transferIlsToFxBox: async (
    id: number,
    body: { ils_box_id: number; amount: string | number; rate: string | number; date?: string },
  ) => {
    const res = await fetch(`${ACC}/cash-box-accounts/${id}/transfer-from-ils/`, {
      method: "POST", headers: headers(), body: JSON.stringify(body),
    });
    await handle(res, "transferIlsToFxBox");
    return res.json();
  },

  getFxBoxLots: async (id: number) => {
    const res = await fetch(`${ACC}/cash-box-accounts/${id}/fx-lots/`, { headers: headers() });
    await handle(res, "getFxBoxLots");
    return res.json() as Promise<{
      currency_code: string;
      fc_balance: string;
      ils_value: string;
      lots: Array<{
        id: number; lot_date: string; original_fc: string;
        remaining_fc: string; rate: string; source: string; journal: number | null;
      }>;
    }>;
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

  /** `granularity` الافتراضي شهريّ — 12 فترة تُقفَل واحدةً واحدة. */
  createFiscalYear: async (year: number, granularity: "monthly" | "yearly" = "monthly") => {
    const res = await fetch(`${ACC}/fiscal-periods/create-year/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ year, granularity }),
    });
    await handle(res, "createFiscalYear");
    return res.json();
  },

  /** 409 = قيود غير مرحّلة داخل الفترة؛ يعيدها للواجهة لتسأل ثم تُعيد بـforce. */
  closeFiscalPeriod: async (id: number, force = false) => {
    const res = await fetch(`${ACC}/fiscal-periods/${id}/close/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ force }),
    });
    if (res.status === 409) {
      const body = await res.json().catch(() => ({}));
      return { requires_force: true as const, error: body.error as string | undefined };
    }
    await handle(res, "closeFiscalPeriod");
    return res.json();
  },

  /** `reason` إلزامي — يُحفظ في سجل التدقيق كصلاحية استثناء مسجَّلة. */
  reopenFiscalPeriod: async (id: number, reason: string) => {
    const res = await fetch(`${ACC}/fiscal-periods/${id}/reopen/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ reason }),
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

  // ─── الأرصدة الافتتاحية (THA-119) ───
  // مستند واحد لكل شركة، فالمسارات كلها بلا معرّف. كل نداء يُرجع الحمولة كاملة
  // (الحالة + البنود + الأطراف + المجاميع) — فلا تحتاج الشاشة إعادة قراءة بعد كل
  // كتابة، ولا يمكن أن يفترق ما تعرضه عمّا في الخادم.

  getOpeningBalance: async (): Promise<OpeningBalanceDto> => {
    const res = await fetch(`${ACC}/opening-balance/`, { headers: headers() });
    await handle(res, "getOpeningBalance");
    return res.json();
  },

  /** حفظ جماعي للمسودة — الرِّجل الغائبة عن الجسم لا تُمَسّ. */
  saveOpeningBalanceLines: async (body: OpeningBalanceLinesInput): Promise<OpeningBalanceDto> => {
    const res = await fetch(`${ACC}/opening-balance/lines/`, {
      method: "PUT",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "saveOpeningBalanceLines");
    return res.json();
  },

  postOpeningBalance: async (): Promise<OpeningBalanceDto> => {
    const res = await fetch(`${ACC}/opening-balance/post/`, {
      method: "POST",
      headers: headers(),
      body: "{}",
    });
    await handle(res, "postOpeningBalance");
    return res.json();
  },

  unpostOpeningBalance: async (): Promise<OpeningBalanceDto> => {
    const res = await fetch(`${ACC}/opening-balance/unpost/`, {
      method: "POST",
      headers: headers(),
      body: "{}",
    });
    await handle(res, "unpostOpeningBalance");
    return res.json();
  },

  /** عكس قيد الرصيد الافتتاحي لطرف واحد — الطريق الوحيد لتعديل رصيد مرحّل. */
  reversePartnerOpeningBalance: async (partnerId: number): Promise<OpeningBalanceDto> => {
    const res = await fetch(`${ACC}/opening-balance/partners/${partnerId}/reverse/`, {
      method: "POST",
      headers: headers(),
      body: "{}",
    });
    await handle(res, "reversePartnerOpeningBalance");
    return res.json();
  },

  /**
   * رصيد الطرف الافتتاحي يُكتب في بطاقة الطرف نفسها (`PATCH /api/partners/{id}/`)
   * — الآلية القائمة تُرحِّله بإشارة الحفظ. تركُ التاريخ فارغاً يجعله يتبع تاريخ
   * القيد الافتتاحي للشركة، فتتوحّد تواريخ كل أرجل الافتتاح.
   */
  savePartnerOpeningBalance: async (
    partnerId: number,
    body: { opening_balance: string; opening_balance_date?: string | null },
  ) => {
    const res = await fetch(`${API_BASE}/partners/${partnerId}/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "savePartnerOpeningBalance");
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
