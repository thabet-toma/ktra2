import React from "react";
import { formatMoney } from "../../utils/formatNumber";

export type InvoicePaymentStatus = "paid" | "partially_paid" | "unpaid";

const META: Record<InvoicePaymentStatus, { label: string; className: string }> = {
  paid: {
    label: "مدفوعة بالكامل",
    className: "bg-green-100 text-green-700",
  },
  partially_paid: {
    label: "مدفوعة جزئياً",
    className: "bg-amber-100 text-amber-700",
  },
  unpaid: {
    label: "غير مدفوعة",
    className: "bg-red-100 text-red-700",
  },
};

/**
 * T-DUE: «متأخرة» بُعدٌ فوق حالة الدفع لا قيمةٌ رابعة فيها — فهي شارةٌ ثانية
 * بجانب الأولى لا بديلٌ عنها: «مدفوعة جزئياً» يبقى ظاهراً ويُقال معه «تأخّرت
 * 12 يوماً». دمجُها في `status` كان يخفي «كم بقي» خلف «تأخّر»، ويكسر الفلاتر
 * والشارات القائمة على القيم الثلاث.
 *
 * T-INTENT: و«غير مرحّلة» بُعدٌ ثالث بالمنطق نفسه — الدفعة المرفقة بمسودة ليست
 * قيمةً رابعة في `status` (فما لم يُرحَّل ليس مدفوعاً في الدفاتر) بل شارةٌ
 * كهرمانية بجانبها تقول إنّ على المستند دفعةً تنتظر الترحيل.
 */
export const PaymentStatusBadge: React.FC<{
  status?: InvoicePaymentStatus;
  label?: string;
  isOverdue?: boolean;
  daysOverdue?: number;
  /** الدفعة المرفقة غير المرحّلة (صفر/غياب ⇒ لا شارة). */
  pendingIntent?: number;
  /** الدفعة تغطّي إجمالي المستند ⇒ «مدفوعة — غير مرحّلة». */
  intentCoversAll?: boolean;
}> = ({
  status = "unpaid", label, isOverdue, daysOverdue, pendingIntent, intentCoversAll,
}) => {
  const meta = META[status];
  const hasIntent = (pendingIntent ?? 0) > 0.009;
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap">
      <span className={`inline-flex rounded px-2 py-0.5 text-xs font-semibold ${meta.className}`}>
        {label || meta.label}
      </span>
      {hasIntent && (
        <span
          data-testid="pending-intent-badge"
          title={
            `دفعة مسجَّلة على المسودة (${formatMoney(pendingIntent ?? 0)}) لم تدخل `
            + "الدفاتر بعد — تتحوّل إلى سند عند ترحيل المستند."
          }
          className="inline-flex rounded bg-amber-500 px-1.5 py-0.5 text-[10px] font-bold text-white"
        >
          {intentCoversAll ? "مدفوعة — غير مرحّلة" : "دفعة غير مرحّلة"}
        </span>
      )}
      {isOverdue && (
        <span
          data-testid="overdue-badge"
          title={
            daysOverdue
              ? `تأخّر السداد ${daysOverdue} يوماً عن تاريخ الاستحقاق`
              : "تأخّر السداد عن تاريخ الاستحقاق"
          }
          className="inline-flex rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold text-white"
        >
          متأخرة{daysOverdue ? ` ${daysOverdue}ي` : ""}
        </span>
      )}
    </span>
  );
};
