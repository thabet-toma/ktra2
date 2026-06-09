import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Banknote,
  Plus,
  Trash2,
  Check,
  AlertCircle,
  Sparkles,
  X,
  Search,
  ChevronRight,
  ChevronLeft,
  ChevronsRight,
  ChevronsLeft,
  Printer,
  FileDown,
  RefreshCw,
} from "lucide-react";
import { AseelSpinner } from "../aseel/AseelStates";
import {
  listCustomerPayments,
  createCustomerPayment,
  postCustomerPayment,
  deleteCustomerPayment,
  suggestFifoAllocations,
  getAgingReport,
  type CustomerPaymentRow,
} from "../../services/salesApi";
import { accountingApi } from "../../services/accountingApi";
import {
  AseelDocumentShell,
  useRecordNavigation,
  useAseelKeymap,
  AseelTabs,
} from "../aseel";

type Partner = { id: number; name: string };
type Account = { id: number; code: string; name: string; account_type?: string };
type Currency = { CurrencyID: number; Code: string; Name?: string };

type AgingInvoice = {
  invoice_id: number;
  invoice_number: string;
  customer_id: number;
  customer_name: string;
  invoice_date: string;
  grand_total: string;
  amount_paid: string;
  remaining: string;
};

export const SalesCustomerPaymentsPage: React.FC = () => {
  const navigate = useNavigate();
  const [payments, setPayments] = useState<CustomerPaymentRow[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [aging, setAging] = useState<AgingInvoice[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [search, setSearch] = useState("");

  // M4-T3: Aseel Navigation for customer payments
  const [selectedPayment, setSelectedPayment] = useState<CustomerPaymentRow | null>(null);
  const [showPartnerPicker, setShowPartnerPicker] = useState(false);

  const nav = useRecordNavigation<CustomerPaymentRow>({
    items: payments,
    getId: (p) => p.id || 0,
    currentId: selectedPayment?.id || null,
    onSelect: (id) => {
      if (id === null) {
        setSelectedPayment(null);
        setShowForm(true);
      } else {
        const found = payments.find(p => p.id === id);
        setSelectedPayment(found || null);
      }
    },
  });

  // M4-T3: Aseel keyboard shortcuts — real handlers.
  useAseelKeymap({
    F2: () => window.print(),
    F5: () => loadAll(),
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-aseel-field="search"]');
      el?.focus();
    },
    Escape: () => {
      if (showPartnerPicker) { setShowPartnerPicker(false); return; }
      if (showForm || selectedPayment) {
        setShowForm(false);
        setSelectedPayment(null);
      } else {
        navigate(-1);
      }
    },
    plus: () => {
      const ae = document.activeElement;
      if (ae?.getAttribute?.('data-aseel-key') === '1') {
        setShowPartnerPicker(true);
      }
    },
    // N0-T11: Ctrl+nav handlers
    CtrlHome: () => nav?.first?.(),
    CtrlEnd: () => nav?.last?.(),
    CtrlPageUp: () => nav?.prev?.(),
    CtrlPageDown: () => nav?.next?.(),
    CtrlIns: () => { setSelectedPayment(null); setShowForm(true); },
  }, { enabled: !showPartnerPicker });

  const loadAll = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [pays, parts, accs, currs, ag] = await Promise.all([
        listCustomerPayments(),
        accountingApi.getPartners() as Promise<Partner[]>,
        accountingApi.getAccounts() as Promise<Account[]>,
        accountingApi.getCurrencies() as Promise<Currency[]>,
        getAgingReport(),
      ]);
      setPayments(pays || []);
      setPartners(parts || []);
      setAccounts(accs || []);
      setCurrencies(currs || []);
      setAging(ag || []);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const fmt = (n: string | number) =>
    Number(n).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

  const partnerName = (id: number) =>
    partners.find((p) => p.id === id)?.name || `#${id}`;

  const accountName = (id: number) => {
    const a = accounts.find((x) => x.id === id);
    return a ? `${a.code} ${a.name}` : `#${id}`;
  };

  const handlePost = async (id: number) => {
    if (!confirm("ترحيل الدفعة سينشئ قيداً محاسبياً ويسدّد الفواتير. متابعة؟"))
      return;
    try {
      await postCustomerPayment(id);
      await loadAll();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "فشل الترحيل");
    }
  };

  const handleDelete = async (id: number, isPosted: boolean) => {
    if (isPosted) {
      alert("لا يمكن حذف دفعة مرحّلة. ألغِ الترحيل أولاً.");
      return;
    }
    if (!confirm("حذف الدفعة؟")) return;
    try {
      await deleteCustomerPayment(id);
      setPayments((ps) => ps.filter((p) => p.id !== id));
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "فشل الحذف");
    }
  };

  const filtered = useMemo(() => {
    if (!search.trim()) return payments;
    const s = search.toLowerCase();
    return payments.filter(
      (p) =>
        partnerName(p.partner).toLowerCase().includes(s) ||
        (p.notes || "").toLowerCase().includes(s) ||
        String(p.id).includes(s),
    );
  }, [payments, search, partners]);

  const totalPending = payments
    .filter((p) => !p.is_posted)
    .reduce((s, p) => s + Number(p.amount), 0);
  const totalPosted = payments
    .filter((p) => p.is_posted)
    .reduce((s, p) => s + Number(p.amount), 0);

  return (
    <div
      data-skin="aseel"
      style={{ height: 'calc(100vh - 5rem)', display: 'flex', flexDirection: 'column' }}
    >
    <AseelDocumentShell
      title="سند قبض/صرف"
      state={selectedPayment ? `سند #${selectedPayment.id}` : 'دفعات العملاء'}
      nav={nav}
      actions={[
        { key: 'new', label: 'سند جديد', icon: <Plus />, onClick: () => setShowForm(true) },
        { key: 'reload', label: 'تحديث', icon: <RefreshCw />, onClick: () => loadAll(), separatorBefore: true },
        { key: 'print', label: 'طباعة', icon: <Printer />, onClick: () => window.print() },
        { key: 'cancel', label: 'إلغاء', icon: <X />, onClick: () => {
          if (showForm || selectedPayment) {
            setShowForm(false);
            setSelectedPayment(null);
          } else {
            navigate(-1);
          }
        }, danger: true, separatorBefore: true },
      ]}
      header={<></>}
      status={
        <>
          <span className="aseel-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
          <span className="aseel-status-item">{payments.length} سند</span>
        </>
      }
    >
    <div className="space-y-4" dir="rtl" style={{ height: '100%', overflow: 'auto', padding: '12px', background: '#ffffff' }}>
      <div className="flex flex-wrap items-center gap-3 p-4 bg-gradient-to-l aseel-bg-panel aseel-bg-panel text-white rounded-xl">
        <Banknote className="w-8 h-8 aseel-text-soft" />
        <div className="flex-1">
          <h1 className="text-lg font-bold">دفعات العملاء</h1>
          <p className="text-xs aseel-text-soft">
            تحصيل من الذمم المدينة مع توزيع FIFO وترحيل محاسبي
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 px-4 py-2 aseel-bg-panel hover:aseel-bg-panel rounded-lg text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          دفعة جديدة
        </button>
      </div>

      {err && (
        <div className="p-3 rounded-lg aseel-bg-panel dark:aseel-bg-panel/20 aseel-text-state text-sm flex gap-2 items-center">
          <AlertCircle className="w-4 h-4" />
          {err}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="rounded-xl border aseel-border-soft dark:aseel-border-soft/40 aseel-bg-panel/60 dark:aseel-bg-panel/10 p-4">
          <div className="text-xs aseel-text-ink dark:aseel-text-soft font-semibold">
            إجمالي مرحّل
          </div>
          <div className="text-2xl font-bold aseel-text-ink dark:aseel-text-soft">
            {fmt(totalPosted)}
          </div>
        </div>
        <div className="rounded-xl border aseel-border-soft dark:aseel-border-soft/40 aseel-bg-panel/60 dark:aseel-bg-panel/10 p-4">
          <div className="text-xs aseel-text-ink dark:aseel-text-soft font-semibold">
            بانتظار الترحيل
          </div>
          <div className="text-2xl font-bold aseel-text-ink dark:aseel-text-soft">
            {fmt(totalPending)}
          </div>
        </div>
        <div className="rounded-xl border aseel-border-soft dark:aseel-border-soft/40 aseel-bg-panel/60 dark:aseel-bg-panel/10 p-4">
          <div className="text-xs aseel-text-ink dark:aseel-text-soft font-semibold">
            فواتير مفتوحة (AR)
          </div>
          <div className="text-2xl font-bold aseel-text-ink dark:aseel-text-soft">
            {aging.length}
          </div>
          <div className="text-[11px] aseel-text-ink/70 mt-1">
            {fmt(aging.reduce((s, a) => s + Number(a.remaining), 0))} متبقي
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 aseel-text-soft" />
          <input
            type="text"
            placeholder="بحث..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pr-9 pl-3 py-2 border rounded-lg dark:aseel-bg-panel dark:aseel-border-soft"
          />
        </div>
      </div>

      {loading ? (
        <AseelSpinner />
      ) : (
        <div className="overflow-x-auto aseel-bg-field dark:aseel-bg-panel rounded-xl border aseel-border-soft dark:aseel-border-soft">
          <table className="min-w-full text-sm">
            <thead className="aseel-bg-panel dark:aseel-bg-panel/50">
              <tr>
                <th className="text-right p-3">#</th>
                <th className="text-right p-3">التاريخ</th>
                <th className="text-right p-3">العميل</th>
                <th className="text-right p-3">المبلغ</th>
                <th className="text-right p-3">الصندوق / البنك</th>
                <th className="text-right p-3">التوزيعات</th>
                <th className="text-center p-3">الحالة</th>
                <th className="text-center p-3">إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => (
                <tr
                  key={p.id}
                  className="border-t aseel-border-soft dark:aseel-border-soft"
                >
                  <td className="p-2 font-mono">#{p.id}</td>
                  <td className="p-2">{p.payment_date}</td>
                  <td className="p-2">{partnerName(p.partner)}</td>
                  <td className="p-2 font-semibold">{fmt(p.amount)}</td>
                  <td className="p-2 text-xs">
                    {accountName(p.cash_or_bank_account)}
                  </td>
                  <td className="p-2">
                    <div className="text-xs space-y-0.5">
                      {p.allocations && p.allocations.length > 0 ? (
                        p.allocations.map((a) => (
                          <div key={a.id || a.invoice}>
                            فاتورة #{a.invoice} = {fmt(a.amount)}
                          </div>
                        ))
                      ) : (
                        <span className="aseel-text-soft">بدون توزيع</span>
                      )}
                    </div>
                  </td>
                  <td className="p-2 text-center">
                    {p.is_posted ? (
                      <span className="text-xs px-2 py-1 aseel-bg-panel dark:aseel-bg-panel/30 aseel-text-ink dark:aseel-text-soft rounded-full">
                        مرحّلة {p.journal ? `#${p.journal}` : ""}
                      </span>
                    ) : (
                      <span className="text-xs px-2 py-1 aseel-bg-panel dark:aseel-bg-panel/30 aseel-text-ink dark:aseel-text-soft rounded-full">
                        مسودة
                      </span>
                    )}
                  </td>
                  <td className="p-2 text-center">
                    <div className="flex items-center gap-1 justify-center">
                      {!p.is_posted && (
                        <button
                          type="button"
                          onClick={() => handlePost(p.id)}
                          className="p-1.5 aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel/30 rounded"
                          title="ترحيل"
                        >
                          <Check className="w-4 h-4" />
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => handleDelete(p.id, p.is_posted)}
                        className="p-1.5 aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel/30 rounded disabled:opacity-40"
                        disabled={p.is_posted}
                        title="حذف"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <p className="p-8 text-center aseel-text-soft">لا توجد دفعات</p>
          )}
        </div>
      )}

      {showForm && (
        <NewPaymentModal
          partners={partners}
          accounts={accounts}
          currencies={currencies}
          aging={aging}
          onClose={() => setShowForm(false)}
          onSaved={async () => {
            setShowForm(false);
            await loadAll();
          }}
        />
      )}
    </div>
    </AseelDocumentShell>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// Modal إنشاء دفعة
// N4-T4: + حقول خصم المصدر (withholding) + grid شيكات + tabs ملاحظات/حسابات
// ═══════════════════════════════════════════════════════════════════════════
interface ChequeLine {
  cheque_number: string;
  payee_name: string;
  due_date: string;
  amount: string;
  bank_name: string;
  branch: string;
}

const newChequeLine = (): ChequeLine => ({
  cheque_number: "",
  payee_name: "",
  due_date: "",
  amount: "",
  bank_name: "",
  branch: "",
});

const NewPaymentModal: React.FC<{
  partners: Partner[];
  accounts: Account[];
  currencies: Currency[];
  aging: AgingInvoice[];
  onClose: () => void;
  onSaved: () => void;
}> = ({ partners, accounts, currencies, aging, onClose, onSaved }) => {
  const today = new Date().toISOString().split("T")[0];
  const [partnerId, setPartnerId] = useState<number | "">("");
  const [date, setDate] = useState(today);
  const [amount, setAmount] = useState(""); // total payment amount
  const [cashAmount, setCashAmount] = useState(""); // N4-T4: نقد جزء
  const [currencyId, setCurrencyId] = useState<number | "">("");
  const [exchangeRate, setExchangeRate] = useState("1");
  const [cashAccountId, setCashAccountId] = useState<number | "">("");
  const [notes, setNotes] = useState("");
  // N4-T4: withholding (خصم المصدر) — يُحسَب من amount
  const [withholdingPct, setWithholdingPct] = useState("0");
  const [withholdingAmt, setWithholdingAmt] = useState("0");
  // N4-T4: cheques inside payment (تفاصيل السند)
  const [cheques, setCheques] = useState<ChequeLine[]>([]);
  const [activeTab, setActiveTab] = useState<"alloc" | "cheques" | "notes" | "accounts">("alloc");
  const [allocations, setAllocations] = useState<
    Array<{ invoice: number; invoice_number?: string; amount: string }>
  >([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // مجموع الشيكات = sum cheques.amount
  const totalCheques = cheques.reduce((s, c) => s + (Number(c.amount) || 0), 0);
  const cashNum = Number(cashAmount) || 0;
  // المجموع = نقد + شيكات
  const computedTotal = cashNum + totalCheques;

  // N4-T4: تَحديث amount auto عند تَغيير cash/cheques
  useEffect(() => {
    if (computedTotal > 0) setAmount(String(computedTotal.toFixed(2)));
  }, [computedTotal]);

  // N4-T4: تَحديث withholdingAmt من النسبة
  useEffect(() => {
    const pct = Number(withholdingPct) || 0;
    const amt = (Number(amount) || 0) * (pct / 100);
    setWithholdingAmt(String(amt.toFixed(2)));
  }, [withholdingPct, amount]);

  useEffect(() => {
    // default currency = ILS if exists
    if (currencies.length && !currencyId) {
      const ils = currencies.find((c) => c.Code === "ILS");
      setCurrencyId((ils?.CurrencyID ?? currencies[0].CurrencyID) as number);
    }
  }, [currencies, currencyId]);

  const cashboxAccounts = useMemo(
    () =>
      accounts.filter((a) => {
        const t = a.account_type || "";
        if (t !== "Asset") return false;
        const code = String(a.code || "");
        const name = (a.name || "").toLowerCase();
        return (
          code.startsWith("110") ||
          name.includes("صندوق") ||
          name.includes("بنك") ||
          name.includes("cash") ||
          name.includes("bank")
        );
      }),
    [accounts],
  );

  const partnerAging = useMemo(
    () => aging.filter((a) => a.customer_id === partnerId),
    [aging, partnerId],
  );

  const totalAlloc = allocations.reduce((s, a) => s + Number(a.amount || 0), 0);
  const amtNum = Number(amount || 0);
  const diff = amtNum - totalAlloc;
  const canSubmit =
    partnerId &&
    amtNum > 0 &&
    cashAccountId &&
    currencyId &&
    Math.abs(diff) < 0.02;

  const suggestFifo = async () => {
    if (!partnerId || amtNum <= 0) {
      setError("اختر العميل وأدخل المبلغ أولاً");
      return;
    }
    try {
      const rows = await suggestFifoAllocations({
        partner: partnerId as number,
        amount: amount,
      });
      setAllocations(
        rows.map((r) => ({
          invoice: r.invoice,
          invoice_number: r.invoice_number,
          amount: r.amount,
        })),
      );
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "فشل اقتراح التوزيع");
    }
  };

  const updateAlloc = (idx: number, amt: string) => {
    setAllocations((as) => as.map((a, i) => (i === idx ? { ...a, amount: amt } : a)));
  };

  const removeAlloc = (idx: number) => {
    setAllocations((as) => as.filter((_, i) => i !== idx));
  };

  const submit = async () => {
    setError(null);
    if (!canSubmit) {
      setError("تأكد من تساوي مجموع التوزيعات مع مبلغ الدفعة");
      return;
    }
    setSubmitting(true);
    try {
      await createCustomerPayment({
        partner: partnerId as number,
        payment_date: date,
        amount,
        currency: currencyId as number,
        exchange_rate: exchangeRate,
        cash_or_bank_account: cashAccountId as number,
        notes,
        allocations: allocations.map((a) => ({
          invoice: a.invoice,
          amount: a.amount,
        })),
      });
      onSaved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "فشل الإنشاء");
    } finally {
      setSubmitting(false);
    }
  };

  const fmt = (n: string | number) =>
    Number(n).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

  return (
    <div
      className="fixed inset-0 bg-black/50 z-50 flex items-start justify-center p-4 overflow-auto"
      dir="rtl"
    >
      <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl shadow-xl w-full max-w-3xl mt-8">
        <div className="flex items-center justify-between p-4 border-b aseel-border-soft dark:aseel-border-soft">
          <h2 className="text-lg font-bold">دفعة عميل جديدة</h2>
          <button type="button" onClick={onClose} className="p-1 hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs aseel-text-soft mb-1">العميل *</label>
              <select
                className="w-full border rounded-lg px-3 py-2 dark:aseel-bg-panel dark:aseel-border-soft"
                value={partnerId}
                onChange={(e) => {
                  setPartnerId(e.target.value ? Number(e.target.value) : "");
                  setAllocations([]);
                }}
              >
                <option value="">اختر...</option>
                {partners.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs aseel-text-soft mb-1">التاريخ *</label>
              <input
                type="date"
                className="w-full border rounded-lg px-3 py-2 dark:aseel-bg-panel dark:aseel-border-soft"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs aseel-text-soft mb-1">المبلغ *</label>
              <input
                type="number"
                step="0.01"
                className="w-full border rounded-lg px-3 py-2 dark:aseel-bg-panel dark:aseel-border-soft"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs aseel-text-soft mb-1">العملة *</label>
              <select
                className="w-full border rounded-lg px-3 py-2 dark:aseel-bg-panel dark:aseel-border-soft"
                value={currencyId}
                onChange={(e) =>
                  setCurrencyId(e.target.value ? Number(e.target.value) : "")
                }
              >
                {currencies.map((c) => (
                  <option key={c.CurrencyID} value={c.CurrencyID}>
                    {c.Code} {c.Name ? `— ${c.Name}` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs aseel-text-soft mb-1">سعر الصرف</label>
              <input
                type="number"
                step="0.000001"
                className="w-full border rounded-lg px-3 py-2 dark:aseel-bg-panel dark:aseel-border-soft"
                value={exchangeRate}
                onChange={(e) => setExchangeRate(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs aseel-text-soft mb-1">الصندوق / البنك *</label>
              <select
                className="w-full border rounded-lg px-3 py-2 dark:aseel-bg-panel dark:aseel-border-soft"
                value={cashAccountId}
                onChange={(e) =>
                  setCashAccountId(e.target.value ? Number(e.target.value) : "")
                }
              >
                <option value="">اختر...</option>
                {cashboxAccounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.code} {a.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* N4-T4: حقول مالية: نقدا + شيكات + المجموع + خصم المصدر */}
          <div className="aseel-bg-panel/40 dark:aseel-bg-panel/10 border aseel-border-soft dark:aseel-border-soft/40 rounded-lg p-3">
            <h3 className="text-xs font-semibold aseel-text-ink dark:aseel-text-soft mb-2">حقول الدفع (N4-T4)</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              <div>
                <label className="block text-[11px] aseel-text-soft mb-0.5">نقدا (Space = remaining)</label>
                <input
                  type="number" step="0.01"
                  data-aseel-field="remaining-amount"
                  className="w-full border rounded px-2 py-1 text-sm dark:aseel-bg-panel dark:aseel-border-soft font-mono"
                  value={cashAmount}
                  onChange={(e) => setCashAmount(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-[11px] aseel-text-soft mb-0.5">مجموع الشيكات (auto)</label>
                <input type="text" readOnly className="w-full border rounded px-2 py-1 text-sm aseel-bg-panel dark:aseel-bg-panel font-mono" value={fmt(totalCheques)} />
              </div>
              <div>
                <label className="block text-[11px] aseel-text-soft mb-0.5">المجموع</label>
                <input type="text" readOnly className="w-full border rounded px-2 py-1 text-sm aseel-bg-panel dark:aseel-bg-panel font-mono font-semibold" value={fmt(computedTotal)} />
              </div>
              <div>
                <label className="block text-[11px] aseel-text-soft mb-0.5">نسبة خصم المصدر %</label>
                <input
                  type="number" step="0.01"
                  className="w-full border rounded px-2 py-1 text-sm dark:aseel-bg-panel dark:aseel-border-soft font-mono"
                  value={withholdingPct}
                  onChange={(e) => setWithholdingPct(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-[11px] aseel-text-soft mb-0.5">مبلغ خصم المصدر</label>
                <input
                  type="number" step="0.01"
                  className="w-full border rounded px-2 py-1 text-sm dark:aseel-bg-panel dark:aseel-border-soft font-mono"
                  value={withholdingAmt}
                  onChange={(e) => {
                    setWithholdingAmt(e.target.value);
                    const amt = Number(e.target.value) || 0;
                    const t = Number(amount) || 0;
                    if (t > 0) setWithholdingPct(((amt / t) * 100).toFixed(2));
                  }}
                />
              </div>
              <div>
                <label className="block text-[11px] aseel-text-soft mb-0.5">مبلغ الحساب (remaining)</label>
                <input
                  type="text" readOnly
                  className="w-full border rounded px-2 py-1 text-sm aseel-bg-panel dark:aseel-bg-panel/20 font-mono font-semibold"
                  value={fmt(Math.max(0, computedTotal - (Number(withholdingAmt) || 0)))}
                />
              </div>
            </div>
          </div>

          {/* Tabs using AseelTabs */}
          <AseelTabs
            activeTab={activeTab}
            onTabChange={(key) => setActiveTab(key as "alloc" | "cheques" | "notes" | "accounts")}
            tabs={[
              {
                key: "alloc",
                label: "التوزيع",
                content: (
                  <div className="border-t aseel-border-soft dark:aseel-border-soft pt-3">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="font-semibold text-sm">توزيع على الفواتير</h3>
                      <button
                        type="button"
                        onClick={suggestFifo}
                        disabled={!partnerId || amtNum <= 0}
                        className="flex items-center gap-1 text-xs px-3 py-1.5 bg-[var(--color-primary)] text-white rounded-lg disabled:opacity-40"
                      >
                        <Sparkles className="w-3 h-3" />
                        اقتراح FIFO
                      </button>
                    </div>

                    {partnerAging.length > 0 && allocations.length === 0 && (
                      <div className="mb-2 p-2 rounded aseel-bg-panel dark:aseel-bg-panel/20 text-xs aseel-text-ink">
                        {partnerAging.length} فاتورة مفتوحة للعميل — اضغط "اقتراح FIFO" للتوزيع
                        التلقائي أو أضف يدوياً.
                      </div>
                    )}

                    {allocations.length === 0 ? (
                      <div className="text-xs aseel-text-soft text-center py-3 border-2 border-dashed aseel-border-soft dark:aseel-border-soft rounded">
                        لا توزيعات بعد
                      </div>
                    ) : (
                      <table className="w-full text-sm">
                        <thead className="aseel-bg-panel dark:aseel-bg-panel/40">
                          <tr>
                            <th className="text-right p-2">الفاتورة</th>
                            <th className="text-right p-2">المبلغ</th>
                            <th className="w-10"></th>
                          </tr>
                        </thead>
                        <tbody>
                          {allocations.map((a, idx) => (
                            <tr key={idx} className="border-t aseel-border-soft dark:aseel-border-soft">
                              <td className="p-2">
                                {a.invoice_number || `#${a.invoice}`}
                              </td>
                              <td className="p-2">
                                <input
                                  type="number"
                                  step="0.01"
                                  className="w-full border rounded px-2 py-1 dark:aseel-bg-panel dark:aseel-border-soft"
                                  value={a.amount}
                                  onChange={(e) => updateAlloc(idx, e.target.value)}
                                />
                              </td>
                              <td className="p-1 text-center">
                                <button
                                  type="button"
                                  onClick={() => removeAlloc(idx)}
                                  className="p-1 aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel/30 rounded"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                        <tfoot className="aseel-bg-panel dark:aseel-bg-panel/40 font-semibold text-sm">
                          <tr>
                            <td className="p-2">الإجمالي / المطلوب {fmt(amtNum)}</td>
                            <td
                              className={`p-2 ${
                                Math.abs(diff) < 0.02 ? "aseel-text-ink" : "aseel-text-ink"
                              }`}
                            >
                              {fmt(totalAlloc)}
                              {Math.abs(diff) >= 0.02 && (
                                <span className="text-xs mr-2">(فرق {fmt(diff)})</span>
                              )}
                            </td>
                            <td></td>
                          </tr>
                        </tfoot>
                      </table>
                    )}
                  </div>
                )
              },
              {
                key: "cheques",
                label: `الشيكات (${cheques.length})`,
                content: (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-sm">تفاصيل الشيكات</h3>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            // N4-T4 (الجديد:29) تَعبئة شيكات متشابهة متكرّرة
                            const last = cheques[cheques.length - 1];
                            if (!last || !last.bank_name) {
                              setError("أضف شيكاً واحداً بكل البيانات أولاً");
                              return;
                            }
                            const months = Number(window.prompt("عدد الشيكات المتتالية (شهور)؟", "3") || "0");
                            if (months <= 0) return;
                            const baseDate = new Date(last.due_date || today);
                            const extra: ChequeLine[] = [];
                            for (let i = 1; i <= months; i++) {
                              const d = new Date(baseDate);
                              d.setMonth(d.getMonth() + i);
                              extra.push({
                                ...last,
                                cheque_number: "",
                                due_date: d.toISOString().split("T")[0],
                              });
                            }
                            setCheques((cs) => [...cs, ...extra]);
                            setError(null);
                          }}
                          className="flex items-center gap-1 text-xs px-2 py-1 border aseel-border-soft aseel-text-ink rounded"
                          title="تعبئة شيكات بنفس البنك/المبلغ لشهور متتالية (الجديد:29)"
                        >
                          تعبئة متشابهة
                        </button>
                        <button
                          type="button"
                          onClick={() => setCheques((cs) => [...cs, newChequeLine()])}
                          className="flex items-center gap-1 text-xs px-2 py-1 aseel-bg-panel text-white rounded"
                        >
                          <Plus className="w-3 h-3" /> شيك
                        </button>
                      </div>
                    </div>
                    {cheques.length === 0 ? (
                      <div className="text-xs aseel-text-soft text-center py-3 border-2 border-dashed aseel-border-soft dark:aseel-border-soft rounded">
                        لا شيكات — اضغط «شيك» للإضافة
                      </div>
                    ) : (
                      <table className="w-full text-xs">
                        <thead className="aseel-bg-panel dark:aseel-bg-panel/40">
                          <tr>
                            <th className="text-right p-1.5">#</th>
                            <th className="text-right p-1.5">رقم</th>
                            <th className="text-right p-1.5">صاحب الشيك</th>
                            <th className="text-right p-1.5">الاستحقاق</th>
                            <th className="text-right p-1.5">المبلغ</th>
                            <th className="text-right p-1.5">البنك</th>
                            <th className="text-right p-1.5">الفرع</th>
                            <th className="w-8"></th>
                          </tr>
                        </thead>
                        <tbody>
                          {cheques.map((c, i) => (
                            <tr key={i} className="border-t aseel-border-soft dark:aseel-border-soft">
                              <td className="p-1 text-center">{i + 1}</td>
                              <td className="p-1"><input className="w-full border rounded px-1 py-0.5 text-xs dark:aseel-bg-panel" value={c.cheque_number} onChange={(e) => setCheques((cs) => cs.map((x, j) => i === j ? { ...x, cheque_number: e.target.value } : x))} /></td>
                              <td className="p-1"><input className="w-full border rounded px-1 py-0.5 text-xs dark:aseel-bg-panel" value={c.payee_name} onChange={(e) => setCheques((cs) => cs.map((x, j) => i === j ? { ...x, payee_name: e.target.value } : x))} /></td>
                              <td className="p-1"><input type="date" className="w-full border rounded px-1 py-0.5 text-xs dark:aseel-bg-panel" value={c.due_date} onChange={(e) => setCheques((cs) => cs.map((x, j) => i === j ? { ...x, due_date: e.target.value } : x))} /></td>
                              <td className="p-1"><input type="number" step="0.01" className="w-full border rounded px-1 py-0.5 text-xs font-mono dark:aseel-bg-panel" value={c.amount} onChange={(e) => setCheques((cs) => cs.map((x, j) => i === j ? { ...x, amount: e.target.value } : x))} /></td>
                              <td className="p-1"><input className="w-full border rounded px-1 py-0.5 text-xs dark:aseel-bg-panel" value={c.bank_name} onChange={(e) => setCheques((cs) => cs.map((x, j) => i === j ? { ...x, bank_name: e.target.value } : x))} /></td>
                              <td className="p-1"><input className="w-full border rounded px-1 py-0.5 text-xs dark:aseel-bg-panel" value={c.branch} onChange={(e) => setCheques((cs) => cs.map((x, j) => i === j ? { ...x, branch: e.target.value } : x))} /></td>
                              <td className="p-1 text-center">
                                <button type="button" onClick={() => setCheques((cs) => cs.filter((_, j) => j !== i))} className="aseel-text-soft">
                                  <Trash2 className="w-3 h-3" />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )
              },
              {
                key: "notes",
                label: "الملاحظات",
                content: (
                  <div>
                    <label className="block text-xs aseel-text-soft mb-1">ملاحظات السند</label>
                    <textarea
                      rows={4}
                      className="w-full border rounded-lg px-3 py-2 dark:aseel-bg-panel dark:aseel-border-soft"
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                    />
                  </div>
                )
              },
              {
                key: "accounts",
                label: "الحسابات",
                content: (
                  <div className="text-xs aseel-text-soft dark:aseel-text-soft p-3 aseel-bg-panel dark:aseel-bg-panel/40 rounded">
                    معاينة القيد المحاسبي ستَظهر هنا بعد الترحيل. حالياً: Dr {(() => {
                      const a = accounts.find((x) => x.id === cashAccountId);
                      return a ? `${a.code} ${a.name}` : "—";
                    })()} / Cr ذمم العميل {(partners.find((p) => p.id === partnerId)?.name) || "—"}.
                  </div>
                )
              }
            ]}
          />

          {error && (
            <div className="p-2 rounded aseel-bg-panel dark:aseel-bg-panel/20 aseel-text-state text-sm">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 p-4 border-t aseel-border-soft dark:aseel-border-soft">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg border aseel-border-soft dark:aseel-border-soft"
          >
            إلغاء
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit || submitting}
            className="px-4 py-2 text-sm rounded-lg aseel-bg-panel text-white font-medium disabled:opacity-40"
          >
            {submitting ? "جاري الحفظ..." : "حفظ"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SalesCustomerPaymentsPage;
