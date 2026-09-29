import React, { useState } from "react";
import { printWarrantyCertificate } from "../../services/afterSalesApi";
import { humanizeThrown } from "../../utils/drfError";
import { formatNumber } from "../../utils/formatNumber";
import {
  WARRANTY_PRINT_BLOCKED_TEXT,
  warrantyInvoicePrintLabel,
} from "../../utils/warranty";
import { useInvoiceWarrantyCount } from "./useInvoiceWarrantyCount";
import { WarrantySendButton } from "./WarrantySendButton";

/**
 * #238 — شريطٌ غير حاجب بعد ترحيل بيعٍ: «اطبع كفالات الفاتورة (N)». مصدرٌ واحد
 * يستعمله محرّر الفاتورة وقائمة الفواتير.
 * يختفي بلا أثر حين لا بطاقات قابلة للطباعة أو الوحدة مطفأة أو لا صلاحية عرض
 * (الشروط في `useInvoiceWarrantyCount`).
 */
export const WarrantyPrintBar: React.FC<{
  invoiceId: number;
  /** رقم الفاتورة للعرض — بدونه «لهذه الفاتورة» (داخل المحرّر). */
  invoiceNumber?: string;
  onDismiss: () => void;
}> = ({ invoiceId, invoiceNumber, onDismiss }) => {
  const count = useInvoiceWarrantyCount(invoiceId, true, false, invoiceId);
  const [problem, setProblem] = useState<string | null>(null);

  if (count <= 0) return null;

  // النافذة تُفتح داخل النقرة نفسها قبل أي await — انظر `printWarrantyCertificate`.
  const print = async () => {
    setProblem(null);
    try {
      const outcome = await printWarrantyCertificate({ sales_invoice: invoiceId });
      if (outcome === "blocked") setProblem(WARRANTY_PRINT_BLOCKED_TEXT);
    } catch (e) {
      setProblem(humanizeThrown(e, "تعذّرت طباعة الكفالات"));
    }
  };

  return (
    <div
      className="ktra-banner ktra-banner--ok mb-2"
      role="status"
      data-testid="warranty-print-bar"
    >
      <span className="flex-1">
        صدرت {formatNumber(count)} بطاقة كفالة {invoiceNumber ? `للفاتورة ${invoiceNumber}` : "لهذه الفاتورة"}.
        {problem && <b className="ms-2 text-red-700">{problem}</b>}
      </span>
      <button
        type="button"
        className="rounded border border-current px-2 py-0.5 text-xs font-bold"
        onClick={() => void print()}
      >
        {warrantyInvoicePrintLabel(count)}
      </button>
      <WarrantySendButton
        docType="warranty_certificate"
        docId={invoiceId}
        docLabel={`شهادة كفالة ${invoiceNumber ?? `الفاتورة #${invoiceId}`}`}
        className="rounded border border-current px-2 py-0.5 text-xs font-bold"
      />
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
