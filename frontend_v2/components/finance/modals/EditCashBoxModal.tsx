import React, { useEffect, useState } from "react";
import { X, Link2 } from "lucide-react";
import { cashBoxesService } from "../../../services/firestoreService";
import { accountingApi, type CashBoxLedgerLink } from "../../../services/accountingApi";
import { CashBox, Currency } from "../../../types";

interface EditCashBoxModalProps {
  isOpen: boolean;
  cashBox: CashBox | null;
  onClose: () => void;
  /** بعد ربط محاسبة أو إغلاق النافذة لتحديث شارات القائمة */
  onLedgersMaybeChanged?: () => void;
}

export const EditCashBoxModal: React.FC<EditCashBoxModalProps> = ({
  isOpen,
  cashBox,
  onClose,
  onLedgersMaybeChanged,
}) => {
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState<Currency>("USD");
  const [isLoading, setIsLoading] = useState(false);
  const [linkLoading, setLinkLoading] = useState(false);
  const [ledgerLink, setLedgerLink] = useState<CashBoxLedgerLink | null | undefined>(
    undefined
  );

  useEffect(() => {
    if (cashBox && isOpen) {
      setName(cashBox.name || "");
      setCurrency(cashBox.currency || "USD");
      setLedgerLink(undefined);
      let cancelled = false;
      accountingApi
        .getCashBoxLedgers()
        .then((rows) => {
          if (cancelled) return;
          const hit = rows.find((r) => String(r.external_id) === String(cashBox.id));
          setLedgerLink(hit ?? null);
        })
        .catch(() => {
          if (!cancelled) setLedgerLink(null);
        });
      return () => {
        cancelled = true;
      };
    }
  }, [cashBox, isOpen]);

  if (!isOpen || !cashBox) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setIsLoading(true);
    try {
      await cashBoxesService.updateCashBox(cashBox.id, {
        name: name.trim(),
        currency,
      });
      onLedgersMaybeChanged?.();
      onClose();
    } catch (error) {
      // console suppressed
      alert("حدث خطأ أثناء تعديل الصندوق");
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateGlAccount = async () => {
    if (!name.trim()) {
      alert("اكتب اسماً للصندوق أولاً — سيُستخدم كاسم الحساب في الشجرة.");
      return;
    }
    setLinkLoading(true);
    try {
      await accountingApi.registerCashBoxLedger({
        external_id: cashBox.id,
        name: name.trim(),
        currency_code: currency,
      });
      const rows = await accountingApi.getCashBoxLedgers();
      const hit = rows.find((r) => String(r.external_id) === String(cashBox.id));
      setLedgerLink(hit ?? null);
      onLedgersMaybeChanged?.();
      alert(
        "✅ تم إنشاء حساب في شجرة المحاسبة بنفس اسم الصندوق، وربطه بهذا الصندوق."
      );
    } catch (e) {
      const m = e instanceof Error ? e.message : String(e);
      alert("تعذّر إنشاء الحساب: " + m);
    } finally {
      setLinkLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-xl font-bold dark:text-white">تعديل الصندوق</h2>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              كل صندوق مرتبط بحساب نقدية في الشجرة بنفس الاسم؛ يُستخدم في قيود الدفع.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 dark:text-gray-400 shrink-0"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              اسم الصندوق
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              العملة
            </label>
            <select
              value={currency}
              onChange={(e) => setCurrency(e.target.value as Currency)}
              className="w-full p-2 border rounded-md dark:bg-gray-700 dark:border-gray-600 dark:text-white"
            >
              <option value="USD">USD</option>
              <option value="ILS">ILS</option>
              <option value="JOD">JOD</option>
            </select>
          </div>

          <div className="rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-900/40 p-3 text-sm">
            <p className="font-medium text-gray-800 dark:text-gray-200 mb-1">
              الربط بالمحاسبة
            </p>
            {ledgerLink === undefined ? (
              <p className="text-gray-500 dark:text-gray-400">جاري التحقق…</p>
            ) : ledgerLink ? (
              <p className="text-green-800 dark:text-green-200">
                مرتبط: حساب الشجرة{" "}
                <span className="font-mono font-semibold">
                  {ledgerLink.account_code}
                </span>{" "}
                — {ledgerLink.name}
              </p>
            ) : (
              <>
                <p className="text-slate-700 dark:text-slate-300 mb-2">
                  لا يوجد حساب في الشجرة لهذا الصندوق بعد.
                </p>
                <button
                  type="button"
                  disabled={linkLoading}
                  onClick={handleCreateGlAccount}
                  className="inline-flex items-center gap-2 rounded-md bg-[var(--color-primary)] px-3 py-2 text-xs font-medium text-white hover:bg-[var(--color-primary-hover)] disabled:opacity-50"
                >
                  <Link2 className="h-3.5 w-3.5" />
                  {linkLoading ? "جاري الإنشاء…" : "إنشاء حساب في الشجرة بنفس الاسم"}
                </button>
              </>
            )}
          </div>

          <p className="text-xs text-gray-500 dark:text-gray-400">
            الرصيد الحالي لا يُعدّل من هنا؛ يتغيّر من حركات الصندوق فقط.
          </p>

          <div className="flex justify-end pt-4 gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-md dark:text-gray-300 dark:hover:bg-gray-700"
            >
              إلغاء
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {isLoading ? "جاري الحفظ…" : "حفظ"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
