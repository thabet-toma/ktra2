import React, { useState } from "react";
import { Loader2, Printer } from "lucide-react";
import { printWarrantyReferralSlip } from "../../services/afterSalesApi";
import { useConfirm } from "../../contexts/ConfirmContext";
import { REFERRAL_PAID_REPAIR_WARNING, WARRANTY_PRINT_BLOCKED_TEXT } from "../../utils/warranty";

interface Props {
  cardId: number;
  onDone: () => void;
  onPaidRepair: () => void;
}

/** #241 — حكم «إحالة»: الجهاز عند الوكيل، لا أمر صيانة هنا إلا بقبول الزبون إصلاحاً مدفوعاً. */
export const ServiceOrderReferralPanel: React.FC<Props> = ({ cardId, onDone, onPaidRepair }) => {
  const confirm = useConfirm();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [printed, setPrinted] = useState(false);

  const printSlip = async () => {
    setBusy(true);
    setErr(null);
    setPrinted(false);
    try {
      const outcome = await printWarrantyReferralSlip(cardId);
      if (outcome === "blocked") setErr(WARRANTY_PRINT_BLOCKED_TEXT);
      else setPrinted(true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "تعذّرت طباعة ورقة الإحالة");
    } finally {
      setBusy(false);
    }
  };

  const paidRepair = async () => {
    const accepted = await confirm({
      title: "إصلاح مدفوع رغم الإحالة",
      message: REFERRAL_PAID_REPAIR_WARNING,
    });
    if (accepted) onPaidRepair();
  };

  return (
    <section
      className="mt-3 space-y-3 rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-200"
      data-testid="intake-referral-panel"
    >
      <div className="text-base font-bold">راجع مركز الوكيل</div>
      <p className="text-sm">
        الجهاز خارج كفالة التاجر وكفالة المصنع سارية: يُحال الزبون إلى مركز الوكيل بورقة الإحالة، ولا يُفتح أمر صيانة هنا.
      </p>
      {err && (
        <div role="alert" className="text-sm text-red-600 dark:text-red-400">{err}</div>
      )}
      {printed && (
        <div role="status" className="text-sm" data-testid="intake-referral-printed">
          سُجّل حدث «أُحيل إلى الوكيل» في سجل البطاقة.
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void printSlip()}
          className="inline-flex items-center gap-1 rounded-lg bg-[var(--color-primary)] px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
          data-testid="intake-referral-print"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Printer className="h-4 w-4" />} ورقة الإحالة
        </button>
        <button
          type="button"
          onClick={onDone}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
          data-testid="intake-referral-done"
        >
          تمّ
        </button>
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => void paidRepair()}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
          data-testid="intake-referral-paid"
        >
          إصلاح مدفوع بطلب الزبون
        </button>
      </div>
    </section>
  );
};
