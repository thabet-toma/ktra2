/**
 * لوحة محاسبة فاتورة الشراء — فصلاً عن نموذج الفاتورة الرئيسي.
 *
 * الغرض: ضمان ترحيل صحيح للمحاسبة مع:
 *  - اختيار نوع الدفع (آجل/نقدي) + حساب الصندوق عند النقدي
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
} from "lucide-react";
import { purchaseInvoiceApi } from "@/services/purchaseInvoiceApi";
import { accountingApi } from "@/services/accountingApi";
import type {
  PurchaseInvoiceDto,
  PurchaseInvoiceFeeDto,
} from "@/types/purchaseInvoice";

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
}) => {
  const [loading, setLoading] = useState(true);
  const [invoice, setInvoice] = useState<PurchaseInvoiceDto | null>(null);
  const [accounts, setAccounts] = useState<AccountDto[]>([]);
  const [fees, setFees] = useState<PurchaseInvoiceFeeDto[]>([]);
  const [paymentType, setPaymentType] = useState<PaymentType>("credit");
  const [cashAccountId, setCashAccountId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

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
          expense_account: f.expense_account,
          capitalize_to_inventory: !!f.capitalize_to_inventory,
          is_taxable: !!f.is_taxable,
        })),
      };
      const updated = await purchaseInvoiceApi.update(invoiceId, payload);
      setInvoice(updated);
      setFees(Array.isArray(updated.fees) ? [...updated.fees] : []);
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

    if (inventoryDebit > 0) {
      lines.push({
        account: "مخزون (1104)",
        debit: inventoryDebit,
        credit: 0,
        note:
          capitalizedFees > 0
            ? `صافي البضاعة + رسوم مرسملة (${capitalizedFees.toFixed(2)})`
            : "صافي البضاعة",
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
    const creditLabel =
      paymentType === "cash"
        ? `صندوق/بنك (${
            accounts.find((a) => a.id === cashAccountId)?.code || "—"
          })`
        : `ذمم مورد (${invoice.partner_name || "—"})`;
    lines.push({ account: creditLabel, debit: 0, credit: creditTotal });

    const totalDebit = lines.reduce((s, l) => s + l.debit, 0);
    const totalCredit = lines.reduce((s, l) => s + l.credit, 0);
    const isBalanced = Math.abs(totalDebit - totalCredit) < 0.015;

    return { lines, totalDebit, totalCredit, isBalanced };
  }, [invoice, fees, paymentType, cashAccountId, accounts]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 justify-center py-12 text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin" />
        <span>جارٍ تحميل البيانات المحاسبية…</span>
      </div>
    );
  }
  if (!invoice) return null;

  const isPosted = !!invoice.is_posted;
  const disableEdit = isPosted;

  return (
    <div
      dir="rtl"
      className="mt-6 rounded-2xl border-2 border-indigo-200 dark:border-indigo-900 bg-white dark:bg-gray-900 shadow-sm overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-indigo-100 dark:border-indigo-900/60 bg-gradient-to-l from-indigo-50 to-white dark:from-indigo-900/30 dark:to-gray-900">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-600 text-white rounded-xl">
            <Calculator className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-white">
              المحاسبة والترحيل
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              الرسوم + نوع الدفع + معاينة القيد
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={reload}
            className="p-2 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
            title="تحديث"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          {isPosted ? (
            <span className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 rounded-full text-sm font-medium border border-emerald-200 dark:border-emerald-800">
              <CheckCircle2 className="w-4 h-4" />
              مرحّلة (قيد #{invoice.journal_id_display})
            </span>
          ) : (
            <span className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-50 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 rounded-full text-sm font-medium border border-amber-200 dark:border-amber-800">
              <AlertTriangle className="w-4 h-4" />
              غير مرحّلة
            </span>
          )}
        </div>
      </div>

      <div className="p-6 space-y-6">
        {error && (
          <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 text-sm border border-red-200 dark:border-red-800">
            {error}
          </div>
        )}
        {success && (
          <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 text-sm border border-emerald-200 dark:border-emerald-800">
            {success}
          </div>
        )}

        {/* نوع الدفع */}
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              نوع الدفع
            </label>
            <select
              value={paymentType}
              onChange={(e) => setPaymentType(e.target.value as PaymentType)}
              disabled={disableEdit}
              className="w-full h-11 px-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white disabled:opacity-60"
            >
              <option value="credit">آجل — على ذمم المورد</option>
              <option value="cash">نقدي — من صندوق/بنك</option>
            </select>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {paymentType === "credit"
                ? "الدائن = حساب ذمم المورد المربوط."
                : "الدائن = الصندوق/البنك المختار أدناه."}
            </p>
          </div>
          {paymentType === "cash" && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                حساب الصندوق / البنك *
              </label>
              <select
                value={cashAccountId ?? ""}
                onChange={(e) =>
                  setCashAccountId(e.target.value ? Number(e.target.value) : null)
                }
                disabled={disableEdit}
                className="w-full h-11 px-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white disabled:opacity-60"
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

        {/* جدول الرسوم */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
              الرسوم الإضافية (شحن، تخليص، جمارك، …)
            </h4>
            {!disableEdit && (
              <button
                onClick={addFee}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg"
              >
                <Plus className="w-4 h-4" />
                إضافة رسم
              </button>
            )}
          </div>
          <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300 text-xs">
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
                      className="px-3 py-6 text-center text-gray-400"
                    >
                      لا توجد رسوم — اضغط "إضافة رسم" لإضافة رسم شحن/تخليص/…
                    </td>
                  </tr>
                )}
                {fees.map((fee, idx) => (
                  <tr
                    key={fee.id ?? `new-${idx}`}
                    className="border-t border-gray-200 dark:border-gray-700"
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
                        className="w-full h-9 px-2 border border-gray-200 dark:border-gray-600 rounded bg-white dark:bg-gray-800"
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
                        className="w-full h-9 px-2 border border-gray-200 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-xs"
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
                        value={fee.amount}
                        onChange={(e) =>
                          updateFee(idx, { amount: Number(e.target.value) || 0 })
                        }
                        disabled={disableEdit}
                        className="w-full h-9 px-2 border border-gray-200 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-right"
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
                          className="p-1.5 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 rounded"
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
          <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 bg-gray-100 dark:bg-gray-800 text-xs font-semibold text-gray-700 dark:text-gray-300">
              <span>معاينة القيد المحاسبي</span>
              <span
                className={
                  preview.isBalanced
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-red-600 dark:text-red-400"
                }
              >
                {preview.isBalanced ? "✓ متوازن" : "✗ غير متوازن"}
              </span>
            </div>
            <table className="w-full text-sm">
              <thead className="text-gray-600 dark:text-gray-400 text-xs">
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="px-4 py-2 text-right font-medium">الحساب</th>
                  <th className="px-4 py-2 text-right font-medium w-32">مدين</th>
                  <th className="px-4 py-2 text-right font-medium w-32">دائن</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {preview.lines.map((l, i) => (
                  <tr key={i}>
                    <td className="px-4 py-2 text-gray-800 dark:text-gray-200">
                      {l.account}
                      {l.note && (
                        <span className="text-xs text-gray-500 block">
                          {l.note}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right font-mono">
                      {l.debit > 0 ? l.debit.toFixed(2) : "—"}
                    </td>
                    <td className="px-4 py-2 text-right font-mono">
                      {l.credit > 0 ? l.credit.toFixed(2) : "—"}
                    </td>
                  </tr>
                ))}
                <tr className="bg-gray-100 dark:bg-gray-800 font-bold">
                  <td className="px-4 py-2 text-right">المجموع</td>
                  <td className="px-4 py-2 text-right font-mono">
                    {preview.totalDebit.toFixed(2)}
                  </td>
                  <td className="px-4 py-2 text-right font-mono">
                    {preview.totalCredit.toFixed(2)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {/* أزرار الإجراءات */}
        {!isPosted && (
          <div className="flex items-center justify-end gap-3 pt-2 border-t border-gray-200 dark:border-gray-700">
            <button
              onClick={saveAccountingFields}
              disabled={saving}
              className="px-4 py-2 text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg disabled:opacity-50"
            >
              {saving ? "جارٍ الحفظ…" : "حفظ الإعدادات"}
            </button>
            <button
              onClick={post}
              disabled={posting || !preview?.isBalanced}
              className="flex items-center gap-2 px-5 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-white rounded-lg font-medium"
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
      </div>
    </div>
  );
};

export default PurchaseInvoiceAccountingPanel;
