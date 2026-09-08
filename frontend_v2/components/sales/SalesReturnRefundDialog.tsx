/**
 * issue #167 م٤ — حوار اختيار ردّ الدفعة عند ترحيل مرتجع البيع.
 *
 * يُفتح فقط حين يكون `auto_refund_on_sales_return` مطفأً على الشركة (القرار
 * التلقائي مُسبَق ولا يُسأل عنه كل ترحيل). الشيك ورقةٌ كاملة أو لا شيء — بلا
 * تجزئة — والنقد محدودٌ بسقف النقد الذي يحسبه الخادم وحده.
 */
import React, { useMemo, useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import type {
  SalesReturnRefundChoice,
  SalesReturnRefundOptions,
  SalesReturnRefundSummary,
} from "../../services/salesApi";
import { formatMoney } from "../../utils/formatNumber";
import { formatDateValue } from "../../utils/formatDate";

interface Props {
  options: SalesReturnRefundOptions;
  onConfirm: (choice: SalesReturnRefundChoice) => void;
  onCancel: () => void;
}

export const SalesReturnRefundDialog: React.FC<Props> = ({ options, onConfirm, onCancel }) => {
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [cashAmount, setCashAmount] = useState<string>("0");

  const cashCap = Number(options.cash_cap) || 0;
  const selectedTotal = useMemo(
    () =>
      options.paper_cheques
        .filter((c) => selectedIds.has(c.id))
        .reduce((sum, c) => sum + (Number(c.amount) || 0), 0),
    [options.paper_cheques, selectedIds],
  );

  const toggleCheque = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const submitSelection = () => {
    const clampedCash = Math.max(0, Math.min(Number(cashAmount) || 0, cashCap));
    onConfirm({
      cheque_ids: Array.from(selectedIds),
      cash_amount: clampedCash.toFixed(2),
    });
  };

  const refundNothing = () => {
    onConfirm({ cheque_ids: [], cash_amount: "0" });
  };

  return (
    <div
      dir="rtl"
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-[1000] p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-lg rounded-2xl bg-[var(--color-surface)] shadow-2xl border border-[var(--color-border)] p-6"
        onClick={(e) => e.stopPropagation()}
        role="alertdialog"
        aria-modal="true"
      >
        <div className="flex items-start gap-3 mb-4">
          <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30">
            <AlertTriangle className="w-5 h-5 text-blue-600 dark:text-blue-400" />
          </div>
          <h3 className="text-lg font-bold flex-1 dark:text-white">ردّ دفعة مرتجع البيع</h3>
          <button
            onClick={onCancel}
            className="p-1 rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)]"
            aria-label="إغلاق"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className="text-sm text-[var(--color-text-muted)] mb-4">
          إجمالي المرتجع {formatMoney(options.return_total)}. اختر ما يُردّ للزبون الآن.
        </p>

        <div className="mb-4">
          <label className="block text-sm font-semibold mb-1 dark:text-white">
            ما وصل نقداً — الحدّ الأقصى {formatMoney(options.cash_cap)}
          </label>
          <input
            type="number"
            min={0}
            max={cashCap}
            step="0.01"
            value={cashAmount}
            onChange={(e) => setCashAmount(e.target.value)}
            className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm dark:text-white"
          />
        </div>

        {options.paper_cheques.length > 0 && (
          <div className="mb-4">
            <div className="text-sm font-semibold mb-2 dark:text-white">
              الشيكاتُ في المحفظة — كاملةً أو لا شيء
            </div>
            <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
              {options.paper_cheques.map((c) => (
                <label
                  key={c.id}
                  className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm cursor-pointer hover:bg-[var(--color-surface-2)]"
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.has(c.id)}
                    onChange={() => toggleCheque(c.id)}
                  />
                  <span className="flex-1 dark:text-white">{c.cheque_number}</span>
                  <span className="text-[var(--color-text-muted)]">
                    استحقاق {formatDateValue(c.due_date)}
                  </span>
                  <span className="font-semibold dark:text-white">{formatMoney(c.amount)}</span>
                </label>
              ))}
            </div>
            {selectedIds.size > 0 && (
              <div className="text-xs text-[var(--color-text-muted)] mt-1">
                مجموع الشيكات المحدَّدة: {formatMoney(selectedTotal)}
              </div>
            )}
          </div>
        )}

        {Number(options.bank_uncollected_total) > 0 && (
          <div className="mb-4 text-sm rounded-lg bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-300 px-3 py-2">
            ما هو عند البنك فلا يُردّ الآن: {formatMoney(options.bank_uncollected_total)}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={refundNothing}
            className="px-4 py-2 text-sm font-semibold rounded-lg border border-[var(--color-border)] text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
          >
            لا شيء الآن
          </button>
          <button
            type="button"
            onClick={submitSelection}
            className="px-4 py-2 text-sm font-bold text-white rounded-lg bg-blue-600 hover:bg-blue-700"
          >
            ردّ المحدَّد
          </button>
        </div>
      </div>
    </div>
  );
};

/**
 * رسالة «ما حدث فعلاً» بعد الترحيل — تُبنى من `refund_summary` وحده، بلا
 * إعادة حساب. غيابه أو صفريّة مبالغه يعني ألا رسالة تُعرض (لا ادّعاء ردٍّ لم يقع).
 */
export function describeRefundOutcome(
  summary: SalesReturnRefundSummary | null | undefined,
): string | null {
  if (!summary) return null;
  const paper = Number(summary.paper_amount) || 0;
  const cash = Number(summary.cash_amount) || 0;
  const creditOnly = Number(summary.credit_balance) || 0;
  // لا ردَّ وقع ولا رصيدَ باقٍ ⇒ لا رسالة (لا يُدَّعى ما لم يحدث).
  if (paper <= 0 && cash <= 0 && creditOnly <= 0) return null;
  // لا ردَّ وقع ولكن بقي رصيدٌ ⇒ **يُقال صراحةً**. ابتلاعُه صامتاً يترك المستخدم
  // لا يعرف أنّه ما زال مديناً للزبون، وهو ما تمنعه المواصفة نصّاً.
  if (paper <= 0 && cash <= 0) {
    return `لم يُردّ شيءٌ الآن — بقي ${formatMoney(creditOnly)} رصيداً دائناً للزبون.`;
  }

  const parts: string[] = [];
  if (paper > 0) {
    const numbers = summary.cheque_numbers?.length
      ? ` (${summary.cheque_numbers.join("، ")})`
      : "";
    parts.push(`رُدّ ${formatMoney(paper)} ورقاً${numbers}`);
  }
  if (cash > 0) {
    parts.push(`رُدّ ${formatMoney(cash)} نقداً`);
  }
  const credit = Number(summary.credit_balance) || 0;
  if (credit > 0) {
    parts.push(`وبقي ${formatMoney(credit)} رصيداً دائناً للزبون`);
  }
  return parts.join("، ") + ".";
}
