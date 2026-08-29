/**
 * T-INTENT — جدول دفعات المستند داخل المستند نفسه (بيع وشراء معاً).
 *
 * قبله كان جواب سؤال «ما الذي دُفع على هذه الفاتورة؟» موزّعاً: جدولُ سنداتٍ لا
 * يظهر إلا في **وضع العرض**، وزرٌّ مكتوبٌ عليه «طباعة السند» يفتح قائمة السندات
 * في تبويب جديد، ودفعةٌ سُجِّلت على المسودة لا أثر لها في الشاشة إطلاقاً. فمن
 * أدخل دفعةً ثم لم يرَها ظنّ أنها ضاعت.
 *
 * هنا سطحٌ واحد يجمع الحالتين ويميّزهما بصراحة:
 *   • **مرحّل** — سندٌ في الدفاتر، يُفتح ويُطبع ولا يُعدَّل من هنا.
 *   • **غير مرحّل** — نيّة دفعٍ على المسودة، تُعدَّل وتُحذف، وتتحوّل سنداً عند
 *     ترحيل المستند.
 *
 * سابقة: Zoho Books تعرض تبويب «Payments Received» داخل الفاتورة بتعديلٍ لكل
 * صفّ، وOdoo تضع زرّ Pay وشارة Partial عليها. أخذنا السطح، وتجاوزناهما بأن
 * المسودة نفسها تحمل دفعتها — وهو ما يفعله «الأصيل» ويطلبه سير عمل المالك.
 *
 * المكوّن **بلا جلب بيانات**: المحرّر يملك الحالة ويمرّرها، فلا مصدرَ ثانٍ.
 */
import React from "react";
import { Loader2, Pencil, Plus, Printer, Trash2 } from "lucide-react";
import { formatMoney } from "../../utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";
import type { DocumentPaymentSide, InvoiceSettlement } from "./DocumentPaymentPanel";

/** شيك مرفق بالمسودة — نيّةٌ لم تدخل الدفاتر. */
export type IntentChequeRow = {
  id: number;
  cheque_number: string;
  bank_name?: string | null;
  due_date?: string | null;
  amount: string | number;
};

/** سندٌ موزَّع على هذا المستند (مرحّل أو مسودة سندٍ قائمة). */
export type PostedPaymentRow = {
  id: number;
  payment_date: string;
  allocated_amount: string | number;
  is_posted: boolean;
  journal: number | null;
};

const WORDS: Record<DocumentPaymentSide, { voucher: string; title: string }> = {
  customer: { voucher: "سند قبض", title: "سندات القبض والدفعات" },
  supplier: { voucher: "سند صرف", title: "سندات الصرف والدفعات" },
};

export type InvoicePaymentsSectionProps = {
  side: DocumentPaymentSide;
  posted: PostedPaymentRow[];
  intentCash: number;
  /** T-AUTOPAID: صفُّ النقد مشتقٌّ من طبيعة المستند النقدي (يُسوّى تلقائياً
   *  عند الترحيل) لا نيّةً مخزَّنة — يتحدّث مع الشاشة ولا يُعدَّل ولا يُحذف؛
   *  مَن لا يريده يحوّل المستند إلى آجل. */
  intentAuto?: boolean;
  /** اسم حساب الصندوق/البنك المنويّ — للعرض فقط. */
  intentCashAccountLabel?: string;
  intentCheques: IntentChequeRow[];
  settlement: InvoiceSettlement;
  paid: number;
  /** مسودة + صلاحية دفع ⇒ صفوف النيّة قابلة للتعديل والحذف. */
  editable: boolean;
  busy?: boolean;
  onAddPayment: () => void;
  onEditIntent: () => void;
  onRemoveIntentCash: () => void;
  onRemoveIntentCheque: (chequeId: number) => void;
  onOpenVoucher: (paymentId: number) => void;
  sectionRef?: React.Ref<HTMLDivElement>;
};

const CELL = "px-2 py-1.5 text-right align-middle";

export const InvoicePaymentsSection: React.FC<InvoicePaymentsSectionProps> = ({
  side, posted, intentCash, intentAuto, intentCashAccountLabel, intentCheques,
  settlement, paid, editable, busy, onAddPayment, onEditIntent,
  onRemoveIntentCash, onRemoveIntentCheque, onOpenVoucher, sectionRef,
}) => {
  const words = WORDS[side];
  const hasIntentCash = intentCash > 0.009;
  const rowCount = posted.length + intentCheques.length + (hasIntentCash ? 1 : 0);

  return (
    <div
      ref={sectionRef}
      data-testid="invoice-payments-section"
      className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-xs"
    >
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <b className="text-[var(--color-text)]">
          {words.title}
          <span className="mr-1 font-normal text-[var(--color-text-muted)]">
            ({rowCount})
          </span>
        </b>
        <button
          type="button"
          data-testid="payments-section-add"
          className="ktra-toolbtn inline-flex items-center gap-1"
          onClick={onAddPayment}
          disabled={busy}
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
          إضافة دفعة
        </button>
      </div>

      {rowCount === 0 ? (
        <p className="py-2 text-center text-[var(--color-text-muted)]">
          لا دفعات على هذا المستند بعد.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
                <th className={CELL}>النوع</th>
                <th className={CELL}>المبلغ</th>
                <th className={CELL}>التاريخ</th>
                <th className={CELL}>المرجع</th>
                <th className={CELL}>الحالة</th>
                <th className={`${CELL} text-center`}>إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {/* الدفعات التي دخلت الدفاتر — تُفتح ولا تُعدَّل من هنا. */}
              {posted.map((row) => (
                <tr key={`p-${row.id}`} className="border-b border-[var(--color-border)]">
                  <td className={CELL}>{words.voucher}</td>
                  <td className={`${CELL} font-mono`}>
                    {formatMoney(Number(row.allocated_amount))}
                  </td>
                  <td className={CELL}>{formatDateLocalized(row.payment_date)}</td>
                  <td className={CELL}>
                    #{row.id}
                    {row.journal ? (
                      <span className="text-[var(--color-text-muted)]"> · قيد #{row.journal}</span>
                    ) : null}
                  </td>
                  <td className={CELL}>
                    <span
                      className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-bold ${
                        row.is_posted
                          ? "bg-green-100 text-green-700"
                          : "bg-amber-100 text-amber-700"
                      }`}
                    >
                      {row.is_posted ? "مرحّل ✓" : "غير مرحّل"}
                    </span>
                  </td>
                  <td className={`${CELL} text-center`}>
                    <button
                      type="button"
                      className="ktra-toolbtn"
                      aria-label={`فتح ${words.voucher} #${row.id}`}
                      title={`فتح ${words.voucher} #${row.id} للعرض والطباعة`}
                      onClick={() => onOpenVoucher(row.id)}
                    >
                      <Printer className="h-3 w-3" />
                    </button>
                  </td>
                </tr>
              ))}

              {/* نيّة الدفع على المسودة — تُعدَّل وتُحذف، وتتحوّل سنداً بالترحيل. */}
              {hasIntentCash && (
                <tr
                  data-testid="intent-row-cash"
                  className="border-b border-[var(--color-border)] bg-amber-50/60"
                >
                  <td className={CELL}>نقد</td>
                  <td className={`${CELL} font-mono`}>{formatMoney(intentCash)}</td>
                  <td className={CELL}>—</td>
                  <td className={CELL}>{intentCashAccountLabel || "الصندوق"}</td>
                  <td className={CELL}>
                    <span className="inline-flex rounded bg-amber-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
                      غير مرحّل
                    </span>
                  </td>
                  <td className={`${CELL} text-center`}>
                    {intentAuto ? (
                      <span
                        className="text-[10px] text-[var(--color-text-muted)]"
                        title="مستند نقدي — دفعته تلقائية تتبع الإجمالي وتُسوّى عند الترحيل. للإلغاء حوِّله إلى آجل."
                      >
                        تلقائي
                      </span>
                    ) : editable && (
                      <span className="inline-flex gap-1">
                        <button
                          type="button" className="ktra-toolbtn"
                          aria-label="تعديل الدفعة النقدية" title="تعديل الدفعة النقدية"
                          onClick={onEditIntent} disabled={busy}
                        >
                          <Pencil className="h-3 w-3" />
                        </button>
                        <button
                          type="button" className="ktra-toolbtn"
                          aria-label="حذف الدفعة النقدية" title="حذف الدفعة النقدية"
                          onClick={onRemoveIntentCash} disabled={busy}
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
              )}

              {intentCheques.map((cheque) => (
                <tr
                  key={`c-${cheque.id}`}
                  data-testid="intent-row-cheque"
                  className="border-b border-[var(--color-border)] bg-amber-50/60"
                >
                  <td className={CELL}>شيك</td>
                  <td className={`${CELL} font-mono`}>{formatMoney(Number(cheque.amount))}</td>
                  <td className={CELL}>
                    {cheque.due_date ? formatDateLocalized(cheque.due_date) : "—"}
                  </td>
                  <td className={CELL}>
                    {cheque.cheque_number}
                    {cheque.bank_name ? (
                      <span className="text-[var(--color-text-muted)]"> · {cheque.bank_name}</span>
                    ) : null}
                  </td>
                  <td className={CELL}>
                    <span className="inline-flex rounded bg-amber-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
                      غير مرحّل
                    </span>
                  </td>
                  <td className={`${CELL} text-center`}>
                    {editable && (
                      <span className="inline-flex gap-1">
                        <button
                          type="button" className="ktra-toolbtn"
                          aria-label={`تعديل الشيك ${cheque.cheque_number}`}
                          title={`تعديل الشيك ${cheque.cheque_number}`}
                          onClick={onEditIntent} disabled={busy}
                        >
                          <Pencil className="h-3 w-3" />
                        </button>
                        <button
                          type="button" className="ktra-toolbtn"
                          aria-label={`حذف الشيك ${cheque.cheque_number}`}
                          title={`حذف الشيك ${cheque.cheque_number}`}
                          onClick={() => onRemoveIntentCheque(cheque.id)} disabled={busy}
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-1.5 flex flex-wrap items-center justify-end gap-3 border-t border-[var(--color-border)] pt-1.5">
        <span className="text-[var(--color-text-muted)]">
          المدفوع المرحّل <b className="font-mono text-[var(--color-text)]">{formatMoney(paid)}</b>
        </span>
        {settlement.pendingIntent > 0.009 && (
          <span className="text-[var(--color-text-muted)]">
            غير مرحّل <b className="font-mono text-amber-600">{formatMoney(settlement.pendingIntent)}</b>
          </span>
        )}
        <span className="text-[var(--color-text-muted)]">
          المتبقي{" "}
          <b className="font-mono text-[var(--color-text)]" data-testid="payments-section-remaining">
            {formatMoney(settlement.remainingAfterIntent)}
          </b>
        </span>
      </div>

      {settlement.intentCoversAll && (
        <p className="mt-1 text-[11px] text-amber-700">
          الدفعة مسجَّلة بالكامل ولم تدخل الدفاتر بعد — تتحوّل إلى {words.voucher} عند
          ترحيل المستند، ولا تؤثّر على رصيد الطرف قبل ذلك.
        </p>
      )}
    </div>
  );
};
