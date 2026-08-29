import React, { useEffect, useState } from "react";
import { X } from "lucide-react";
import { accountingApi, type CashBoxLedgerLink } from "../../../services/accountingApi";
import { CashBox, Currency } from "../../../types";
import { useToast } from "../../../contexts/ToastContext";
import { humanizeThrown } from "../../../utils/drfError";

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
  const toast = useToast();
  const [formError, setFormError] = useState<string | null>(null);
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

  /** T-CASHBOX M2: التعديل خادميّ — الاسم يزامن حساب الشجرة والمرآة معاً.
   *
   * كان يُكتب في المرآة وحدها، فيبقى اسم الحساب في الشجرة على القديم: اسمان
   * لصندوق واحد، وكشفٌ لا يطابق شجرةً.
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    if (!ledgerLink) {
      setFormError("هذا الصندوق بلا حساب في الشجرة — شغّل أمر backfill_cash_boxes.");
      return;
    }
    setIsLoading(true);
    setFormError(null);
    try {
      await accountingApi.updateCashBox(ledgerLink.id, {
        name: name.trim(),
        currency_code: currency,
      });
      toast("تم حفظ تعديل الصندوق، وتزامن اسم حسابه في الشجرة.", "success");
      onLedgersMaybeChanged?.();
      onClose();
    } catch (error) {
      // الفشل يبقي النافذة مفتوحة بمدخلاتها ويعرض السبب.
      setFormError(humanizeThrown(error, "تعذّر تعديل الصندوق"));
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleActive = async () => {
    if (!ledgerLink) return;
    setLinkLoading(true);
    setFormError(null);
    try {
      const next = !(ledgerLink.is_active !== false);
      const updated = await accountingApi.updateCashBox(ledgerLink.id, { is_active: next });
      setLedgerLink(updated);
      onLedgersMaybeChanged?.();
      toast(next ? "تم تفعيل الصندوق." : "تم تعطيل الصندوق — لن يظهر في منتقيات الدفع.", "success");
    } catch (e) {
      setFormError(humanizeThrown(e, "تعذّر تغيير حالة الصندوق"));
    } finally {
      setLinkLoading(false);
    }
  };

  const handleSetDefault = async () => {
    if (!ledgerLink) return;
    setLinkLoading(true);
    setFormError(null);
    try {
      const updated = await accountingApi.setDefaultCashBox(ledgerLink.id);
      setLedgerLink(updated);
      onLedgersMaybeChanged?.();
      toast("صار هذا هو صندوق الشركة الافتراضي.", "success");
    } catch (e) {
      setFormError(humanizeThrown(e, "تعذّر تعيين الصندوق الافتراضي"));
    } finally {
      setLinkLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]">
      <div className="bg-[var(--color-surface)] rounded-lg p-6 w-full max-w-md">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-xl font-bold dark:text-white">تعديل الصندوق</h2>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">
              كل صندوق مرتبط بحساب نقدية في الشجرة بنفس الاسم؛ يُستخدم في قيود الدفع.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-[var(--color-text-muted)] hover:text-[var(--color-text)] shrink-0"
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
            <label className="block text-sm font-medium text-[var(--color-text)] mb-1">
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

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-sm">
            <p className="font-medium text-[var(--color-text)] mb-1">
              الربط بالمحاسبة
            </p>
            {ledgerLink === undefined ? (
              <p className="text-[var(--color-text-muted)]">جاري التحقق…</p>
            ) : ledgerLink ? (
              <>
                <p className="text-green-800 dark:text-green-200">
                  مرتبط: حساب الشجرة{" "}
                  <span className="font-mono font-semibold">
                    {ledgerLink.account_code}
                  </span>{" "}
                  — {ledgerLink.name}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {!ledgerLink.is_default && ledgerLink.is_active !== false && (
                    <button
                      type="button"
                      disabled={linkLoading}
                      onClick={handleSetDefault}
                      className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-surface-3)] disabled:opacity-50"
                    >
                      جعله الصندوق الافتراضي
                    </button>
                  )}
                  {ledgerLink.is_default && (
                    <span className="rounded-md bg-[var(--color-surface-3)] px-3 py-1.5 text-xs text-[var(--color-text-muted)]">
                      الصندوق الافتراضي للشركة
                    </span>
                  )}
                  <button
                    type="button"
                    disabled={linkLoading}
                    onClick={handleToggleActive}
                    className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-surface-3)] disabled:opacity-50"
                  >
                    {ledgerLink.is_active === false ? "تفعيل الصندوق" : "تعطيل الصندوق"}
                  </button>
                </div>
              </>
            ) : (
              <p className="text-[var(--color-text)]">
                لا يوجد حساب في الشجرة لهذا الصندوق — صندوقٌ قديم من قبل توحيد
                الإنشاء. شغّل <span className="font-mono">backfill_cash_boxes</span>{" "}
                لربطه، فالربط صار يُنشأ مع الصندوق نفسه.
              </p>
            )}
          </div>

          <p className="text-xs text-[var(--color-text-muted)]">
            الرصيد الحالي لا يُعدّل من هنا؛ يتغيّر من حركات الصندوق فقط.
          </p>

          <div className="flex justify-end pt-4 gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)] rounded-md"
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
