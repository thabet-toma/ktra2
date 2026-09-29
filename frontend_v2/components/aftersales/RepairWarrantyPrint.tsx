import React, { useState } from "react";
import { Printer } from "lucide-react";
import { printWarrantyCertificate } from "../../services/afterSalesApi";
import { humanizeThrown } from "../../utils/drfError";
import { WARRANTY_PRINT_BLOCKED_TEXT } from "../../utils/warranty";

/**
 * #244 — طباعة ورقة كفالة الإصلاح التي أنشأها تسليم أمر الصيانة. النافذة تُفتح داخل
 * النقرة نفسها قبل أي await (انظر `printWarrantyCertificate`).
 */
const useRepairPrint = (cardId: number) => {
  const [problem, setProblem] = useState<string | null>(null);
  const print = async () => {
    setProblem(null);
    try {
      const outcome = await printWarrantyCertificate({ cards: [cardId] });
      if (outcome === "blocked") setProblem(WARRANTY_PRINT_BLOCKED_TEXT);
    } catch (e) {
      setProblem(humanizeThrown(e, "تعذّرت طباعة كفالة الإصلاح"));
    }
  };
  return { problem, print };
};

export const RepairWarrantyPrintButton: React.FC<{ cardId: number }> = ({ cardId }) => {
  const { problem, print } = useRepairPrint(cardId);
  return (
    <>
      <button
        type="button"
        onClick={() => void print()}
        className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm font-bold text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
        data-testid="repair-warranty-print"
      >
        <Printer className="h-4 w-4" /> اطبع كفالة الإصلاح
      </button>
      {problem && <b className="text-xs text-red-700 dark:text-red-400">{problem}</b>}
    </>
  );
};

/** شريطٌ غير حاجب بعد نقلة التسليم: «صدرت كفالة إصلاح لهذا الأمر». */
export const RepairWarrantyPrintBar: React.FC<{
  cardId: number;
  orderNumber: string;
  onDismiss: () => void;
}> = ({ cardId, orderNumber, onDismiss }) => {
  const { problem, print } = useRepairPrint(cardId);
  return (
    <div className="ktra-banner ktra-banner--ok" role="status" data-testid="repair-warranty-print-bar">
      <span className="flex-1">
        صدرت كفالة إصلاح للأمر {orderNumber}.
        {problem && <b className="ms-2 text-red-700 dark:text-red-400">{problem}</b>}
      </span>
      <button
        type="button"
        className="rounded border border-current px-2 py-0.5 text-xs font-bold"
        onClick={() => void print()}
      >
        اطبع كفالة الإصلاح
      </button>
      <button
        type="button"
        className="rounded px-2 py-0.5 text-xs"
        aria-label="إخفاء الشريط"
        onClick={onDismiss}
      >
        إخفاء
      </button>
    </div>
  );
};
