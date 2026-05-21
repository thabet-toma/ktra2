import React, { useState, useEffect, useCallback, useMemo } from "react";
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
      setShowForm(false);
      setSelectedPayment(null);
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
      <div className="flex flex-wrap items-center gap-3 p-4 bg-gradient-to-l from-emerald-900 to-slate-900 text-white rounded-xl">
        <Banknote className="w-8 h-8 text-emerald-300" />
        <div className="flex-1">
          <h1 className="text-lg font-bold">دفعات العملاء</h1>
          <p className="text-xs text-emerald-200">
            تحصيل من الذمم المدينة مع توزيع FIFO وترحيل محاسبي
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          دفعة جديدة
        </button>
      </div>

      {err && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 text-sm flex gap-2 items-center">
          <AlertCircle className="w-4 h-4" />
          {err}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="rounded-xl border border-emerald-200 dark:border-emerald-900/40 bg-emerald-50/60 dark:bg-emerald-900/10 p-4">
          <div className="text-xs text-emerald-700 dark:text-emerald-300 font-semibold">
            إجمالي مرحّل
          </div>
          <div className="text-2xl font-bold text-emerald-900 dark:text-emerald-200">
            {fmt(totalPosted)}
          </div>
        </div>
        <div className="rounded-xl border border-amber-200 dark:border-amber-900/40 bg-amber-50/60 dark:bg-amber-900/10 p-4">
          <div className="text-xs text-amber-700 dark:text-amber-300 font-semibold">
            بانتظار الترحيل
          </div>
          <div className="text-2xl font-bold text-amber-900 dark:text-amber-200">
            {fmt(totalPending)}
          </div>
        </div>
        <div className="rounded-xl border border-rose-200 dark:border-rose-900/40 bg-rose-50/60 dark:bg-rose-900/10 p-4">
          <div className="text-xs text-rose-700 dark:text-rose-300 font-semibold">
            فواتير مفتوحة (AR)
          </div>
          <div className="text-2xl font-bold text-rose-900 dark:text-rose-200">
            {aging.length}
          </div>
          <div className="text-[11px] text-rose-700/70 mt-1">
            {fmt(aging.reduce((s, a) => s + Number(a.remaining), 0))} متبقي
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="بحث..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pr-9 pl-3 py-2 border rounded-lg dark:bg-gray-900 dark:border-gray-600"
          />
        </div>
      </div>

      {loading ? (
        <div className="py-16 text-center text-gray-500">جاري التحميل…</div>
      ) : (
        <div className="overflow-x-auto bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
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
                  className="border-t border-gray-100 dark:border-gray-700"
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
                        <span className="text-gray-500">بدون توزيع</span>
                      )}
                    </div>
                  </td>
                  <td className="p-2 text-center">
                    {p.is_posted ? (
                      <span className="text-xs px-2 py-1 bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 rounded-full">
                        مرحّلة {p.journal ? `#${p.journal}` : ""}
                      </span>
                    ) : (
                      <span className="text-xs px-2 py-1 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded-full">
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
                          className="p-1.5 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/30 rounded"
                          title="ترحيل"
                        >
                          <Check className="w-4 h-4" />
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => handleDelete(p.id, p.is_posted)}
                        className="p-1.5 text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-900/30 rounded disabled:opacity-40"
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
            <p className="p-8 text-center text-gray-500">لا توجد دفعات</p>
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
// ═══════════════════════════════════════════════════════════════════════════
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
  const [amount, setAmount] = useState("");
  const [currencyId, setCurrencyId] = useState<number | "">("");
  const [exchangeRate, setExchangeRate] = useState("1");
  const [cashAccountId, setCashAccountId] = useState<number | "">("");
  const [notes, setNotes] = useState("");
  const [allocations, setAllocations] = useState<
    Array<{ invoice: number; invoice_number?: string; amount: string }>
  >([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-3xl mt-8">
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-bold">دفعة عميل جديدة</h2>
          <button type="button" onClick={onClose} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">العميل *</label>
              <select
                className="w-full border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
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
              <label className="block text-xs text-gray-500 mb-1">التاريخ *</label>
              <input
                type="date"
                className="w-full border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs text-gray-500 mb-1">المبلغ *</label>
              <input
                type="number"
                step="0.01"
                className="w-full border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs text-gray-500 mb-1">العملة *</label>
              <select
                className="w-full border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
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
              <label className="block text-xs text-gray-500 mb-1">سعر الصرف</label>
              <input
                type="number"
                step="0.000001"
                className="w-full border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                value={exchangeRate}
                onChange={(e) => setExchangeRate(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs text-gray-500 mb-1">الصندوق / البنك *</label>
              <select
                className="w-full border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
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

          <div>
            <label className="block text-xs text-gray-500 mb-1">ملاحظات</label>
            <input
              type="text"
              className="w-full border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          <div className="border-t border-gray-200 dark:border-gray-700 pt-3">
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
              <div className="mb-2 p-2 rounded bg-amber-50 dark:bg-amber-900/20 text-xs text-amber-700">
                {partnerAging.length} فاتورة مفتوحة للعميل — اضغط "اقتراح FIFO" للتوزيع
                التلقائي أو أضف يدوياً.
              </div>
            )}

            {allocations.length === 0 ? (
              <div className="text-xs text-gray-500 text-center py-3 border-2 border-dashed border-gray-200 dark:border-gray-700 rounded">
                لا توزيعات بعد
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-gray-50 dark:bg-gray-900/40">
                  <tr>
                    <th className="text-right p-2">الفاتورة</th>
                    <th className="text-right p-2">المبلغ</th>
                    <th className="w-10"></th>
                  </tr>
                </thead>
                <tbody>
                  {allocations.map((a, idx) => (
                    <tr key={idx} className="border-t border-gray-100 dark:border-gray-700">
                      <td className="p-2">
                        {a.invoice_number || `#${a.invoice}`}
                      </td>
                      <td className="p-2">
                        <input
                          type="number"
                          step="0.01"
                          className="w-full border rounded px-2 py-1 dark:bg-gray-900 dark:border-gray-600"
                          value={a.amount}
                          onChange={(e) => updateAlloc(idx, e.target.value)}
                        />
                      </td>
                      <td className="p-1 text-center">
                        <button
                          type="button"
                          onClick={() => removeAlloc(idx)}
                          className="p-1 text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-900/30 rounded"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-gray-100 dark:bg-gray-900/40 font-semibold text-sm">
                  <tr>
                    <td className="p-2">الإجمالي / المطلوب {fmt(amtNum)}</td>
                    <td
                      className={`p-2 ${
                        Math.abs(diff) < 0.02 ? "text-emerald-700" : "text-rose-700"
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

          {error && (
            <div className="p-2 rounded bg-red-50 dark:bg-red-900/20 text-red-700 text-sm">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 p-4 border-t border-gray-200 dark:border-gray-700">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-600"
          >
            إلغاء
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit || submitting}
            className="px-4 py-2 text-sm rounded-lg bg-emerald-600 text-white font-medium disabled:opacity-40"
          >
            {submitting ? "جاري الحفظ..." : "حفظ"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SalesCustomerPaymentsPage;
