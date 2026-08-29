import React, { useEffect, useMemo, useState } from "react";
import { X, Calculator } from "lucide-react";
import { accountingApi, type CashBoxLedgerLink } from "../../../services/accountingApi";
import { useToast } from "../../../contexts/ToastContext";
import { humanizeThrown } from "../../../utils/drfError";
import { formatMoney } from "../../../utils/formatNumber";

interface CashCountModalProps {
  isOpen: boolean;
  box: CashBoxLedgerLink | null;
  onClose: () => void;
  onCounted?: () => void;
}

/** فئات العملة الشائعة — العدّ يجمعها، والمجموع وحده هو المعتمد. */
const DENOMINATIONS: Record<string, number[]> = {
  ILS: [200, 100, 50, 20, 10, 5, 2, 1],
  USD: [100, 50, 20, 10, 5, 1],
  JOD: [50, 20, 10, 5, 1],
};

/** T-CASHBOX M6 — جرد الصندوق: عدّ الفعلي ومقارنته بالدفتري (نمط Odoo/ERPNext).
 *
 * حاسبة الفئات تجمع للعادّ ولا تحكم: `counted_total` هو المعتمد، والفئات
 * تُحفظ للمراجعة. والفرق يُرحّله الخادم إلى «زيادة الصندوق» (4202) أو «عجز
 * الصندوق» (5206) — لا تسويةَ صامتة على الرصيد.
 */
export const CashCountModal: React.FC<CashCountModalProps> = ({
  isOpen,
  box,
  onClose,
  onCounted,
}) => {
  const toast = useToast();
  const [counts, setCounts] = useState<Record<string, string>>({});
  const [manualTotal, setManualTotal] = useState("");
  const [date, setDate] = useState(new Date().toISOString().split("T")[0]);
  const [notes, setNotes] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const currency = box?.currency_code || "ILS";
  const denominations = DENOMINATIONS[currency] ?? DENOMINATIONS.ILS;
  const bookBalance = box?.balance != null ? Number(box.balance) : 0;

  const denomTotal = useMemo(
    () =>
      denominations.reduce(
        (sum, face) => sum + face * (Number(counts[String(face)]) || 0),
        0,
      ),
    [counts, denominations],
  );
  // العدّ بالفئات يقود المجموع؛ فإن لم يُدخل العادّ فئةً واحدة قَبِلنا رقماً يدوياً.
  const countedTotal = denomTotal > 0 ? denomTotal : Number(manualTotal) || 0;
  const difference = countedTotal - bookBalance;

  useEffect(() => {
    if (!isOpen) return;
    setCounts({});
    setManualTotal("");
    setNotes("");
    setDate(new Date().toISOString().split("T")[0]);
    setFormError(null);
  }, [isOpen, box?.id]);

  if (!isOpen || !box) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (countedTotal < 0) return;
    setIsLoading(true);
    setFormError(null);
    try {
      const created = await accountingApi.createCashCount({
        cash_box: box.id,
        count_date: date,
        counted_total: countedTotal,
        denominations: denomTotal > 0
          ? Object.fromEntries(
              denominations
                .filter((f) => Number(counts[String(f)]) > 0)
                .map((f) => [String(f), Number(counts[String(f)])]),
            )
          : undefined,
        notes: notes.trim() || undefined,
      });
      await accountingApi.postCashCount(created.id);
      toast(
        difference === 0
          ? "الجرد مطابق — لا فرق."
          : `تم ترحيل فرق الجرد (${formatMoney(difference)} ${currency}).`,
        "success",
      );
      onCounted?.();
      onClose();
    } catch (error) {
      setFormError(humanizeThrown(error, "تعذّر ترحيل الجرد"));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-4">
      <div className="bg-[var(--color-surface)] rounded-lg p-6 w-full max-w-lg max-h-full overflow-y-auto">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold dark:text-white flex items-center">
            <Calculator className="w-5 h-5 ml-2 text-purple-600" />
            جرد {box.name}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {formError && (
          <div className="mb-3 rounded-md border border-red-300 bg-red-50 p-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
            {formError}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-[var(--color-text)] mb-2">
              عدّ الفئات
            </label>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {denominations.map((face) => (
                <label key={face} className="flex flex-col text-xs">
                  <span className="mb-1 text-[var(--color-text-muted)]">{face}</span>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={counts[String(face)] ?? ""}
                    onChange={(e) =>
                      setCounts((prev) => ({ ...prev, [String(face)]: e.target.value }))
                    }
                    className="w-full rounded-md border p-2 text-sm dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                    placeholder="0"
                  />
                </label>
              ))}
            </div>
          </div>

          {denomTotal === 0 && (
            <div>
              <label className="block text-sm font-medium text-[var(--color-text)] mb-1">
                أو أدخل المعدود إجمالاً ({currency})
              </label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={manualTotal}
                onChange={(e) => setManualTotal(e.target.value)}
                className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                placeholder="0.00"
              />
            </div>
          )}

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-sm space-y-1">
            <div className="flex justify-between">
              <span className="text-[var(--color-text-muted)]">الرصيد الدفتري</span>
              <span className="font-bold tabular-nums">
                {formatMoney(bookBalance)} {currency}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--color-text-muted)]">المعدود</span>
              <span className="font-bold tabular-nums">
                {formatMoney(countedTotal)} {currency}
              </span>
            </div>
            <div className="flex justify-between border-t border-[var(--color-border)] pt-1">
              <span className="text-[var(--color-text-muted)]">الفرق</span>
              <span
                className={`font-bold tabular-nums ${
                  difference === 0
                    ? "text-[var(--color-text)]"
                    : difference > 0
                      ? "text-green-700 dark:text-green-400"
                      : "text-red-700 dark:text-red-400"
                }`}
              >
                {formatMoney(difference)} {currency}
              </span>
            </div>
            <p className="pt-1 text-xs text-[var(--color-text-muted)]">
              {difference === 0
                ? "مطابق — لن يُنشأ قيد."
                : difference > 0
                  ? "زيادة — تُرحَّل إلى «زيادة الصندوق» (4202)."
                  : "عجز — يُرحَّل إلى «عجز الصندوق» (5206)."}
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1">
              تاريخ الجرد
            </label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1">
              ملاحظات (اختياري)
            </label>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              placeholder="من قام بالعدّ، ملاحظات على الفرق..."
            />
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="button"
              onClick={onClose}
              className="mr-2 px-4 py-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)] rounded-md"
            >
              إلغاء
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:opacity-50"
            >
              {isLoading ? "جاري الترحيل..." : "ترحيل الجرد"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
