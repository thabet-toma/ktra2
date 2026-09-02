/**
 * issue #56 — سند مصروف: مستندٌ عامٌّ لكل شركة، بلا مورّدٍ إلزامي وبلا مخزون.
 *
 * المشكلة قبل هذه الشاشة كانت شخصاً لا نقطة API: «قيدٌ يدوي يلزمه من يعرف
 * المدين من الدائن — صاحب المحلّ لا يعرف». النموذج هنا يسأل بلغته: كم، بماذا
 * صُرف، وكيف دُفع — ويُقرّر عنه المدين والدائن، مع معاينة القيد قبل الحفظ
 * (`utils/expenseVoucherEntryPreview.ts`، نفس نهج `voucherEntryPreview.ts`
 * لسندَي القبض والصرف).
 *
 * الحفظ يرحّل فوراً (لا مسودة وسطى — الخادم `create_expense_voucher` يفعل
 * الاثنين في نداء واحد)، والتراجع فعلٌ صريح خلف تأكيد.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { accountingApi } from "../../services/accountingApi";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { usePermissions } from "../../contexts/PermissionsContext";
import { useSimpleUi } from "../../hooks/useSimpleUi";
import { humanizeThrown } from "../../utils/drfError";
import { formatMoney } from "../../utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";
import { AccountTreeField } from "./AccountTreePicker";
import { PaymentVoucherModal } from "../sales/PaymentVoucherParts";
import {
  buildExpenseVoucherEntryPreview,
  EXPENSE_PAYMENT_METHODS,
  expenseVoucherRequiresCashAccount,
  type ExpensePaymentMethod,
} from "../../utils/expenseVoucherEntryPreview";
import { KitDocumentShell, KitDenseTable } from "../kit";
import type { KitToolbarAction, DenseColumn } from "../kit";
import { Plus, RotateCcw } from "lucide-react";
import type { AccountingPartner, ExpenseVoucherDto } from "../../types/accounting";

type AccountRow = {
  id: number; code: string | null; name: string | null; parent: number | null; account_type?: string | null;
};
type CurrencyRow = { CurrencyID: number; Code: string };

const PAYMENT_METHOD_LABEL: Record<ExpensePaymentMethod, string> =
  Object.fromEntries(EXPENSE_PAYMENT_METHODS.map((m) => [m.value, m.label])) as Record<ExpensePaymentMethod, string>;

const today = () => new Date().toISOString().slice(0, 10);

export const ExpenseVouchersPage: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const { can } = usePermissions();
  const { show: showAdv } = useSimpleUi();

  const [rows, setRows] = useState<ExpenseVoucherDto[]>([]);
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
        accountingApi.getExpenseVouchers(),
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

  const beneficiaryLabelOf = useCallback(
    (r: ExpenseVoucherDto) => r.beneficiary_partner_name || r.beneficiary_name || "—",
    [],
  );

  const doUnpost = useCallback(async (row: ExpenseVoucherDto) => {
    if (busy) return;
    if (!(await confirm({
      title: "التراجع عن ترحيل سند المصروف",
      message: `سيُحذف قيد سند المصروف #${row.number} وتعود الأرصدة إلى ما كانت عليه. المتابعة؟`,
      confirmText: "ألغِ الترحيل",
      danger: true,
    }))) return;
    setBusy(true);
    setErr(null);
    try {
      await accountingApi.unpostExpenseVoucher(row.id);
      toast(`أُلغي ترحيل سند المصروف #${row.number}`, "success");
      await load();
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "تعذّر التراجع عن الترحيل"));
    } finally {
      setBusy(false);
    }
  }, [busy, confirm, load, toast]);

  const columns: DenseColumn<ExpenseVoucherDto>[] = [
    { key: "date", header: "التاريخ", width: "110px", render: (r) => formatDateLocalized(r.date) || r.date },
    { key: "number", header: "الرقم", width: "70px", render: (r) => r.number || "—" },
    {
      key: "expense_account", header: "حساب المصروف", width: "180px",
      render: (r) => (r.expense_account_code
        ? `${r.expense_account_code} — ${r.expense_account_name ?? ""}`
        : accountLabelOf(r.expense_account)),
    },
    { key: "amount", header: "المبلغ", width: "100px", numeric: true, render: (r) => formatMoney(r.amount) },
    {
      key: "payment_method", header: "طريقة الدفع", width: "100px",
      render: (r) => PAYMENT_METHOD_LABEL[r.payment_method] || r.payment_method,
    },
    { key: "beneficiary", header: "المستفيد", width: "140px", render: (r) => beneficiaryLabelOf(r) },
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
        r.is_posted && can("finance.expense.unpost") ? (
          <button
            type="button"
            className="ktra-toolbtn"
            disabled={busy}
            title={`إلغاء ترحيل سند المصروف #${r.number}`}
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
    ...(can("finance.expense.create") ? [{
      key: "new", label: "سند مصروف جديد",
      icon: <Plus className="w-4 h-4" />, onClick: () => setCreating(true),
    }] : []),
    { key: "refresh", label: "تحديث", onClick: () => void load() },
  ];

  return (
    <div>
      {err && !creating && (
        <div className="ktra-banner ktra-banner--err" style={{ marginBottom: "8px" }}>{err}</div>
      )}
      <KitDocumentShell title="سندات المصروف" actions={actions} status={<span className="ktra-status-item">{rows.length} سند</span>}>
        <KitDenseTable<ExpenseVoucherDto>
          columns={columns}
          rows={rows}
          getRowKey={(r) => r.id}
          loading={loading}
          emptyHint="لا سندات مصروف بعد"
          exportable
          exportFilename="expense-vouchers"
        />
      </KitDocumentShell>

      {creating && (
        <NewExpenseVoucherModal
          accounts={accounts}
          currencies={currencies}
          partners={partners}
          showBeneficiary={(keepIfSet) => showAdv("doc.expense-beneficiary", keepIfSet)}
          onClose={() => setCreating(false)}
          onSaved={() => { setCreating(false); void load(); }}
        />
      )}
    </div>
  );
};

const NewExpenseVoucherModal: React.FC<{
  accounts: AccountRow[];
  currencies: CurrencyRow[];
  partners: AccountingPartner[];
  showBeneficiary: (keepIfSet: boolean) => boolean;
  onClose: () => void;
  onSaved: () => void;
}> = ({ accounts, currencies, partners, showBeneficiary, onClose, onSaved }) => {
  const toast = useToast();
  const [date, setDate] = useState(today());
  const [amount, setAmount] = useState("");
  const [taxAmount, setTaxAmount] = useState("0");
  const [currencyId, setCurrencyId] = useState<number | "">(currencies[0]?.CurrencyID ?? "");
  const [exchangeRate, setExchangeRate] = useState("1");
  const [paymentMethod, setPaymentMethod] = useState<ExpensePaymentMethod>("cash");
  const [expenseAccountId, setExpenseAccountId] = useState<number | "">("");
  const [expenseAccountName, setExpenseAccountName] = useState("");
  const [cashAccountId, setCashAccountId] = useState<number | "">("");
  const [beneficiaryPartnerId, setBeneficiaryPartnerId] = useState<number | "">("");
  const [beneficiaryName, setBeneficiaryName] = useState("");
  const [description, setDescription] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const amountNum = Number(amount) || 0;
  const taxNum = Number(taxAmount) || 0;

  const expenseAccountLabel = useMemo(() => {
    if (expenseAccountId) {
      const a = accounts.find((x) => x.id === expenseAccountId);
      return a ? `${a.code ?? ""} ${a.name ?? ""}`.trim() : "";
    }
    return expenseAccountName.trim();
  }, [accounts, expenseAccountId, expenseAccountName]);

  const cashAccountLabel = useMemo(() => {
    const a = accounts.find((x) => x.id === cashAccountId);
    return a ? `${a.code ?? ""} ${a.name ?? ""}`.trim() : null;
  }, [accounts, cashAccountId]);

  const beneficiaryLabel = beneficiaryPartnerId
    ? (partners.find((p) => p.id === beneficiaryPartnerId)?.name || null)
    : (beneficiaryName.trim() || null);

  const preview = buildExpenseVoucherEntryPreview({
    expenseAccountLabel: expenseAccountLabel || "حساب المصروف",
    amount: amountNum,
    taxAmount: taxNum,
    paymentMethod,
    cashAccountLabel,
    beneficiaryLabel,
  });

  const submit = useCallback(async () => {
    if (amountNum <= 0) {
      setErr("المبلغ يجب أن يكون أكبر من صفر");
      return;
    }
    if (!expenseAccountId && !expenseAccountName.trim()) {
      setErr("اختر حساب المصروف من الشجرة أو اكتب اسمه");
      return;
    }
    if (expenseVoucherRequiresCashAccount(paymentMethod) && !cashAccountId) {
      setErr("حدّد الصندوق/البنك الذي دُفع منه");
      return;
    }
    if (!currencyId) {
      setErr("العملة مطلوبة");
      return;
    }
    setSubmitting(true);
    setErr(null);
    try {
      const saved = await accountingApi.createExpenseVoucher({
        date,
        amount: amountNum,
        tax_amount: taxNum,
        currency: Number(currencyId),
        exchange_rate: exchangeRate || "1",
        payment_method: paymentMethod,
        ...(expenseAccountId ? { expense_account: Number(expenseAccountId) } : {}),
        ...(!expenseAccountId && expenseAccountName.trim() ? { expense_account_name: expenseAccountName.trim() } : {}),
        ...(expenseVoucherRequiresCashAccount(paymentMethod) && cashAccountId ? { cash_or_bank_account: Number(cashAccountId) } : {}),
        ...(beneficiaryPartnerId ? { beneficiary_partner: Number(beneficiaryPartnerId) } : {}),
        ...(!beneficiaryPartnerId && beneficiaryName.trim() ? { beneficiary_name: beneficiaryName.trim() } : {}),
        ...(description.trim() ? { description: description.trim() } : {}),
      });
      toast(`تم تسجيل سند المصروف #${saved.number} وترحيله`, "success");
      onSaved();
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل حفظ سند المصروف"));
    } finally {
      setSubmitting(false);
    }
  }, [amountNum, taxNum, currencyId, exchangeRate, paymentMethod, expenseAccountId, expenseAccountName,
      cashAccountId, beneficiaryPartnerId, beneficiaryName, description, date, onSaved, toast]);

  // قاعدة السقوط للظهور: مستفيدٌ سُمِّي فعلاً (من فتح النافذة على تعديل لاحق
  // أو من إدخال جارٍ) يبقى ظاهراً في الوضع السهل رغم طيّه افتراضياً.
  const showBeneficiaryField = showBeneficiary(Boolean(beneficiaryPartnerId || beneficiaryName));

  return (
    <PaymentVoucherModal
      title="سند مصروف جديد"
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

        <label className="ktra-field" style={{ gridColumn: "span 2" }}>
          <span className="ktra-field-label">حساب المصروف — ماذا صُرف *</span>
          <AccountTreeField
            accounts={accounts}
            value={expenseAccountId}
            onChange={(id) => { setExpenseAccountId(id ?? ""); if (id) setExpenseAccountName(""); }}
            purpose="expense"
            title="اختيار حساب المصروف"
            placeholder="— اختر من الشجرة —"
          />
        </label>
        <label className="ktra-field">
          <span className="ktra-field-label">أو اسم مصروف جديد</span>
          <input
            className="ktra-input"
            placeholder="مثال: اشتراك إنترنت"
            value={expenseAccountName}
            disabled={!!expenseAccountId}
            onChange={(e) => setExpenseAccountName(e.target.value)}
          />
        </label>

        <label className="ktra-field">
          <span className="ktra-field-label">طريقة الدفع</span>
          <select
            className="ktra-input" value={paymentMethod}
            onChange={(e) => setPaymentMethod(e.target.value as ExpensePaymentMethod)}
          >
            {EXPENSE_PAYMENT_METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </label>
        {expenseVoucherRequiresCashAccount(paymentMethod) && (
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
          <span className="ktra-field-label">ضريبة مدخلات (اختياري)</span>
          <input type="number" step="0.01" className="ktra-input ktra-num" value={taxAmount} onChange={(e) => setTaxAmount(e.target.value)} />
        </label>
      </div>

      {showBeneficiaryField && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <label className="ktra-field">
            <span className="ktra-field-label">المستفيد (اختياري)</span>
            <select
              className="ktra-input" value={beneficiaryPartnerId}
              onChange={(e) => { setBeneficiaryPartnerId(e.target.value ? Number(e.target.value) : ""); if (e.target.value) setBeneficiaryName(""); }}
            >
              <option value="">— بلا مستفيد —</option>
              {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <label className="ktra-field">
            <span className="ktra-field-label">أو اسم حرّ</span>
            <input
              className="ktra-input" value={beneficiaryName} disabled={!!beneficiaryPartnerId}
              onChange={(e) => setBeneficiaryName(e.target.value)}
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

export default ExpenseVouchersPage;
