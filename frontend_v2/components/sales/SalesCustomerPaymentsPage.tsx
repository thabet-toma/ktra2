/**
 * SalesCustomerPaymentsPage — «سند قبض» (دفعات العملاء).
 *
 * التصميم موحَّد مع {@link SupplierPaymentsPage} (قرار المالك 2026-07-25): نفس
 * الهيكل — AseelDocumentShell + شريط أدوات + AseelDenseTable + شريط حالة —
 * والنافذة تُبنى من نفس قطع {@link PaymentVoucherParts} المشتركة مع سند الصرف.
 *
 * T-ONACC: التوزيع على الفواتير **اختياري**. سند بلا توزيع (أو بتوزيع جزئي)
 * يُرحَّل ويظهر في كشف حساب العميل (Dr صندوق / Cr ذمم) دون تسديد أي فاتورة،
 * ويُوزَّع لاحقاً عبر «توزيع» — ربط فقط بلا قيد جديد.
 */
import React, { useState, useEffect, useCallback, useMemo } from "react";
import { formatMoney, formatNumber } from "../../utils/formatNumber";
import { useNavigate } from "react-router-dom";
import {
  Banknote,
  Plus,
  Trash2,
  Check,
  Split,
  Sparkles,
  X,
  Printer,
  RefreshCw,
} from "lucide-react";
import {
  listCustomerPayments,
  createCustomerPayment,
  postCustomerPayment,
  deleteCustomerPayment,
  allocateCustomerPayment,
  suggestFifoAllocations,
  getAgingReport,
  getSalesSettings,
  type CustomerPaymentRow,
} from "../../services/salesApi";
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";
import { accountingApi } from "../../services/accountingApi";
import { apiGetObject } from "../../services/restApi";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import {
  AseelDocumentShell,
  AseelDenseTable,
  useRecordNavigation,
  useAseelKeymap,
  type DenseColumn,
  type AseelToolbarAction,
  type AseelTab,
} from "../aseel";
import {
  ChequeGrid,
  PaymentFinanceFields,
  PaymentVoucherModal,
  type ChequeLine,
} from "./PaymentVoucherParts";
import { VoucherAllocationModal } from "../shared/VoucherAllocationModal";
import { PartnerNoteAlert } from "../partners/PartnerNoteAlert";
import { formatDateLocalized } from "../../utils/formatDate";
import {
  buildPartnerChequeDefaults,
  type PartnerBankAccount,
} from "../../utils/partnerChequeDefaults";

type Partner = { id: number; name: string; legal_name?: string | null };
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

const fmt = (n: string | number) => formatMoney(n);

/** المتبقّي غير الموزَّع على الفواتير (يأتي محسوباً من الخادم، ويُشتق احتياطاً). */
const unallocatedOf = (p: CustomerPaymentRow) =>
  p.unallocated_amount != null
    ? Number(p.unallocated_amount)
    : Number(p.amount) - (p.allocations || []).reduce((s, a) => s + Number(a.amount || 0), 0);

export const SalesCustomerPaymentsPage: React.FC = () => {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const toast = useToast();
  const [payments, setPayments] = useState<CustomerPaymentRow[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [aging, setAging] = useState<AgingInvoice[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  // T-P2: عميل مُسبق التعبئة عند الوصول من كشف الحساب (?pay_partner=ID).
  const [prefillPartnerId, setPrefillPartnerId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [defaultCashAccountId, setDefaultCashAccountId] = useState<number | "">("");
  // T-AUTOPOST: إعداد الشركة «ترحيل السندات تلقائياً عند الحفظ».
  const [autoPostPayments, setAutoPostPayments] = useState(true);
  // T-ONACC: السند المُراد توزيعه على الفواتير (بعد الترحيل أو قبله).
  const [allocatingPayment, setAllocatingPayment] = useState<CustomerPaymentRow | null>(null);

  useEffect(() => {
    const pid = new URLSearchParams(window.location.search).get("pay_partner");
    if (pid && Number(pid)) {
      setPrefillPartnerId(Number(pid));
      setShowForm(true);
    }
  }, []);

  // M4-T3: Aseel Navigation for customer payments
  const [selectedPayment, setSelectedPayment] = useState<CustomerPaymentRow | null>(null);

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

  const loadAll = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [pays, parts, accs, currs, ag, pSettings, sSettings] = await Promise.all([
        listCustomerPayments(),
        accountingApi.getPartners() as Promise<Partner[]>,
        accountingApi.getAccounts() as Promise<Account[]>,
        accountingApi.getCurrencies() as Promise<Currency[]>,
        getAgingReport(),
        purchaseInvoiceApi.getSettings().catch(() => null),
        getSalesSettings().catch(() => null),
      ]);
      setPayments(pays || []);
      setPartners(parts || []);
      setAccounts(accs || []);
      setCurrencies(currs || []);
      setAging(ag || []);
      const paymentId = Number(new URLSearchParams(window.location.search).get("payment_id"));
      if (paymentId) {
        setSearch(String(paymentId));
        setSelectedPayment((pays || []).find((payment) => payment.id === paymentId) || null);
      }
      // T-A4: Set default cash account (prefer sales settings, fallback to purchase settings)
      const defCash = sSettings?.default_cash_account || pSettings?.default_cash_account;
      if (defCash) {
        setDefaultCashAccountId(defCash);
      }
      if (sSettings) setAutoPostPayments(!!sSettings.auto_post_payments);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // M4-T3: Aseel keyboard shortcuts — real handlers.
  useAseelKeymap({
    F2: () => window.print(),
    F5: () => loadAll(),
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-aseel-field="search"]');
      el?.focus();
    },
    Escape: () => {
      if (showForm || allocatingPayment || selectedPayment) {
        setShowForm(false);
        setAllocatingPayment(null);
        setSelectedPayment(null);
      } else {
        navigate(-1);
      }
    },
    // N0-T11: Ctrl+nav handlers
    CtrlHome: () => nav?.first?.(),
    CtrlEnd: () => nav?.last?.(),
    CtrlPageUp: () => nav?.prev?.(),
    CtrlPageDown: () => nav?.next?.(),
    CtrlIns: () => { setSelectedPayment(null); setShowForm(true); },
  });

  const partnerName = (id: number) =>
    partners.find((p) => p.id === id)?.name || `#${id}`;

  const accountName = (id: number) => {
    const a = accounts.find((x) => x.id === id);
    return a ? `${a.code} ${a.name}` : `#${id}`;
  };

  const handlePost = async (p: CustomerPaymentRow) => {
    const unalloc = unallocatedOf(p);
    const ok = await confirm({
      title: "ترحيل السند",
      message:
        unalloc > 0.009
          ? `ترحيل السند سينشئ قيداً محاسبياً. المبلغ غير الموزَّع (${fmt(unalloc)}) `
            + "سيُسجَّل على حساب العميل (رصيد لصالحه) ويمكن توزيعه على الفواتير لاحقاً. متابعة؟"
          : "ترحيل السند سينشئ قيداً محاسبياً ويسدّد الفواتير الموزَّعة. متابعة؟",
      confirmText: "ترحيل",
      danger: false,
    });
    if (!ok) return;
    try {
      await postCustomerPayment(p.id);
      toast("تم ترحيل السند", "success");
      await loadAll();
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : "فشل الترحيل", "error");
    }
  };

  const handleDelete = async (p: CustomerPaymentRow) => {
    if (p.is_posted) {
      toast("لا يمكن حذف سند مرحّل. ألغِ الترحيل أولاً.", "error");
      return;
    }
    if (!(await confirm({ message: `حذف السند #${p.id}؟` }))) return;
    try {
      await deleteCustomerPayment(p.id);
      setPayments((ps) => ps.filter((x) => x.id !== p.id));
      toast("تم حذف السند", "success");
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : "فشل الحذف", "error");
    }
  };

  const filtered = useMemo(() => {
    if (!search.trim()) return payments;
    const s = search.toLowerCase();
    return payments.filter(
      (p) =>
        (p.partner_name || partnerName(p.partner)).toLowerCase().includes(s) ||
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
  const totalUnallocated = payments.reduce((s, p) => s + Math.max(0, unallocatedOf(p)), 0);

  const columns: DenseColumn<CustomerPaymentRow>[] = [
    { key: "id", header: "#", width: "60px", align: "center", render: (r) => <span className="font-mono text-xs">#{r.id}</span> },
    { key: "payment_date", header: "التاريخ", width: "110px", align: "center", render: (r) => <span className="text-xs">{formatDateLocalized(r.payment_date)}</span> },
    {
      key: "customer", header: "العميل",
      render: (r) => (
        <span
          className="text-xs"
          data-ctx-partner-id={r.partner ?? undefined}
          data-ctx-partner-name={r.partner_name || partnerName(r.partner)}
          data-ctx-partner-kind="customer"
        >
          {r.partner_name || partnerName(r.partner)}
        </span>
      ),
    },
    { key: "amount", header: "المبلغ", width: "120px", align: "left", numeric: true, render: (r) => <span className="aseel-num font-mono text-xs font-semibold">{fmt(r.amount)}</span> },
    {
      key: "unallocated", header: "على الحساب", width: "110px", align: "left", numeric: true,
      render: (r) => {
        const u = unallocatedOf(r);
        return (
          <span
            className="aseel-num font-mono text-xs"
            style={{ color: u > 0.009 ? "var(--aseel-warn, #b06800)" : "var(--aseel-ink-soft)" }}
          >
            {fmt(u)}
          </span>
        );
      },
    },
    { key: "cash_account", header: "الصندوق", render: (r) => <span className="text-xs">{accountName(r.cash_or_bank_account)}</span> },
    {
      key: "allocations", header: "التوزيعات",
      render: (r) => (
        <span className="text-[11px]">
          {r.allocations && r.allocations.length > 0
            ? r.allocations.map((a) => `#${a.invoice} = ${fmt(a.amount)}`).join(" · ")
            : <span style={{ color: "var(--aseel-ink-soft)" }}>بدون توزيع</span>}
        </span>
      ),
    },
    {
      key: "status", header: "الحالة", width: "100px", align: "center",
      render: (r) => (
        <span
          style={{
            fontSize: "11px",
            fontWeight: 600,
            color: r.is_posted ? "var(--aseel-ok, #2d7d46)" : "var(--aseel-warn, #b06800)",
          }}
        >
          {r.is_posted ? `مرحَّل ${r.journal ? "#" + r.journal : ""}` : "مسودة"}
        </span>
      ),
    },
    {
      key: "actions", header: "إجراءات", width: "110px", align: "center",
      render: (r) => (
        <div style={{ display: "flex", gap: "2px", justifyContent: "center" }} onClick={(e) => e.stopPropagation()}>
          {!r.is_posted && (
            <button type="button" className="aseel-toolbtn" title="ترحيل" onClick={() => void handlePost(r)}>
              <Check className="w-3 h-3" />
            </button>
          )}
          <button
            type="button"
            className="aseel-toolbtn"
            title="توزيع على الفواتير"
            disabled={unallocatedOf(r) <= 0.009}
            onClick={() => setAllocatingPayment(r)}
          >
            <Split className="w-3 h-3" />
          </button>
          <button
            type="button"
            className="aseel-toolbtn"
            title="حذف"
            disabled={r.is_posted}
            onClick={() => void handleDelete(r)}
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      ),
    },
  ];

  const actions: AseelToolbarAction[] = [
    { key: "new", label: "سند قبض جديد (Ctrl+Ins)", icon: <Plus />, onClick: () => { setSelectedPayment(null); setShowForm(true); } },
    { key: "refresh", label: "تحديث", icon: <RefreshCw className={loading ? "animate-spin" : ""} />, onClick: () => void loadAll(), separatorBefore: true },
    { key: "print", label: "طباعة", icon: <Printer />, onClick: () => window.print() },
    {
      key: "cancel",
      label: "إلغاء",
      icon: <X />,
      onClick: () => {
        if (showForm || allocatingPayment || selectedPayment) {
          setShowForm(false);
          setAllocatingPayment(null);
          setSelectedPayment(null);
        } else {
          navigate(-1);
        }
      },
      danger: true,
      separatorBefore: true,
    },
  ];

  const tabs: AseelTab[] = [
    {
      key: "list",
      label: "سندات القبض",
      content: (
        <div style={{ padding: "8px" }}>
          {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}

          <AseelDenseTable<CustomerPaymentRow>
            columns={columns}
            rows={filtered}
            getRowKey={(r) => r.id}
            loading={loading}
            selectable
            selectedKey={selectedPayment?.id ?? null}
            onSelect={(key) => setSelectedPayment(filtered.find((p) => p.id === key) || null)}
            emptyHint="لا سندات قبض — اضغط Ctrl+Ins للإضافة"
          />
        </div>
      ),
    },
  ];

  return (
    <div style={{ minHeight: "calc(100vh - 5rem)" }}>
      <AseelDocumentShell
        title="سندات القبض من العملاء"
        state={selectedPayment ? `سند #${selectedPayment.id}` : `${filtered.length} سند`}
        nav={nav}
        actions={actions}
        header={
          <label className="aseel-field" style={{ flex: 1, minWidth: "200px" }}>
            <span className="aseel-field-label">بحث (عميل / رقم / ملاحظة)</span>
            <input
              className="aseel-input"
              data-aseel-field="search"
              placeholder="بحث... (F6)"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        }
        tabs={tabs}
        status={
          <>
            <span className="aseel-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
            <span className="aseel-status-item"><Banknote className="w-3 h-3 inline" /> {filtered.length} سند</span>
            <span className="aseel-status-item">مرحَّل <b className="aseel-num">{fmt(totalPosted)}</b></span>
            <span className="aseel-status-item" style={{ color: "var(--aseel-warn, #b06800)" }}>
              مسودة <b className="aseel-num">{fmt(totalPending)}</b>
            </span>
            <span className="aseel-status-item" style={{ color: "var(--aseel-warn, #b06800)" }}>
              على الحساب <b className="aseel-num">{fmt(totalUnallocated)}</b>
            </span>
            <span className="aseel-status-item">
              فواتير مفتوحة {aging.length} · متبقٍ{" "}
              <b className="aseel-num">{fmt(aging.reduce((s, a) => s + Number(a.remaining), 0))}</b>
            </span>
          </>
        }
      />

      {showForm && (
        <NewPaymentModal
          partners={partners}
          accounts={accounts}
          currencies={currencies}
          aging={aging}
          initialPartnerId={prefillPartnerId}
          defaultCashAccountId={defaultCashAccountId}
          autoPostPayments={autoPostPayments}
          onClose={() => { setShowForm(false); setPrefillPartnerId(null); }}
          onSaved={async () => {
            setShowForm(false);
            setPrefillPartnerId(null);
            toast(autoPostPayments ? "تم حفظ السند وترحيله" : "تم حفظ السند", "success");
            await loadAll();
          }}
        />
      )}

      {allocatingPayment && (
        <PaymentAllocationModal
          payment={allocatingPayment}
          partnerLabel={allocatingPayment.partner_name || partnerName(allocatingPayment.partner)}
          aging={aging.filter((a) => a.customer_id === allocatingPayment.partner)}
          onClose={() => setAllocatingPayment(null)}
          onSaved={async () => {
            setAllocatingPayment(null);
            toast("تم توزيع السند على الفواتير", "success");
            await loadAll();
          }}
        />
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// Modal إنشاء سند قبض — نفس هيكل «سند صرف» عبر PaymentVoucherParts
// N4-T4: حقول خصم المصدر (withholding) + شبكة شيكات + توزيع على الفواتير
// ═══════════════════════════════════════════════════════════════════════════
export const NewPaymentModal: React.FC<{
  partners?: Partner[];
  accounts?: Account[];
  currencies?: Currency[];
  aging?: AgingInvoice[];
  onClose: () => void;
  onSaved: () => void;
  /** T-P2: عميل مُسبق التعبئة عند الفتح من كشف الحساب. */
  initialPartnerId?: number | null;
  initialPartner?: Partner | null;
  lockPartner?: boolean;
  defaultCashAccountId?: number | "";
  /** T-AUTOPOST: إعداد الشركة «ترحيل السندات تلقائياً» (يحدّد الزر الأساسي). */
  autoPostPayments?: boolean;
  /** T-ONEPAY: فاتورة مُسبقة التوزيع عند الفتح من داخلها (المبلغ = متبقّيها). */
  initialInvoice?: { id: number; number?: string; remaining: number } | null;
}> = ({
  partners: providedPartners,
  accounts: providedAccounts,
  currencies: providedCurrencies,
  aging: providedAging,
  onClose,
  onSaved,
  initialPartnerId,
  initialPartner,
  lockPartner = false,
  defaultCashAccountId,
  autoPostPayments,
  initialInvoice,
}) => {
  const today = new Date().toISOString().split("T")[0];
  const [loadedPartners, setLoadedPartners] = useState<Partner[]>(initialPartner ? [initialPartner] : []);
  const [loadedAccounts, setLoadedAccounts] = useState<Account[]>([]);
  const [loadedCurrencies, setLoadedCurrencies] = useState<Currency[]>([]);
  const [loadedAging, setLoadedAging] = useState<AgingInvoice[]>([]);
  const [loadedDefaultCashAccountId, setLoadedDefaultCashAccountId] = useState<number | "">("");
  // T-AUTOPOST: يُحمَّل ذاتياً حين تُفتح النافذة من بطاقة الشريك (بلا props من الصفحة).
  const [loadedAutoPost, setLoadedAutoPost] = useState<boolean | null>(null);
  const effectiveAutoPost = autoPostPayments ?? loadedAutoPost ?? true;
  const partners = providedPartners ?? loadedPartners;
  const accounts = providedAccounts ?? loadedAccounts;
  const currencies = providedCurrencies ?? loadedCurrencies;
  const aging = providedAging ?? loadedAging;
  const effectiveDefaultCashAccountId = defaultCashAccountId || loadedDefaultCashAccountId;
  const [partnerId, setPartnerId] = useState<number | "">(initialPartnerId ?? initialPartner?.id ?? "");
  const [date, setDate] = useState(today);
  const [cashAmount, setCashAmount] = useState(
    initialInvoice ? String(initialInvoice.remaining) : "",
  ); // N4-T4: نقد جزء
  const [currencyId, setCurrencyId] = useState<number | "">("");
  const [exchangeRate, setExchangeRate] = useState("1");
  const [cashAccountId, setCashAccountId] = useState<number | "">(effectiveDefaultCashAccountId);
  const [notes, setNotes] = useState("");
  // N4-T4: withholding (خصم المصدر) — يُحسَب من المجموع
  const [withholdingPct, setWithholdingPct] = useState("0");
  const [withholdingAmt, setWithholdingAmt] = useState("0");
  // N4-T4: cheques inside payment (تفاصيل السند)
  const [cheques, setCheques] = useState<ChequeLine[]>([]);
  const [chequeDefaults, setChequeDefaults] = useState<Partial<ChequeLine>>({});
  const [allocations, setAllocations] = useState<
    Array<{ invoice: number; invoice_number?: string; amount: string }>
  >(
    initialInvoice
      ? [{
          invoice: initialInvoice.id,
          invoice_number: initialInvoice.number,
          amount: String(initialInvoice.remaining),
        }]
      : [],
  );
  // T-P1: الفاتورة المحددة لتسوية الدفعة عليها (بديل لتوزيع FIFO).
  const [pickInvoiceId, setPickInvoiceId] = useState<number | "">("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (
      providedPartners !== undefined &&
      providedAccounts !== undefined &&
      providedCurrencies !== undefined &&
      providedAging !== undefined
    ) return;

    let cancelled = false;
    Promise.all([
      providedPartners !== undefined
        ? Promise.resolve(providedPartners)
        : lockPartner && initialPartner
          ? Promise.resolve([initialPartner])
          : accountingApi.getPartners() as Promise<Partner[]>,
      providedAccounts !== undefined
        ? Promise.resolve(providedAccounts)
        : accountingApi.getAccounts() as Promise<Account[]>,
      providedCurrencies !== undefined
        ? Promise.resolve(providedCurrencies)
        : accountingApi.getCurrencies() as Promise<Currency[]>,
      providedAging !== undefined
        ? Promise.resolve(providedAging)
        : getAgingReport(),
      defaultCashAccountId
        ? Promise.resolve(null)
        : purchaseInvoiceApi.getSettings().catch(() => null),
      defaultCashAccountId
        ? Promise.resolve(null)
        : getSalesSettings().catch(() => null),
    ])
      .then(([parts, accs, currs, agingRows, purchaseSettings, salesSettings]) => {
        if (cancelled) return;
        setLoadedPartners(parts || []);
        setLoadedAccounts(accs || []);
        setLoadedCurrencies(currs || []);
        setLoadedAging(agingRows || []);
        const defaultAccount =
          salesSettings?.default_cash_account || purchaseSettings?.default_cash_account;
        if (defaultAccount) setLoadedDefaultCashAccountId(defaultAccount);
        if (salesSettings) setLoadedAutoPost(!!salesSettings.auto_post_payments);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "فشل تحميل إعدادات السند");
      });

    return () => { cancelled = true; };
  }, [
    providedPartners,
    providedAccounts,
    providedCurrencies,
    providedAging,
    lockPartner,
    initialPartner,
    defaultCashAccountId,
  ]);

  // تحديث الصندوق الافتراضي في حال تم تحميله بعد فتح النافذة (مثال: فتح من رابط)
  useEffect(() => {
    if (effectiveDefaultCashAccountId && cashAccountId === "") {
      setCashAccountId(effectiveDefaultCashAccountId);
    }
  }, [effectiveDefaultCashAccountId, cashAccountId]);

  // المبلغ = نقد + شيكات (كما في سند الصرف)
  const totalCheques = cheques.reduce((s, c) => s + (Number(c.amount) || 0), 0);
  const amtNum = (Number(cashAmount) || 0) + totalCheques;

  // N4-T4: تَحديث withholdingAmt من النسبة
  useEffect(() => {
    const pct = Number(withholdingPct) || 0;
    setWithholdingAmt(formatNumber(amtNum * (pct / 100), { maxDecimals: 2 }));
  }, [withholdingPct, amtNum]);

  useEffect(() => {
    // default currency = ILS if exists
    if (currencies.length && !currencyId) {
      const ils = currencies.find((c) => c.Code === "ILS");
      setCurrencyId((ils?.CurrencyID ?? currencies[0].CurrencyID) as number);
    }
  }, [currencies, currencyId]);

  useEffect(() => {
    const partner = partners.find((p) => p.id === partnerId) || initialPartner || null;
    if (!partnerId || !partner) {
      setChequeDefaults({});
      return;
    }
    let cancelled = false;
    setChequeDefaults(buildPartnerChequeDefaults(partner, null, "Incoming"));
    const currencyQuery = currencyId ? `&currency=${currencyId}` : "";
    apiGetObject<{
      selected_bank_account: PartnerBankAccount | null;
    }>(
      `partners/${partnerId}/payment-defaults/?direction=Incoming${currencyQuery}`,
    )
      .then((defaults) => {
        if (!cancelled) {
          setChequeDefaults(
            buildPartnerChequeDefaults(
              partner, defaults.selected_bank_account, "Incoming",
            ),
          );
        }
      })
      .catch(() => {
        if (!cancelled) {
          setChequeDefaults(buildPartnerChequeDefaults(partner, null, "Incoming"));
        }
      });
    return () => { cancelled = true; };
  }, [currencyId, initialPartner, partnerId, partners]);

  const cashboxAccounts = useMemo(
    () =>
      accounts.filter((a) => {
        // T-A4: Ensure consistent filtering with PurchaseSettings / SalesSettings
        if (a.account_type === undefined) return false;
        const t = (a.account_type || "").toLowerCase();
        if (t === "cash" || t === "bank") return true;
        if (t === "asset") {
          const code = String(a.code || "");
          const name = (a.name || "").toLowerCase();
          return (
            code.startsWith("110") ||
            name.includes("صندوق") ||
            name.includes("بنك") ||
            name.includes("cash") ||
            name.includes("bank")
          );
        }
        return false;
      }),
    [accounts],
  );

  const partnerAging = useMemo(
    () => aging.filter((a) => a.customer_id === partnerId),
    [aging, partnerId],
  );

  const totalAlloc = allocations.reduce((s, a) => s + Number(a.amount || 0), 0);
  // T-ONACC: الفرق ليس خطأً — هو ما سيُسجَّل على حساب العميل.
  const onAccount = amtNum - totalAlloc;
  const canSubmit =
    !!partnerId &&
    amtNum > 0 &&
    !!cashAccountId &&
    !!currencyId &&
    totalAlloc <= amtNum + 0.01;

  const suggestFifo = async () => {
    if (!partnerId || amtNum <= 0) {
      setError("اختر العميل وأدخل المبلغ أولاً");
      return;
    }
    try {
      const rows = await suggestFifoAllocations({
        partner: partnerId as number,
        amount: String(amtNum),
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

  // T-P1: تسوية الدفعة على فاتورة محددة يختارها المستخدم (بدل FIFO). تُضاف كسطر
  // توزيع بمبلغ افتراضي = الأقل بين المتبقي من الدفعة ومتبقي الفاتورة.
  const addInvoiceAllocation = () => {
    const inv = partnerAging.find((a) => a.invoice_id === Number(pickInvoiceId));
    if (!inv) return;
    if (allocations.some((a) => a.invoice === inv.invoice_id)) {
      setError("الفاتورة مضافة مسبقاً في التوزيع");
      return;
    }
    const remainingPayment = Math.max(0, amtNum - totalAlloc);
    const invRemaining = Number(inv.remaining) || 0;
    const amt = remainingPayment > 0 ? Math.min(remainingPayment, invRemaining) : invRemaining;
    setAllocations((as) => [
      ...as,
      { invoice: inv.invoice_id, invoice_number: inv.invoice_number, amount: String(amt.toFixed(2)) },
    ]);
    setPickInvoiceId("");
    setError(null);
  };

  const updateAlloc = (idx: number, amt: string) => {
    setAllocations((as) => as.map((a, i) => (i === idx ? { ...a, amount: amt } : a)));
  };

  const removeAlloc = (idx: number) => {
    setAllocations((as) => as.filter((_, i) => i !== idx));
  };

  // T-AUTOPOST: الحفظ يُرحّل مباشرةً حسب إعداد الشركة، والزر الثانوي هو البديل الصريح.
  const submit = async (autoPost: boolean) => {
    setError(null);
    if (!canSubmit) {
      setError(
        totalAlloc > amtNum + 0.01
          ? "مجموع التوزيعات يتجاوز مبلغ السند"
          : "أكمل الحقول المطلوبة (العميل + الصندوق + مبلغ > 0)",
      );
      return;
    }
    setSubmitting(true);
    try {
      const saved = await createCustomerPayment({
        partner: partnerId as number,
        payment_date: date,
        amount: amtNum.toFixed(2),
        currency: currencyId as number,
        exchange_rate: exchangeRate,
        cash_or_bank_account: cashAccountId as number,
        notes,
        auto_post: autoPost,
        // T-ONEPAY: الشيكات جزء من مبلغ السند — تُرسَل ليُقيَّد جزؤها على
        // «شيكات برسم التحصيل» لا على الصندوق، وتُنشأ شيكات حقيقية.
        ...(cheques.length > 0
          ? {
              cheques: cheques.map((c) => ({
                cheque_number: c.cheque_number,
                amount: c.amount,
                bank_name: c.bank_name || "",
                account_number: c.account_number || "",
                bank_branch: c.branch || "",
                payee_name: c.payee_name || "",
                due_date: c.due_date || null,
                issue_date: c.issue_date || null,
              })),
            }
          : {}),
        ...(allocations.length > 0
          ? {
              allocations: allocations.map((a) => ({
                invoice: a.invoice,
                amount: a.amount,
              })),
            }
          : {}),
      });
      // فشل الترحيل التلقائي لا يُضيع السند — يبقى مسودة ونُظهر السبب.
      if (saved?.auto_post_error) {
        setError(`حُفظ السند كمسودة — تعذّر الترحيل: ${saved.auto_post_error}`);
        setSubmitting(false);
        return;
      }
      onSaved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "فشل الإنشاء");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <PaymentVoucherModal
      title="سند قبض جديد"
      error={error}
      submitting={submitting}
      disabled={!canSubmit}
      submitLabel={effectiveAutoPost ? "حفظ وترحيل" : "حفظ"}
      secondaryLabel={effectiveAutoPost ? "حفظ كمسودة" : "حفظ وترحيل"}
      onSecondary={() => void submit(!effectiveAutoPost)}
      onClose={onClose}
      onSubmit={() => void submit(effectiveAutoPost)}
    >
      {/* ملاحظة عاجلة مستحقة على هذا العميل — تظهر قبل إتمام السند. */}
      <PartnerNoteAlert partnerId={partnerId === "" ? null : partnerId} className="mb-2" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px" }}>
        <label className="aseel-field" style={{ gridColumn: "span 2" }}>
          <span className="aseel-field-label">العميل *</span>
          {lockPartner && initialPartner ? (
            <input className="aseel-input" value={initialPartner.name} readOnly style={{ background: "var(--aseel-surface-2)" }} />
          ) : (
            <select
              className="aseel-input"
              value={partnerId}
              onChange={(e) => {
                setPartnerId(e.target.value ? Number(e.target.value) : "");
                setAllocations([]);
              }}
            >
              <option value="">— اختر —</option>
              {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          )}
        </label>
        <label className="aseel-field">
          <span className="aseel-field-label">التاريخ</span>
          <input type="date" className="aseel-input" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>

        <label className="aseel-field">
          <span className="aseel-field-label">الصندوق / البنك *</span>
          <select className="aseel-input" value={cashAccountId} onChange={(e) => setCashAccountId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">— اختر —</option>
            {cashboxAccounts.map((a) => <option key={a.id} value={a.id}>{a.code} {a.name}</option>)}
          </select>
        </label>
        <label className="aseel-field">
          <span className="aseel-field-label">العملة *</span>
          <select className="aseel-input" value={currencyId} onChange={(e) => setCurrencyId(e.target.value ? Number(e.target.value) : "")}>
            {currencies.map((c) => (
              <option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}{c.Name ? ` — ${c.Name}` : ""}</option>
            ))}
          </select>
        </label>
        <label className="aseel-field">
          <span className="aseel-field-label">سعر الصرف</span>
          <input type="number" step="0.000001" className="aseel-input aseel-num" value={exchangeRate} onChange={(e) => setExchangeRate(e.target.value)} />
        </label>
      </div>

      <PaymentFinanceFields
        cashAmount={cashAmount}
        onCashAmount={setCashAmount}
        totalCheques={totalCheques}
        total={amtNum}
        withholdingPct={withholdingPct}
        onWithholdingPct={setWithholdingPct}
        withholdingAmt={withholdingAmt}
        onWithholdingAmt={setWithholdingAmt}
        netLabel="مبلغ الحساب"
      />

      {/* التوزيع على الفواتير — اختياري (T-ONACC) */}
      <div style={{ marginTop: "12px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
          <span style={{ fontWeight: 600, fontSize: "12px" }}>توزيع على الفواتير (اختياري)</span>
          <button
            type="button"
            className="aseel-toolbtn"
            style={{ fontSize: "11px" }}
            onClick={() => void suggestFifo()}
            disabled={!partnerId || amtNum <= 0}
          >
            <Sparkles className="w-3 h-3" /> اقتراح FIFO
          </button>
        </div>

        {partnerId && partnerAging.length > 0 && (
          <div style={{ display: "flex", gap: "6px", marginBottom: "6px" }}>
            <select
              className="aseel-input"
              style={{ flex: 1, fontSize: "11px" }}
              value={pickInvoiceId}
              onChange={(e) => setPickInvoiceId(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">— اختر فاتورة محددة لتسويتها —</option>
              {partnerAging.map((a) => (
                <option key={a.invoice_id} value={a.invoice_id}>
                  {a.invoice_number || `#${a.invoice_id}`} — متبقٍ {fmt(a.remaining)}
                </option>
              ))}
            </select>
            <button type="button" className="aseel-toolbtn" style={{ fontSize: "11px" }} onClick={addInvoiceAllocation} disabled={!pickInvoiceId}>
              أضف الفاتورة
            </button>
          </div>
        )}

        {allocations.length === 0 ? (
          <div style={{ textAlign: "center", fontSize: "11px", padding: "12px", color: "var(--aseel-ink-soft)", border: "1px dashed var(--aseel-border)", borderRadius: "4px" }}>
            بلا توزيع — كامل المبلغ يُسجَّل على حساب العميل ويمكن توزيعه لاحقاً
          </div>
        ) : (
          <table style={{ width: "100%", fontSize: "11px" }}>
            <thead style={{ background: "var(--aseel-surface-2, #f4ede0)" }}>
              <tr>
                <th style={{ padding: "4px", textAlign: "right" }}>الفاتورة</th>
                <th style={{ padding: "4px", textAlign: "right" }}>المبلغ</th>
                <th style={{ width: "30px" }}></th>
              </tr>
            </thead>
            <tbody>
              {allocations.map((a, idx) => (
                <tr key={idx} style={{ borderTop: "1px solid var(--aseel-border)" }}>
                  <td style={{ padding: "2px" }}>{a.invoice_number || `#${a.invoice}`}</td>
                  <td style={{ padding: "2px" }}>
                    <input type="number" step="0.01" className="aseel-input aseel-num" style={{ fontSize: "11px" }} value={a.amount} onChange={(e) => updateAlloc(idx, e.target.value)} />
                  </td>
                  <td style={{ padding: "2px", textAlign: "center" }}>
                    <button type="button" onClick={() => removeAlloc(idx)} style={{ color: "var(--aseel-err, #c0392b)" }}>
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot style={{ background: "var(--aseel-surface-2, #f4ede0)", fontWeight: 600 }}>
              <tr>
                <td style={{ padding: "4px" }}>المُوزَّع من {fmt(amtNum)}</td>
                <td style={{ padding: "4px" }} className="aseel-num">{fmt(totalAlloc)}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        )}

        {amtNum > 0 && (
          <div style={{ fontSize: "11px", marginTop: "6px", color: onAccount < -0.01 ? "var(--aseel-err, #c0392b)" : "var(--aseel-warn, #b06800)" }}>
            {onAccount < -0.01
              ? `التوزيع يتجاوز مبلغ السند بـ ${fmt(Math.abs(onAccount))}`
              : `يُسجَّل على حساب العميل: ${fmt(onAccount)}`}
          </div>
        )}
      </div>

      <ChequeGrid
        cheques={cheques}
        onChange={setCheques}
        onError={setError}
        newLineDefaults={chequeDefaults}
      />

      <label className="aseel-field" style={{ marginTop: "12px", display: "block" }}>
        <span className="aseel-field-label">ملاحظات</span>
        <textarea className="aseel-input" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>

      <div style={{ fontSize: "11px", marginTop: "8px", color: "var(--aseel-ink-soft)" }}>
        القيد: Dr {(() => {
          const a = accounts.find((x) => x.id === cashAccountId);
          return a ? `${a.code} ${a.name}` : "—";
        })()} / Cr ذمم العميل {(partners.find((p) => p.id === partnerId)?.name) || initialPartner?.name || "—"}
      </div>
    </PaymentVoucherModal>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// T-ONACC — توزيع سند قبض قائم على الفواتير (بعد الترحيل أو قبله)
// غلاف رقيق حول VoucherAllocationModal المشترك مع سند الصرف (تصميم واحد).
// ═══════════════════════════════════════════════════════════════════════════
export const PaymentAllocationModal: React.FC<{
  payment: CustomerPaymentRow;
  partnerLabel: string;
  aging: AgingInvoice[];
  onClose: () => void;
  onSaved: () => void;
}> = ({ payment, partnerLabel, aging, onClose, onSaved }) => (
  <VoucherAllocationModal
    kind="customer"
    voucher={{
      id: payment.id,
      amount: payment.amount,
      unallocated: unallocatedOf(payment),
      is_posted: payment.is_posted,
    }}
    partnerLabel={partnerLabel}
    docs={aging.map((a) => ({
      id: a.invoice_id,
      label: a.invoice_number || `#${a.invoice_id}`,
      remaining: a.remaining,
    }))}
    onClose={onClose}
    onSaved={onSaved}
  />
);

export default SalesCustomerPaymentsPage;
