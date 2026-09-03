/**
 * issue #80 — سند إيراد: مرآةُ شاشة سند المصروف بعكس الاتجاه.
 *
 * الخادم بناها كاملةً منذ #80 (`RevenueVoucherViewSet` + `create_revenue_voucher`
 * + `unpost_revenue_voucher`) وبقيت **بلا مستدعٍ واحد في الواجهة**: كان سند
 * الإيراد يُكتب من شاشة الترميز الدفعي وحدها ثم لا يظهر في أي قائمة — فمن
 * سجّل إيراداً لم يجد ما سجّله، ولا طريقاً للتراجع عنه إلا بحذف قيده من دفتر
 * اليومية يدوياً.
 *
 * الشاشة مرآةٌ متعمَّدة لـ`ExpenseVouchersPage`: نفس الأعمدة ونفس النموذج ونفس
 * معاينة القيد — من عرف أختها لا يتعلّم هذه من جديد.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { accountingApi } from "../../services/accountingApi";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { usePermissions } from "../../contexts/PermissionsContext";
import { useSimpleUi } from "../../hooks/useSimpleUi";
import { useTenantSettings } from "../../hooks/useTenantSettings";
import { humanizeThrown } from "../../utils/drfError";
import { formatMoney } from "../../utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";
import { AccountTreeField } from "./AccountTreePicker";
import { PaymentVoucherModal } from "../sales/PaymentVoucherParts";
import {
  buildRevenueVoucherEntryPreview,
  REVENUE_PAYMENT_METHODS,
  revenueVoucherRequiresCashAccount,
  type RevenuePaymentMethod,
} from "../../utils/revenueVoucherEntryPreview";
import { voucherAccountEntryIsLinked } from "../../utils/voucherAccountEntryMode";
import { KitDocumentShell, KitDenseTable } from "../kit";
import type { KitToolbarAction, DenseColumn } from "../kit";
import { Plus, RotateCcw } from "lucide-react";
import type { AccountingPartner, RevenueVoucherDto } from "../../types/accounting";

type AccountRow = {
  id: number; code: string | null; name: string | null; parent: number | null; account_type?: string | null;
};
type CurrencyRow = { CurrencyID: number; Code: string };

const PAYMENT_METHOD_LABEL: Record<RevenuePaymentMethod, string> =
  Object.fromEntries(REVENUE_PAYMENT_METHODS.map((m) => [m.value, m.label])) as Record<RevenuePaymentMethod, string>;

const today = () => new Date().toISOString().slice(0, 10);

export const RevenueVouchersPage: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const { can } = usePermissions();
  const { show: showAdv } = useSimpleUi();

  const [rows, setRows] = useState<RevenueVoucherDto[]>([]);
  const [accounts, setAccounts] = useState<AccountRow[]>([]);
  const [currencies, setCurrencies] = useState<CurrencyRow[]>([]);
  const [partners, setPartners] = useState<AccountingPartner[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [vouchers, accs, currs, parts] = await Promise.all([
        accountingApi.getRevenueVouchers(),
        accountingApi.getAccounts() as Promise<AccountRow[]>,
        accountingApi.getCurrencies() as Promise<CurrencyRow[]>,
        accountingApi.getPartners() as Promise<AccountingPartner[]>,
      ]);
      setRows(vouchers);
      setAccounts(accs || []);
      setCurrencies(currs || []);
      setPartners(parts || []);
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل التحميل"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const accountLabelOf = useCallback(
    (id: number | null | undefined) => {
      if (!id) return "—";
      const a = accounts.find((x) => x.id === id);
      return a ? `${a.code ?? ""} ${a.name ?? ""}`.trim() : "—";
    },
    [accounts],
  );

  const payerLabelOf = useCallback(
    (r: RevenueVoucherDto) => r.payer_partner_name || r.payer_name || "—",
    [],
  );

  const doUnpost = useCallback(async (row: RevenueVoucherDto) => {
    if (busy) return;
    if (!(await confirm({
      title: "التراجع عن ترحيل سند الإيراد",
      message: `سيُحذف قيد سند الإيراد #${row.number} وتعود الأرصدة إلى ما كانت عليه. المتابعة؟`,
      confirmText: "ألغِ الترحيل",
      danger: true,
    }))) return;
    setBusy(true);
    setErr(null);
    try {
      await accountingApi.unpostRevenueVoucher(row.id);
      toast(`أُلغي ترحيل سند الإيراد #${row.number}`, "success");
      await load();
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "تعذّر التراجع عن الترحيل"));
    } finally {
      setBusy(false);
    }
  }, [busy, confirm, load, toast]);

  const columns: DenseColumn<RevenueVoucherDto>[] = [
    { key: "date", header: "التاريخ", width: "110px", render: (r) => formatDateLocalized(r.date) || r.date },
    { key: "number", header: "الرقم", width: "70px", render: (r) => r.number || "—" },
    {
      key: "revenue_account", header: "حساب الإيراد", width: "180px",
      render: (r) => (r.revenue_account_code
        ? `${r.revenue_account_code} — ${r.revenue_account_name ?? ""}`
        : accountLabelOf(r.revenue_account)),
    },
    { key: "amount", header: "المبلغ", width: "100px", numeric: true, render: (r) => formatMoney(r.amount) },
    {
      key: "payment_method", header: "طريقة القبض", width: "100px",
      render: (r) => PAYMENT_METHOD_LABEL[r.payment_method] || r.payment_method,
    },
    { key: "payer", header: "الدافع", width: "140px", render: (r) => payerLabelOf(r) },
    { key: "description", header: "الوصف", render: (r) => r.description || "—" },
    {
      key: "status", header: "الحالة", width: "90px",
      render: (r) => (
        <span className={r.is_posted ? "text-[var(--ktra-ok)]" : "text-[var(--ktra-ink-soft)]"}>
          {r.is_posted ? "مرحَّل" : "مسودة"}
        </span>
      ),
    },
    {
      key: "actions", header: "", width: "110px",
      render: (r) => (
        r.is_posted && can("finance.revenue.unpost") ? (
          <button
            type="button"
            className="ktra-toolbtn"
            disabled={busy}
            title={`إلغاء ترحيل سند الإيراد #${r.number}`}
            onClick={() => void doUnpost(r)}
          >
            <RotateCcw className="w-3 h-3" />
            إلغاء الترحيل
          </button>
        ) : null
      ),
    },
  ];

  const actions: KitToolbarAction[] = [
    ...(can("finance.revenue.create") ? [{
      key: "new", label: "سند إيراد جديد",
      icon: <Plus className="w-4 h-4" />, onClick: () => setCreating(true),
    }] : []),
    { key: "refresh", label: "تحديث", onClick: () => void load() },
  ];

  return (
    <div>
      {err && !creating && (
        <div className="ktra-banner ktra-banner--err" style={{ marginBottom: "8px" }}>{err}</div>
      )}
      <KitDocumentShell title="سندات الإيراد" actions={actions} status={<span className="ktra-status-item">{rows.length} سند</span>}>
        <KitDenseTable<RevenueVoucherDto>
          columns={columns}
          rows={rows}
          getRowKey={(r) => r.id}
          loading={loading}
          emptyHint="لا سندات إيراد بعد"
          exportable
          exportFilename="revenue-vouchers"
        />
      </KitDocumentShell>

      {creating && (
        <NewRevenueVoucherModal
          accounts={accounts}
          currencies={currencies}
          partners={partners}
          showPayer={(keepIfSet) => showAdv("doc.revenue-payer", keepIfSet)}
          onClose={() => setCreating(false)}
          onSaved={() => { setCreating(false); void load(); }}
        />
      )}
    </div>
  );
};

const NewRevenueVoucherModal: React.FC<{
  accounts: AccountRow[];
  currencies: CurrencyRow[];
  partners: AccountingPartner[];
  showPayer: (keepIfSet: boolean) => boolean;
  onClose: () => void;
  onSaved: () => void;
}> = ({ accounts, currencies, partners, showPayer, onClose, onSaved }) => {
  const toast = useToast();
  const { preferences } = useTenantSettings();
  // نفس الإعداد الذي يفرضه الخادم في `create_revenue_voucher`: تُخفى خانةُ
  // الاسم الحرّ حين يُلزِم بالربط، فلا يكتب المستخدم فيها ثم يُردّ بخطأ.
  const linkedOnly = voucherAccountEntryIsLinked(preferences?.voucher_account_entry_mode);
  const [date, setDate] = useState(today());
  const [amount, setAmount] = useState("");
  const [taxAmount, setTaxAmount] = useState("0");
  const [currencyId, setCurrencyId] = useState<number | "">(currencies[0]?.CurrencyID ?? "");
  const [exchangeRate] = useState("1");
  const [paymentMethod, setPaymentMethod] = useState<RevenuePaymentMethod>("cash");
  const [revenueAccountId, setRevenueAccountId] = useState<number | "">("");
  const [revenueAccountName, setRevenueAccountName] = useState("");
  const [cashAccountId, setCashAccountId] = useState<number | "">("");
  const [payerPartnerId, setPayerPartnerId] = useState<number | "">("");
  const [payerName, setPayerName] = useState("");
  const [description, setDescription] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const amountNum = Number(amount) || 0;
  const taxNum = Number(taxAmount) || 0;

  const revenueAccountLabel = useMemo(() => {
    if (revenueAccountId) {
      const a = accounts.find((x) => x.id === revenueAccountId);
      return a ? `${a.code ?? ""} ${a.name ?? ""}`.trim() : "";
    }
    return revenueAccountName.trim();
  }, [accounts, revenueAccountId, revenueAccountName]);

  const cashAccountLabel = useMemo(() => {
    const a = accounts.find((x) => x.id === cashAccountId);
    return a ? `${a.code ?? ""} ${a.name ?? ""}`.trim() : null;
  }, [accounts, cashAccountId]);

  const payerLabel = payerPartnerId
    ? (partners.find((p) => p.id === payerPartnerId)?.name || null)
    : (payerName.trim() || null);

  const preview = buildRevenueVoucherEntryPreview({
    revenueAccountLabel: revenueAccountLabel || "حساب الإيراد",
    amount: amountNum,
    taxAmount: taxNum,
    paymentMethod,
    cashAccountLabel,
    payerLabel,
  });

  const submit = useCallback(async () => {
    if (amountNum <= 0) {
      setErr("المبلغ يجب أن يكون أكبر من صفر");
      return;
    }
    if (!revenueAccountId && (linkedOnly || !revenueAccountName.trim())) {
      setErr(linkedOnly
        ? "إعدادات الشركة تُلزم باختيار حساب الإيراد من الشجرة"
        : "اختر حساب الإيراد من الشجرة أو اكتب اسمه");
      return;
    }
    if (revenueVoucherRequiresCashAccount(paymentMethod) && !cashAccountId) {
      setErr("حدّد الصندوق/البنك الذي قُبض فيه");
      return;
    }
    if (!currencyId) {
      setErr("العملة مطلوبة");
      return;
    }
    setSubmitting(true);
    setErr(null);
    try {
      const saved = await accountingApi.createRevenueVoucher({
        date,
        amount: amountNum,
        tax_amount: taxNum,
        currency: Number(currencyId),
        exchange_rate: exchangeRate || "1",
        payment_method: paymentMethod,
        ...(revenueAccountId ? { revenue_account: Number(revenueAccountId) } : {}),
        ...(!revenueAccountId && revenueAccountName.trim() ? { revenue_account_name: revenueAccountName.trim() } : {}),
        ...(revenueVoucherRequiresCashAccount(paymentMethod) && cashAccountId ? { cash_or_bank_account: Number(cashAccountId) } : {}),
        ...(payerPartnerId ? { payer_partner: Number(payerPartnerId) } : {}),
        ...(!payerPartnerId && payerName.trim() ? { payer_name: payerName.trim() } : {}),
        ...(description.trim() ? { description: description.trim() } : {}),
      });
      toast(`تم تسجيل سند الإيراد #${saved.number} وترحيله`, "success");
      onSaved();
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل حفظ سند الإيراد"));
    } finally {
      setSubmitting(false);
    }
  }, [amountNum, taxNum, currencyId, exchangeRate, paymentMethod, revenueAccountId, revenueAccountName,
      linkedOnly, cashAccountId, payerPartnerId, payerName, description, date, onSaved, toast]);

  // قاعدة السقوط للظهور: دافعٌ سُمِّي فعلاً يبقى ظاهراً في الوضع السهل.
  const showPayerField = showPayer(Boolean(payerPartnerId || payerName));

  return (
    <PaymentVoucherModal
      title="سند إيراد جديد"
      error={err}
      submitting={submitting}
      submitLabel="حفظ وترحيل"
      onClose={onClose}
      onSubmit={() => void submit()}
    >
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px" }}>
        <label className="ktra-field">
          <span className="ktra-field-label">التاريخ</span>
          <input type="date" className="ktra-input" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label className="ktra-field">
          <span className="ktra-field-label">المبلغ *</span>
          <input type="number" step="0.01" className="ktra-input ktra-num" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
        <label className="ktra-field">
          <span className="ktra-field-label">العملة</span>
          <select className="ktra-input" value={currencyId} onChange={(e) => setCurrencyId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">—</option>
            {currencies.map((c) => <option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}</option>)}
          </select>
        </label>

        <label className="ktra-field" style={{ gridColumn: linkedOnly ? "span 3" : "span 2" }}>
          <span className="ktra-field-label">حساب الإيراد — ماذا قُبض *</span>
          <AccountTreeField
            accounts={accounts}
            value={revenueAccountId}
            onChange={(id) => { setRevenueAccountId(id ?? ""); if (id) setRevenueAccountName(""); }}
            purpose="revenue"
            title="اختيار حساب الإيراد"
            placeholder="— اختر من الشجرة —"
          />
        </label>
        {!linkedOnly && (
          <label className="ktra-field">
            <span className="ktra-field-label">أو اسم إيراد جديد</span>
            <input
              className="ktra-input"
              placeholder="مثال: عمولة وساطة"
              value={revenueAccountName}
              disabled={!!revenueAccountId}
              onChange={(e) => setRevenueAccountName(e.target.value)}
            />
          </label>
        )}

        <label className="ktra-field">
          <span className="ktra-field-label">طريقة القبض</span>
          <select
            className="ktra-input" value={paymentMethod}
            onChange={(e) => setPaymentMethod(e.target.value as RevenuePaymentMethod)}
          >
            {REVENUE_PAYMENT_METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </label>
        {revenueVoucherRequiresCashAccount(paymentMethod) && (
          <label className="ktra-field" style={{ gridColumn: "span 2" }}>
            <span className="ktra-field-label">الصندوق / البنك *</span>
            <AccountTreeField
              accounts={accounts}
              value={cashAccountId}
              onChange={(id) => setCashAccountId(id ?? "")}
              purpose="cash"
              title="اختيار الصندوق / البنك"
            />
          </label>
        )}

        <label className="ktra-field">
          <span className="ktra-field-label">ضريبة مخرجات (اختياري)</span>
          <input type="number" step="0.01" className="ktra-input ktra-num" value={taxAmount} onChange={(e) => setTaxAmount(e.target.value)} />
        </label>
      </div>

      {showPayerField && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <label className="ktra-field">
            <span className="ktra-field-label">الدافع (اختياري)</span>
            <select
              className="ktra-input" value={payerPartnerId}
              onChange={(e) => { setPayerPartnerId(e.target.value ? Number(e.target.value) : ""); if (e.target.value) setPayerName(""); }}
            >
              <option value="">— بلا دافع —</option>
              {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <label className="ktra-field">
            <span className="ktra-field-label">أو اسم حرّ</span>
            <input
              className="ktra-input" value={payerName} disabled={!!payerPartnerId}
              onChange={(e) => setPayerName(e.target.value)}
            />
          </label>
        </div>
      )}

      <label className="ktra-field" style={{ marginTop: "12px", display: "block" }}>
        <span className="ktra-field-label">الوصف (اختياري)</span>
        <textarea className="ktra-input" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
      </label>

      <div style={{ fontSize: "11px", marginTop: "8px", color: "var(--ktra-ink-soft)" }}>
        القيد: {preview.length
          ? preview.map((line) => `${line.side} ${line.label} ${formatMoney(line.amount)}`).join(" / ")
          : "—"}
      </div>
    </PaymentVoucherModal>
  );
};

export default RevenueVouchersPage;
