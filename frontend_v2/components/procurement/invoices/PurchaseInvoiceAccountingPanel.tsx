/**
 * لوحة محاسبة فاتورة الشراء — فصلاً عن نموذج الفاتورة الرئيسي.
 *
 * الغرض: ضمان ترحيل صحيح للمحاسبة مع:
 *  - مربع «مدفوعة» (مؤشَّر = نقدي) + حساب الصندوق عند التأشير
 *  - إدارة الرسوم الإضافية (شحن/تخليص/جمركي/…) مع اختيار حساب لكل رسم
 *  - معاينة القيد المحاسبي قبل الترحيل
 *  - زر ترحيل يستدعي post-to-accounting الآمن (مع تحقق توازن)
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Plus,
  Trash2,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Calculator,
  Send,
  RefreshCw,
  PackageCheck,
  Undo2,
  Banknote,
  Receipt,
} from "lucide-react";
import { purchaseInvoiceApi } from "@/services/purchaseInvoiceApi";
import { accountingApi } from "@/services/accountingApi";
import { formatMoney } from "@/utils/formatNumber";
import type {
  PurchaseInvoiceDto,
  PurchaseInvoiceFeeDto,
  PurchaseInvoiceItemDto,
  ReceiptStatus,
} from "@/types/purchaseInvoice";
import { ReceiveGoodsModal } from "./ReceiveGoodsModal";
import { SettleFromOnAccountModal } from "@/components/shared/SettleFromOnAccountModal";
import { useConfirm } from "@/contexts/ConfirmContext";

const RECEIPT_BADGE: Record<ReceiptStatus, { label: string; cls: string }> = {
  not_received: { label: "غير مستلمة", cls: "aseel-text-state" },
  partially_received: { label: "مستلمة جزئياً", cls: "aseel-text-ink" },
  received: { label: "مستلمة", cls: "aseel-text-soft" },
};

interface AccountDto {
  id: number;
  code?: string;
  name?: string;
  account_type?: string;
  is_active?: boolean;
}

interface Props {
  invoiceId: number;
  onPosted?: (journalId: number) => void;
  readOnly?: boolean;
}

type PaymentType = "credit" | "cash";

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  Asset: "أصل",
  Liability: "التزام",
  Equity: "حقوق ملكية",
  Revenue: "إيراد",
  Expense: "مصروف",
};

export const PurchaseInvoiceAccountingPanel: React.FC<Props> = ({
  invoiceId,
  onPosted,
  readOnly,
}) => {
  const confirmDialog = useConfirm();
  const [loading, setLoading] = useState(true);
  const [invoice, setInvoice] = useState<PurchaseInvoiceDto | null>(null);
  const [accounts, setAccounts] = useState<AccountDto[]>([]);
  const [fees, setFees] = useState<PurchaseInvoiceFeeDto[]>([]);
  const [items, setItems] = useState<PurchaseInvoiceItemDto[]>([]);
  const [paymentType, setPaymentType] = useState<PaymentType>("credit");
  const [cashAccountId, setCashAccountId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showReceive, setShowReceive] = useState(false);
  // T-ONACC: تسديد الفاتورة من رصيد المورد «على الحساب» (سندات صرف غير موزَّعة).
  const [showSettleModal, setShowSettleModal] = useState(false);
  // وصل دفع للمورد (Feature 2)
  const [payAmount, setPayAmount] = useState("");
  const [payAccountId, setPayAccountId] = useState<number | null>(null);
  const [paySaving, setPaySaving] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [inv, accs] = await Promise.all([
        purchaseInvoiceApi.get(invoiceId),
        accountingApi.getAccounts() as Promise<AccountDto[]>,
      ]);
      setInvoice(inv);
      setAccounts(Array.isArray(accs) ? accs : []);
      setFees(Array.isArray(inv.fees) ? [...inv.fees] : []);
      setItems(Array.isArray(inv.items) ? [...inv.items] : []);
      setPaymentType((inv.payment_type as PaymentType) || "credit");
      setCashAccountId(inv.cash_or_bank_account ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذر التحميل");
    } finally {
      setLoading(false);
    }
  }, [invoiceId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // ─── Filters لاختيار الحسابات المناسبة ─────────────────────────────────
  const expenseAccountOptions = useMemo(
    () =>
      accounts
        .filter(
          (a) =>
            a.is_active !== false &&
            (a.account_type === "Expense" || a.account_type === "Asset") &&
            a.code // نطلب كود حساب
        )
        .sort((a, b) => (a.code || "").localeCompare(b.code || "")),
    [accounts]
  );
  const cashAccountOptions = useMemo(
    () =>
      accounts
        .filter(
          (a) =>
            a.is_active !== false &&
            a.account_type === "Asset" &&
            a.code &&
            (a.code.startsWith("1101") ||
              a.code.startsWith("1102") ||
              (a.name || "").toLowerCase().includes("صندوق") ||
              (a.name || "").toLowerCase().includes("بنك") ||
              (a.name || "").toLowerCase().includes("cash") ||
              (a.name || "").toLowerCase().includes("bank"))
        )
        .sort((a, b) => (a.code || "").localeCompare(b.code || "")),
    [accounts]
  );

  // ─── تفاعل المستخدم مع الرسوم ──────────────────────────────────────────
  const addFee = () => {
    const firstExp =
      expenseAccountOptions.find((a) => (a.code || "").startsWith("53")) ||
      expenseAccountOptions[0];
    setFees((f) => [
      ...f,
      {
        description: "",
        amount: 0,
        calculation_type: "amount",
        calculation_value: 0,
        percentage_basis: "goods",
        expense_account: firstExp?.id || 0,
        capitalize_to_inventory: false,
        is_taxable: false,
      },
    ]);
  };
  const removeFee = (idx: number) => {
    setFees((f) => f.filter((_, i) => i !== idx));
  };
  const updateFee = (idx: number, patch: Partial<PurchaseInvoiceFeeDto>) => {
    setFees((f) => f.map((x, i) => (i === idx ? { ...x, ...patch } : x)));
  };

  const updateItemAccount = (idx: number, accountId: number | null) => {
    setItems((items) => items.map((x, i) => (i === idx ? { ...x, expense_account: accountId } : x)));
  };

  // ─── حفظ الرسوم + نوع الدفع ────────────────────────────────────────────
  const saveAccountingFields = async () => {
    if (!invoice) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const payload: Partial<PurchaseInvoiceDto> = {
        payment_type: paymentType,
        cash_or_bank_account: paymentType === "cash" ? cashAccountId : null,
        fees: fees.map((f) => ({
          ...(f.id ? { id: f.id } : {}),
          description: f.description || "رسم",
          amount: Number(f.amount) || 0,
          calculation_type: f.calculation_type || "amount",
          calculation_value: Number(f.calculation_value ?? f.amount) || 0,
          percentage_basis: f.percentage_basis || "goods",
          expense_account: f.expense_account,
          capitalize_to_inventory: !!f.capitalize_to_inventory,
          is_taxable: !!f.is_taxable,
        })),
        items: items,
      };
      const updated = await purchaseInvoiceApi.update(invoiceId, payload);
      setInvoice(updated);
      setFees(Array.isArray(updated.fees) ? [...updated.fees] : []);
      setItems(Array.isArray(updated.items) ? [...updated.items] : []);
      setSuccess("تم حفظ الإعدادات المحاسبية.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذر الحفظ");
    } finally {
      setSaving(false);
    }
  };

  // ─── ترحيل ──────────────────────────────────────────────────────────────
  const post = async () => {
    if (!invoice) return;
    setPosting(true);
    setError(null);
    setSuccess(null);
    try {
      // حفظ تلقائي قبل الترحيل لضمان تزامن البيانات
      await saveAccountingFields();
      const result = await purchaseInvoiceApi.postToAccounting(invoiceId);
      setSuccess(
        `✅ تم الترحيل بنجاح — رقم القيد: ${result.journal_id}`
      );
      onPosted?.(result.journal_id);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذر الترحيل");
    } finally {
      setPosting(false);
    }
  };

  // ─── التراجع عن الترحيل (حذف القيود) ─────────────────────────────────────
  const unpost = async () => {
    if (!invoice) return;
    if (!(await confirmDialog({
      title: "تراجع عن الترحيل",
      message:
        "هذا المستند مرحَّل. سيؤدي التراجع عن الترحيل إلى حذف كل قيود اليومية " +
        "وحركات الاستلام الخاصة بهذه الفاتورة وإرجاعها مسودة. متابعة؟",
      confirmText: "تراجع عن الترحيل",
    }))) return;
    setPosting(true);
    setError(null);
    setSuccess(null);
    try {
      await purchaseInvoiceApi.unpost(invoiceId);
      setSuccess("تم التراجع عن الترحيل وحذف القيود. الفاتورة الآن مسودة.");
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذر التراجع عن الترحيل");
    } finally {
      setPosting(false);
    }
  };

  // ─── وصل دفع للمورد (Feature 2): سند صرف مستقل Dr ذمم المورد / Cr صندوق ───
  const addSupplierPayment = async () => {
    if (!invoice) return;
    const amt = Number(payAmount);
    if (!amt || amt <= 0) {
      setError("أدخل مبلغ وصل الدفع.");
      return;
    }
    if (!payAccountId) {
      setError("اختر حساب الصندوق/البنك لوصل الدفع.");
      return;
    }
    setPaySaving(true);
    setError(null);
    setSuccess(null);
    try {
      await purchaseInvoiceApi.addSupplierPayment({
        partner: invoice.partner,
        purchase_invoice: invoiceId,
        payment_date: new Date().toISOString().slice(0, 10),
        amount: amt.toFixed(2),
        currency: invoice.currency ?? null,
        cash_or_bank_account: payAccountId,
        notes: `وصل دفع فاتورة ${invoice.invoice_number || invoice.id}`,
        // T-AUTOPOST: وصل الدفع من داخل الفاتورة يُرحَّل دائماً (لا مسودة) مهما كان إعداد الشركة.
        auto_post: true,
      });
      setSuccess("✅ تم تسجيل وصل الدفع وترحيله (مدين ذمم المورد / دائن الصندوق).");
      setPayAmount("");
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذر تسجيل وصل الدفع");
    } finally {
      setPaySaving(false);
    }
  };

  // ─── معاينة القيد المحاسبي ─────────────────────────────────────────────
  const preview = useMemo(() => {
    if (!invoice) return null;
    const grand = Number(invoice.grand_total) || 0;
    const tax = Number(invoice.tax_amount) || 0;
    const feeTotal = fees.reduce((s, f) => s + (Number(f.amount) || 0), 0);
    const capitalizedFees = fees
      .filter((f) => f.capitalize_to_inventory)
      .reduce((s, f) => s + (Number(f.amount) || 0), 0);
    const nonCapFees = feeTotal - capitalizedFees;
    const merchandiseNet = grand - tax - nonCapFees;
    const inventoryDebit = merchandiseNet + capitalizedFees;

    const lines: {
      account: string;
      debit: number;
      credit: number;
      note?: string;
    }[] = [];

    // Default item behavior is still going to single inventory account unless mapped
    const totalDiscount = Number(invoice.discount_amount) || 0;
    let sumMapped = 0;

    items.filter(it => it.expense_account).forEach(it => {
        const acc = accounts.find(a => a.id === it.expense_account);
        const label = acc ? `${acc.code || "?"} — ${acc.name || ""}` : `حساب #${it.expense_account}`;
        let lineAmount = Number(it.total_price) || 0;
        sumMapped += lineAmount;
        lines.push({
            account: label,
            debit: lineAmount,
            credit: 0,
            note: it.name,
        });
    });

    const remainingInventoryDebit = merchandiseNet + capitalizedFees - sumMapped;

    if (remainingInventoryDebit > 0) {
      lines.push({
        account: "مخزون / مشتريات (1104)",
        debit: remainingInventoryDebit,
        credit: 0,
        note:
          capitalizedFees > 0
            ? `صافي البضاعة + رسوم مرسملة (${formatMoney(capitalizedFees)})`
            : "صافي البضاعة غير المخصصة",
      });
    }
    if (tax > 0) {
      lines.push({
        account: "ضريبة مدخلات (1105)",
        debit: tax,
        credit: 0,
      });
    }
    fees
      .filter((f) => !f.capitalize_to_inventory && (Number(f.amount) || 0) > 0)
      .forEach((f) => {
        const acc = accounts.find((a) => a.id === f.expense_account);
        const label = acc
          ? `${acc.code || "?"} — ${acc.name || ""}`
          : `حساب #${f.expense_account}`;
        lines.push({
          account: label,
          debit: Number(f.amount) || 0,
          credit: 0,
          note: f.description,
        });
      });

    const creditTotal = grand + feeTotal;
    const supplierLabel = `ذمم مورد (${invoice.partner_name || "—"})`;
    
    // إثبات الفاتورة على حساب المورد (Feature 2: لا تسوية نقدية في قيد الفاتورة —
    // الدفع للمورد يُسجَّل كوصل دفع مستقل بعد الترحيل).
    lines.push({ account: supplierLabel, debit: 0, credit: creditTotal, note: "إثبات الفاتورة" });

    const totalDebit = lines.reduce((s, l) => s + l.debit, 0);
    const totalCredit = lines.reduce((s, l) => s + l.credit, 0);
    const isBalanced = Math.abs(totalDebit - totalCredit) < 0.015;

    return { lines, totalDebit, totalCredit, isBalanced };
  }, [invoice, fees, paymentType, cashAccountId, accounts]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 justify-center py-12 aseel-text-soft">
        <Loader2 className="w-5 h-5 animate-spin" />
        <span>جارٍ تحميل البيانات المحاسبية…</span>
      </div>
    );
  }
  if (!invoice) return null;

  const isPosted = !!invoice.is_posted;
  const disableEdit = isPosted || !!readOnly;

  return (
    <div
      dir="rtl"
      className="mt-6 rounded-2xl border-2 border-[var(--color-border)] dark:border-[var(--color-border)] aseel-bg-field dark:aseel-bg-panel shadow-sm overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)] dark:border-[var(--color-border)]/60 bg-gradient-to-l from-[var(--color-primary)] to-white dark:from-[var(--color-primary)]/30 dark:aseel-bg-panel">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-[var(--color-primary)] text-white rounded-xl">
            <Calculator className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-lg font-bold aseel-text-ink dark:text-white">
              المحاسبة والترحيل
            </h3>
            <p className="text-xs aseel-text-soft dark:aseel-text-soft">
              الرسوم + نوع الدفع + معاينة القيد
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 justify-end">
          {/* task16 C10: الإجمالي + المتبقي + حالة الدفع */}
          <span className="px-3 py-1.5 rounded-full text-sm font-medium border aseel-border-soft aseel-bg-panel aseel-text-ink" title="إجمالي الفاتورة">
            الإجمالي: {Number(invoice.grand_total || 0).toLocaleString()} {invoice.currency_code || ""}
          </span>
          <span className="px-3 py-1.5 rounded-full text-sm font-medium border aseel-border-soft aseel-bg-panel aseel-text-ink" title="المبلغ المدفوع المرحّل">
            المدفوع: {Number(invoice.amount_paid || 0).toLocaleString()} {invoice.currency_code || ""}
          </span>
          <span className="px-3 py-1.5 rounded-full text-sm font-medium border aseel-border-soft aseel-bg-panel aseel-text-ink" title="المبلغ المتبقي">
            المتبقي: {Number(invoice.remaining_balance ?? invoice.grand_total ?? 0).toLocaleString()} {invoice.currency_code || ""}
          </span>
          {invoice.payment_status && (
            <span
              className={`px-3 py-1.5 rounded-full text-sm font-medium border aseel-border-soft ${
                invoice.payment_status === "paid"
                  ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
                  : invoice.payment_status === "partially_paid"
                    ? "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300"
                    : "aseel-bg-panel aseel-text-state"
              }`}
              title="حالة الدفع"
            >
              {invoice.payment_status_display ||
                (invoice.payment_status === "paid"
                  ? "مدفوعة"
                  : invoice.payment_status === "partially_paid"
                    ? "مدفوعة جزئياً"
                    : "غير مدفوعة")}
            </span>
          )}
          {invoice.receipt_status && (
            <span
              className={`px-3 py-1.5 rounded-full text-sm font-medium border aseel-border-soft aseel-bg-panel ${
                RECEIPT_BADGE[invoice.receipt_status]?.cls || ""
              }`}
              title="حالة استلام البضاعة للمخزن"
            >
              {invoice.receipt_status_display ||
                RECEIPT_BADGE[invoice.receipt_status]?.label}
            </span>
          )}
          {invoice.is_local && invoice.receipt_status !== "received" && !readOnly && (
            <button
              onClick={() => setShowReceive(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-full text-sm font-medium"
              title="استلام البضاعة وعكسها على المستودع"
            >
              <PackageCheck className="w-4 h-4" />
              استلام البضاعة
            </button>
          )}
          <button
            onClick={reload}
            className="p-2 aseel-text-soft dark:aseel-text-soft hover:aseel-bg-panel dark:hover:aseel-bg-panel rounded-lg"
            title="تحديث"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          {isPosted ? (
            <span className="flex items-center gap-1.5 px-3 py-1.5 aseel-bg-panel dark:aseel-bg-panel/40 aseel-text-ink dark:aseel-text-soft rounded-full text-sm font-medium border aseel-border-soft dark:aseel-border-soft">
              <CheckCircle2 className="w-4 h-4" />
              مرحّلة (قيد #{invoice.journal_id_display})
            </span>
          ) : (
            <span className="flex items-center gap-1.5 px-3 py-1.5 aseel-bg-panel dark:aseel-bg-panel/40 aseel-text-ink dark:aseel-text-soft rounded-full text-sm font-medium border aseel-border-soft dark:aseel-border-soft">
              <AlertTriangle className="w-4 h-4" />
              غير مرحّلة
            </span>
          )}
        </div>
      </div>

      <div className="p-6 space-y-6">
        {error && (
          <div className="p-3 rounded-lg aseel-bg-panel dark:aseel-bg-panel/30 aseel-text-state dark:aseel-text-soft text-sm border aseel-border-soft dark:aseel-border-soft">
            {error}
          </div>
        )}
        {success && (
          <div className="p-3 rounded-lg aseel-bg-panel dark:aseel-bg-panel/30 aseel-text-ink dark:aseel-text-soft text-sm border aseel-border-soft dark:aseel-border-soft">
            {success}
          </div>
        )}

        {/* نوع الدفع */}
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium aseel-text-ink dark:aseel-text-soft mb-1.5">
              حالة الدفع
            </label>
            {/* «مدفوعة» بدل قائمة آجل/نقدي — مربع اختيار: مؤشَّر = مدفوعة من
                صندوق/بنك، فارغ = على ذمم المورد. القيم الخادمية كما هي. */}
            <label className="flex items-center gap-2 h-11 aseel-text-ink dark:text-white cursor-pointer select-none">
              <input
                type="checkbox"
                className="w-4 h-4 accent-emerald-600"
                checked={paymentType === "cash"}
                onChange={(e) => setPaymentType((e.target.checked ? "cash" : "credit") as PaymentType)}
                disabled={disableEdit}
              />
              مدفوعة
            </label>
            <p className="text-xs aseel-text-soft dark:aseel-text-soft mt-1">
              {paymentType === "credit"
                ? "الدائن = حساب ذمم المورد المربوط."
                : "الدائن = الصندوق/البنك المختار أدناه."}
            </p>
          </div>
          {paymentType === "cash" && (
            <div>
              <label className="block text-sm font-medium aseel-text-ink dark:aseel-text-soft mb-1.5">
                حساب الصندوق / البنك *
              </label>
              <select
                value={cashAccountId ?? ""}
                onChange={(e) =>
                  setCashAccountId(e.target.value ? Number(e.target.value) : null)
                }
                disabled={disableEdit}
                className="w-full h-11 px-3 border aseel-border-soft dark:aseel-border-soft rounded-lg aseel-bg-field dark:aseel-bg-panel aseel-text-ink dark:text-white disabled:opacity-60"
              >
                <option value="">— اختر حساب —</option>
                {cashAccountOptions.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.code} — {a.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* جدول الأصناف - توجيه حسابات الأسطر */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold aseel-text-ink dark:aseel-text-soft">
              توجيه حسابات بنود الفاتورة
            </h4>
          </div>
          <div className="overflow-x-auto rounded-lg border aseel-border-soft dark:aseel-border-soft">
            <table className="w-full text-sm">
              <thead className="aseel-bg-panel dark:aseel-bg-panel aseel-text-soft dark:aseel-text-soft text-xs">
                <tr>
                  <th className="px-3 py-2 text-right font-medium">الصنف</th>
                  <th className="px-3 py-2 text-right font-medium">المبلغ</th>
                  <th className="px-3 py-2 text-right font-medium">حساب المصروف (تجاوز)</th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-3 py-6 text-center aseel-text-soft">
                      لا توجد أصناف
                    </td>
                  </tr>
                )}
                {items.map((item, idx) => (
                  <tr key={item.id ?? `it-${idx}`} className="border-t aseel-border-soft dark:aseel-border-soft">
                    <td className="px-3 py-2">{item.name}</td>
                    <td className="px-3 py-2">{formatMoney(item.total_price)}</td>
                    <td className="px-3 py-2">
                      <select
                        value={item.expense_account || ""}
                        onChange={(e) => updateItemAccount(idx, e.target.value ? Number(e.target.value) : null)}
                        disabled={disableEdit}
                        className="w-full h-9 px-2 border aseel-border-soft dark:aseel-border-soft rounded aseel-bg-field dark:aseel-bg-panel text-xs"
                      >
                        <option value="">— حساب المخزون الافتراضي —</option>
                        {expenseAccountOptions.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.code} — {a.name}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* جدول الرسوم */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold aseel-text-ink dark:aseel-text-soft">
              الرسوم الإضافية (شحن، تخليص، جمارك، …)
            </h4>
            {!disableEdit && (
              <button
                onClick={addFee}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded-lg"
              >
                <Plus className="w-4 h-4" />
                إضافة رسم
              </button>
            )}
          </div>
          <div className="overflow-x-auto rounded-lg border aseel-border-soft dark:aseel-border-soft">
            <table className="w-full text-sm">
              <thead className="aseel-bg-panel dark:aseel-bg-panel aseel-text-soft dark:aseel-text-soft text-xs">
                <tr>
                  <th className="px-3 py-2 text-right font-medium">الوصف</th>
                  <th className="px-3 py-2 text-right font-medium">الحساب المحاسبي</th>
                  <th className="px-3 py-2 text-right font-medium">المبلغ</th>
                  <th className="px-3 py-2 text-center font-medium">رسملة على المخزون</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {fees.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-3 py-6 text-center aseel-text-soft"
                    >
                      لا توجد رسوم — اضغط "إضافة رسم" لإضافة رسم شحن/تخليص/…
                    </td>
                  </tr>
                )}
                {fees.map((fee, idx) => (
                  <tr
                    key={fee.id ?? `new-${idx}`}
                    className="border-t aseel-border-soft dark:aseel-border-soft"
                  >
                    <td className="px-3 py-2">
                      <input
                        type="text"
                        value={fee.description}
                        onChange={(e) =>
                          updateFee(idx, { description: e.target.value })
                        }
                        disabled={disableEdit}
                        placeholder="مثلاً: رسوم تخليص"
                        className="w-full h-9 px-2 border aseel-border-soft dark:aseel-border-soft rounded aseel-bg-field dark:aseel-bg-panel"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <select
                        value={fee.expense_account || ""}
                        onChange={(e) =>
                          updateFee(idx, {
                            expense_account: Number(e.target.value),
                          })
                        }
                        disabled={disableEdit}
                        className="w-full h-9 px-2 border aseel-border-soft dark:aseel-border-soft rounded aseel-bg-field dark:aseel-bg-panel text-xs"
                      >
                        <option value="">— اختر —</option>
                        {expenseAccountOptions.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.code} — {a.name}{" "}
                            {a.account_type &&
                              `(${ACCOUNT_TYPE_LABELS[a.account_type] || a.account_type})`}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2 w-32">
                      <input
                        type="number"
                        step="0.01"
                        min={0}
                        value={fee.calculation_type === "percentage" ? fee.amount : (fee.calculation_value ?? fee.amount)}
                        onChange={(e) =>
                          updateFee(idx, {
                            amount: Number(e.target.value) || 0,
                            calculation_value: Number(e.target.value) || 0,
                          })
                        }
                        disabled={disableEdit || fee.calculation_type === "percentage"}
                        className="w-full h-9 px-2 border aseel-border-soft dark:aseel-border-soft rounded aseel-bg-field dark:aseel-bg-panel text-right"
                      />
                    </td>
                    <td className="px-3 py-2 text-center">
                      <input
                        type="checkbox"
                        checked={!!fee.capitalize_to_inventory}
                        onChange={(e) =>
                          updateFee(idx, {
                            capitalize_to_inventory: e.target.checked,
                          })
                        }
                        disabled={disableEdit}
                        title="رسملة على المخزون بدل تسجيله كمصروف"
                      />
                    </td>
                    <td className="px-3 py-2 w-10">
                      {!disableEdit && (
                        <button
                          onClick={() => removeFee(idx)}
                          className="p-1.5 aseel-text-state hover:aseel-bg-panel dark:hover:aseel-bg-panel/30 rounded"
                          title="حذف"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* معاينة القيد */}
        {preview && (
          <div className="rounded-lg border aseel-border-soft dark:aseel-border-soft aseel-bg-panel dark:aseel-bg-panel/50 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 aseel-bg-panel dark:aseel-bg-panel text-xs font-semibold aseel-text-ink dark:aseel-text-soft">
              <span>معاينة القيد المحاسبي</span>
              <span
                className={
                  preview.isBalanced
                    ? "aseel-text-soft dark:aseel-text-soft"
                    : "aseel-text-state dark:aseel-text-soft"
                }
              >
                {preview.isBalanced ? "✓ متوازن" : "✗ غير متوازن"}
              </span>
            </div>
            <table className="w-full text-sm">
              <thead className="aseel-text-soft dark:aseel-text-soft text-xs">
                <tr className="border-b aseel-border-soft dark:aseel-border-soft">
                  <th className="px-4 py-2 text-right font-medium">الحساب</th>
                  <th className="px-4 py-2 text-right font-medium w-32">مدين</th>
                  <th className="px-4 py-2 text-right font-medium w-32">دائن</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {preview.lines.map((l, i) => (
                  <tr key={i}>
                    <td className="px-4 py-2 aseel-text-ink dark:aseel-text-soft">
                      {l.account}
                      {l.note && (
                        <span className="text-xs aseel-text-soft block">
                          {l.note}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right font-mono">
                      {l.debit > 0 ? formatMoney(l.debit) : "—"}
                    </td>
                    <td className="px-4 py-2 text-right font-mono">
                      {l.credit > 0 ? formatMoney(l.credit) : "—"}
                    </td>
                  </tr>
                ))}
                <tr className="aseel-bg-panel dark:aseel-bg-panel font-bold">
                  <td className="px-4 py-2 text-right">المجموع</td>
                  <td className="px-4 py-2 text-right font-mono">
                    {formatMoney(preview.totalDebit)}
                  </td>
                  <td className="px-4 py-2 text-right font-mono">
                    {formatMoney(preview.totalCredit)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {/* أزرار الإجراءات */}
        {!isPosted && !readOnly && (
          <div className="flex items-center justify-end gap-3 pt-2 border-t aseel-border-soft dark:aseel-border-soft">
            <button
              onClick={saveAccountingFields}
              disabled={saving}
              className="px-4 py-2 aseel-text-ink dark:aseel-text-soft aseel-bg-panel dark:aseel-bg-panel hover:aseel-bg-grid-head dark:hover:aseel-bg-panel rounded-lg disabled:opacity-50"
            >
              {saving ? "جارٍ الحفظ…" : "حفظ الإعدادات"}
            </button>
            <button
              onClick={post}
              disabled={posting || !preview?.isBalanced}
              className="flex items-center gap-2 px-5 py-2 aseel-bg-panel hover:aseel-bg-panel disabled:aseel-bg-panel disabled:cursor-not-allowed text-white rounded-lg font-medium"
              title={
                !preview?.isBalanced
                  ? "القيد غير متوازن — لا يمكن الترحيل"
                  : "ترحيل القيد إلى دفتر اليومية"
              }
            >
              {posting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
              ترحيل للمحاسبة
            </button>
          </div>
        )}

        {/* مستند مرحَّل: تحذير + تراجع عن الترحيل */}
        {isPosted && !readOnly && (
          <div className="flex items-center justify-between gap-3 pt-2 border-t aseel-border-soft dark:aseel-border-soft">
            <p className="text-sm aseel-text-soft">
              هذا المستند مرحَّل. يجب التراجع عن الترحيل قبل تعديله أو حذفه.
            </p>
            <button
              onClick={unpost}
              disabled={posting}
              className="flex items-center gap-2 px-5 py-2 rounded-lg font-medium border aseel-border-soft aseel-text-ink hover:aseel-bg-grid-head disabled:opacity-50 disabled:cursor-not-allowed"
              title="حذف قيود الفاتورة وإرجاعها مسودة"
            >
              {posting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Undo2 className="w-4 h-4" />
              )}
              تراجع عن الترحيل
            </button>
          </div>
        )}

        {/* وصل دفع للمورد (Feature 2): سند صرف مستقل يُفرّغ ذمم المورد للصندوق */}
        {isPosted && (
          <div className="pt-3 mt-1 border-t aseel-border-soft dark:aseel-border-soft space-y-2">
            <div className="flex items-center gap-2">
              <Receipt className="w-4 h-4 aseel-text-soft" />
              <h4 className="font-medium aseel-text-ink">وصل دفع للمورد</h4>
              {invoice.remaining_balance != null && (
                <span className="text-sm aseel-text-soft">
                  المتبقي: {invoice.remaining_balance}
                </span>
              )}
            </div>
            <p className="text-xs aseel-text-soft">
              قيد مستقل: مدين «ذمم المورد» / دائن «الصندوق/البنك» — لا يولّده ترحيل الفاتورة.
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-sm">
                <span className="aseel-text-soft">المبلغ</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={payAmount}
                  onChange={(e) => setPayAmount(e.target.value)}
                  className="px-3 py-2 rounded-lg border aseel-border-soft aseel-bg-panel w-36"
                  placeholder="0.00"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="aseel-text-soft">حساب الصندوق/البنك</span>
                <select
                  value={payAccountId ?? ""}
                  onChange={(e) => setPayAccountId(e.target.value ? Number(e.target.value) : null)}
                  className="px-3 py-2 rounded-lg border aseel-border-soft aseel-bg-panel min-w-[12rem]"
                >
                  <option value="">— اختر حساب —</option>
                  {cashAccountOptions.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.code} — {a.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                onClick={addSupplierPayment}
                disabled={paySaving}
                className="flex items-center gap-2 px-5 py-2 rounded-lg font-medium aseel-bg-accent text-white disabled:opacity-50 disabled:cursor-not-allowed"
                title="تسجيل وصل دفع وترحيله"
              >
                {paySaving ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Banknote className="w-4 h-4" />
                )}
                تسجيل وصل الدفع
              </button>
              {/* T-ONACC: تسديد من رصيد المورد «على الحساب» (سندات صرف غير موزَّعة). */}
              {Number(invoice.remaining_balance ?? 0) > 0.009 && (
                <button
                  onClick={() => setShowSettleModal(true)}
                  className="flex items-center gap-2 px-5 py-2 rounded-lg font-medium border aseel-border-soft"
                  title="تسديد الفاتورة من رصيدنا عند المورد"
                >
                  <Receipt className="w-4 h-4" />
                  تسديد من الرصيد
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* T-ONACC: تسديد فاتورة الشراء من رصيدنا عند المورد (سند صرف غير موزَّع). */}
      {showSettleModal && invoice && (
        <SettleFromOnAccountModal
          kind="supplier"
          partnerId={invoice.partner}
          partnerLabel={invoice.partner_name || ""}
          invoiceId={invoiceId}
          invoiceLabel={`فاتورة ${invoice.invoice_number || invoiceId}`}
          remaining={Number(invoice.remaining_balance ?? 0)}
          onClose={() => setShowSettleModal(false)}
          onSettled={async () => {
            setShowSettleModal(false);
            setSuccess("✅ تم تسديد الفاتورة من الرصيد على حساب المورد.");
            await reload();
          }}
        />
      )}

      {showReceive && (
        <ReceiveGoodsModal
          invoice={invoice}
          onClose={() => setShowReceive(false)}
          onReceived={async () => {
            setShowReceive(false);
            setSuccess("✅ تم استلام البضاعة وعكسها على المستودع.");
            await reload();
          }}
        />
      )}
    </div>
  );
};

export default PurchaseInvoiceAccountingPanel;
