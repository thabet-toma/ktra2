import React, { useEffect, useMemo, useState } from "react";
import { X, ArrowLeftRight } from "lucide-react";
import { accountingApi, type CashBoxLedgerLink } from "../../../services/accountingApi";
import { useToast } from "../../../contexts/ToastContext";
import { humanizeThrown } from "../../../utils/drfError";
import { formatMoney } from "../../../utils/formatNumber";

interface CashTransferModalProps {
  isOpen: boolean;
  boxes: CashBoxLedgerLink[];
  /** الصندوق المنطلق منه، إن فُتحت النافذة من بطاقته. */
  fromBox?: CashBoxLedgerLink | null;
  onClose: () => void;
  onTransferred?: () => void;
}

/** T-CASHBOX M6 — تحويل بين الخزائن: مستندٌ واحد بقيدٍ واحد.
 *
 * قبله كان النقل بين صندوقين «إيداعاً هنا وسحباً هناك» لا يربطهما شيء، فلا
 * يُعرف أنهما حركة واحدة ولا يُعكسان معاً. والتحويل إلى صندوق عملة أجنبية
 * يمرّ خادمياً على محرّك FIFO فتُحفظ طبقة بسعرها — لا قيدٌ مباشر يفسد التكلفة.
 */
export const CashTransferModal: React.FC<CashTransferModalProps> = ({
  isOpen,
  boxes,
  fromBox,
  onClose,
  onTransferred,
}) => {
  const toast = useToast();
  const [fromId, setFromId] = useState<number | "">("");
  const [toId, setToId] = useState<number | "">("");
  const [amount, setAmount] = useState("");
  const [rate, setRate] = useState("");
  const [date, setDate] = useState(new Date().toISOString().split("T")[0]);
  const [notes, setNotes] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const live = useMemo(() => boxes.filter((b) => b.is_active !== false), [boxes]);
  const from = live.find((b) => b.id === fromId) ?? null;
  const to = live.find((b) => b.id === toId) ?? null;
  const crossCurrency =
    !!from && !!to && (from.currency_code || "") !== (to.currency_code || "");

  useEffect(() => {
    if (!isOpen) return;
    setFromId(fromBox?.id ?? "");
    setToId("");
    setAmount("");
    setRate("");
    setNotes("");
    setDate(new Date().toISOString().split("T")[0]);
    setFormError(null);
  }, [isOpen, fromBox?.id]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fromId || !toId || Number(amount) <= 0) return;
    if (fromId === toId) {
      setFormError("لا يمكن التحويل من الخزينة إلى نفسها.");
      return;
    }
    if (crossCurrency && Number(rate) <= 0) {
      setFormError("العملتان مختلفتان — أدخل سعر الصرف.");
      return;
    }
    setIsLoading(true);
    setFormError(null);
    try {
      await accountingApi.createCashTransfer({
        transfer_date: date,
        amount: Number(amount),
        from_cash_box: Number(fromId),
        to_cash_box: Number(toId),
        rate: crossCurrency ? Number(rate) : 1,
        notes: notes.trim() || undefined,
      });
      toast("تم التحويل وقيده في المحاسبة.", "success");
      onTransferred?.();
      onClose();
    } catch (error) {
      setFormError(humanizeThrown(error, "تعذّر تنفيذ التحويل"));
    } finally {
      setIsLoading(false);
    }
  };

  const boxOption = (b: CashBoxLedgerLink) => (
    <option key={b.id} value={b.id}>
      {b.name} ({b.currency_code})
      {b.balance != null ? ` — ${formatMoney(Number(b.balance))}` : ""}
    </option>
  );

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]">
      <div className="bg-[var(--color-surface)] rounded-lg p-6 w-full max-w-md">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold dark:text-white flex items-center">
            <ArrowLeftRight className="w-5 h-5 ml-2 text-blue-600" />
            تحويل بين الخزائن
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
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1">
              من صندوق
            </label>
            <select
              value={fromId}
              onChange={(e) => setFromId(e.target.value ? Number(e.target.value) : "")}
              className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              required
            >
              <option value="">— اختر —</option>
              {live.map(boxOption)}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1">
              إلى صندوق
            </label>
            <select
              value={toId}
              onChange={(e) => setToId(e.target.value ? Number(e.target.value) : "")}
              className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              required
            >
              <option value="">— اختر —</option>
              {live.filter((b) => b.id !== fromId).map(boxOption)}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1">
              المبلغ {from ? `(${from.currency_code})` : ""}
            </label>
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white font-bold text-lg"
              placeholder="0.00"
              required
            />
          </div>

          {crossCurrency && (
            <div>
              <label className="block text-sm font-medium text-[var(--color-text)] mb-1">
                سعر الصرف ({from?.currency_code} لكل {to?.currency_code})
              </label>
              <input
                type="number"
                min="0.000001"
                step="0.000001"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
                className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                placeholder="مثال: 3.6"
                required
              />
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                الوارد إلى {to?.name}:{" "}
                {Number(rate) > 0 && Number(amount) > 0
                  ? `${formatMoney(Number(amount) / Number(rate))} ${to?.currency_code}`
                  : "—"}{" "}
                — تُحفظ طبقة بسعرها لحساب التكلفة لاحقاً (FIFO).
              </p>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1">
              التاريخ
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
              placeholder="سبب التحويل"
            />
          </div>

          <div className="flex justify-end pt-4">
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
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {isLoading ? "جاري التحويل..." : "تأكيد التحويل"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
