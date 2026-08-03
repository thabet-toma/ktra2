/**
 * ConvertTargetDialog — «تحويل إلى…»: طلبية أم فاتورة؟
 *
 * يحلّ محل `window.confirm` (حوار المتصفح الذي يحمل اسم الدومين ولا يقبل أكثر
 * من خيارين نعم/لا). هنا خياران حقيقيان بشرح أثر كلٍّ منهما قبل الضغط.
 *
 * مشترك بين عروض البيع والشراء والاستيراد — مصدر واحد لسلوك التحويل.
 */
import React from "react";
import { FileText, ClipboardList, X } from "lucide-react";

export type ConvertTarget = "order" | "invoice";

interface Props {
  title?: string;
  /** وصف مختصر يظهر أعلى الخيارين (اختياري). */
  hint?: string;
  /** أثر كل وجهة — يختلف بين البيع والشراء، فلا يُثبَّت نص البيع للطرفين. */
  orderDescription?: string;
  invoiceDescription?: string;
  onPick: (target: ConvertTarget) => void;
  onClose: () => void;
}

export const ConvertTargetDialog: React.FC<Props> = ({
  title = "تحويل المستند",
  hint = "اختر الوجهة — الطلبية تحجز الكمية للزبون، والفاتورة تُثبت البيع محاسبياً.",
  orderDescription = "تحجز الكمية للزبون مدةً محدودة، وتقبل عربوناً — بلا قيد محاسبي.",
  invoiceDescription = "مستند بيع مباشر — يُثبت الذمّة عند ترحيله.",
  onPick,
  onClose,
}) => (
  <div
    dir="rtl"
    className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
    role="dialog"
    aria-modal="true"
  >
    <div className="w-full max-w-md rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl">
      <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
        <h3 className="font-bold text-[var(--color-text)]">{title}</h3>
        <button
          type="button"
          onClick={onClose}
          className="p-1 rounded text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
          title="إغلاق"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="p-4 space-y-3">
        <p className="text-xs text-[var(--color-text-muted)]">{hint}</p>

        <button
          type="button"
          onClick={() => onPick("order")}
          className="flex w-full items-start gap-3 rounded-lg border border-[var(--color-border)] p-3 text-right hover:bg-[var(--color-surface-2)]"
        >
          <ClipboardList className="mt-0.5 h-5 w-5 text-[var(--color-primary)]" />
          <span>
            <span className="block font-semibold text-[var(--color-text)]">طلبية</span>
            <span className="block text-[11px] text-[var(--color-text-muted)]">
              {orderDescription}
            </span>
          </span>
        </button>

        <button
          type="button"
          onClick={() => onPick("invoice")}
          className="flex w-full items-start gap-3 rounded-lg border border-[var(--color-border)] p-3 text-right hover:bg-[var(--color-surface-2)]"
        >
          <FileText className="mt-0.5 h-5 w-5 text-emerald-600" />
          <span>
            <span className="block font-semibold text-[var(--color-text)]">فاتورة</span>
            <span className="block text-[11px] text-[var(--color-text-muted)]">
              {invoiceDescription}
            </span>
          </span>
        </button>
      </div>

      <div className="flex justify-start border-t border-[var(--color-border)] px-4 py-3">
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg border border-[var(--color-border)] px-4 py-1.5 text-sm text-[var(--color-text-muted)]"
        >
          إلغاء الأمر
        </button>
      </div>
    </div>
  </div>
);

export default ConvertTargetDialog;
