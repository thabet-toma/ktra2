import React, { useMemo } from "react";
import { Deal, DealPayment } from "@/types";
import { dealsService } from "@/services/dealsService";
import { formatMoney } from "@/utils/formatNumber";
import { useToast } from "@/contexts/ToastContext";
import { useConfirm } from "@/contexts/ConfirmContext";
import {
  Clock,
  Trash2,
  BookOpen,
  AlertTriangle,
  HelpCircle,
  RotateCcw,
  Link2,
  Image as ImageIcon,
  Receipt,
} from "lucide-react";

interface DealPaymentListProps {
  deal: Partial<Deal>;
  currentUser: any;
  onPaymentOperation: (
    operation:
      | "claim"
      | "swift"
      | "add"
      | "confirm"
      | "cancel"
      | "unpost"
      | "linkJournal",
    paymentType: string,
    data: any,
    paymentId?: string
  ) => void;
  onConfirmSupplier: (data: any) => void;
  /** فتح شاشة قيد اليومية في المحاسبة */
  onOpenAccountingJournal?: (journalId: number | null) => void;
}

const paymentSettled = (p: DealPayment) =>
  Boolean(p.confirmedBySupplier || p.isPosted);

/** حذف مسموح للدفعات غير المرحّلة محاسبياً (بعد «إلغاء الترحيل» أو إن لم يُرحّل أصلاً). التأكيد من المورد لا يمنع الحذف طالما الدفعة غير مرحّلة. */
const canDeletePayment = (p: DealPayment) => !p.isPosted;

const isManagerUser = (u: { role?: string } | undefined) =>
  String(u?.role || "").toLowerCase() === "manager";

function paymentLogicalKey(p: DealPayment): string {
  return `${Number(p.installmentNumber) || 0}:${Math.round(
    Number(p.amount ?? 0) * 100
  )}`;
}

function statusBadge(p: DealPayment): { label: string; cls: string } {
  if (p.isPosted)
    return {
      label: "مرحّل",
      cls: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200",
    };
  if (p.confirmedBySupplier)
    return {
      label: "مؤكدة من المورد",
      cls: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200",
    };
  if (p.bankSwiftImage)
    return {
      label: "تم الدفع (سليب)",
      cls: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200",
    };
  return {
    label: "مطالبة",
    cls: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200",
  };
}

const cellCls = "px-3 py-2 whitespace-nowrap";
const iconBtnCls =
  "inline-flex items-center gap-1 rounded border aseel-border-soft aseel-bg-field px-2 py-1 text-xs font-medium aseel-text-ink hover:aseel-bg-panel dark:aseel-bg-panel dark:hover:aseel-bg-grid-head";

/**
 * سجل مدفوعات الصفقة — جدول كثيف بنمط جداول الفواتير (بدل البطاقات القديمة
 * التي كانت تستهلك الشاشة). نفس العمليات: فتح/ربط قيد، شرح عدم الترحيل،
 * إلغاء ترحيل (مدير)، حذف من السجل.
 */
export const DealPaymentList: React.FC<DealPaymentListProps> = ({
  deal,
  currentUser,
  onPaymentOperation,
  onOpenAccountingJournal,
}) => {
  const toast = useToast();
  const confirmDialog = useConfirm();
  const showManagerUnpost = isManagerUser(currentUser);
  const payments = deal.payments || [];

  const duplicateKeyCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const p of payments) {
      const k = paymentLogicalKey(p);
      m.set(k, (m.get(k) ?? 0) + 1);
    }
    return m;
  }, [payments]);

  const totalSum = payments.reduce((s, p) => s + Number(p.amount ?? 0), 0);
  const dealCap = Number(deal.totalAmount ?? 0);
  const overpay = dealCap > 0 && totalSum > dealCap + 0.01;

  const openImage = (url?: string) => {
    if (url && String(url).trim())
      window.open(url, "_blank", "width=800,height=600");
  };

  const explainPosting = async (payment: DealPayment) => {
    try {
      const d = await dealsService.getPaymentPostingDiagnostics(
        String(deal.id),
        String(payment.id)
      );
      const lines =
        d.blockers?.length > 0
          ? d.blockers.map((b, i) => `${i + 1}. ${b}`).join("\n\n")
          : d.can_auto_post
            ? "الشروط تبدو مستوفاة على الخادم؛ جرّب إعادة تحميل الصفقة. إن استمرت المشكلة راجع سجل الخادم (أخطاء ترحيل الدفعة)."
            : "لم يُرجع الخادم تفاصيل؛ تحقق من ربط المورد والصندوق في المحاسبة.";
      void confirmDialog({
        title: "شرح عدم الترحيل التلقائي",
        message: `من الخادم:\n\n${lines}`,
        danger: false, hideCancel: true, confirmText: "حسناً",
      });
    } catch {
      toast("تعذّر جلب التشخيص من الخادم. تحقق من الاتصال ومسار واجهة الـ API.", "error");
    }
  };

  const linkManualJournal = (payment: DealPayment) => {
    const raw = window.prompt(
      "أدخل رقم قيد اليومية المرحّل (Journal ID) الظاهر في شاشة المحاسبة:",
      ""
    );
    if (raw == null || String(raw).trim() === "") return;
    const n = parseInt(String(raw).trim(), 10);
    if (!Number.isFinite(n) || n <= 0) {
      toast("أدخل رقماً صحيحاً.", "error");
      return;
    }
    onPaymentOperation("linkJournal", payment.type, { journalId: n }, payment.id);
  };

  const unpostPayment = async (payment: DealPayment) => {
    const ok = await confirmDialog({
      title: "إلغاء الترحيل المحاسبي",
      message:
        "• يُنشأ قيد عكسي مرحّل (مدين/دائن معكوس) فيُحدَّث ميزان المراجعة والأستاذ العام بشكل صحيح.\n" +
        "• القيد الأصلي يُبقى في النظام لكن يصبح غير مرحّل للتدقيق.\n" +
        "• يمكنك بعدها تصحيح النسب/المبالغ وحفظ الصفقة.",
      confirmText: "إلغاء الترحيل",
    });
    if (!ok) return;
    onPaymentOperation("unpost", payment.type, {}, payment.id);
  };

  const deletePayment = async (payment: DealPayment) => {
    const ok = await confirmDialog({
      title: "حذف الدفعة",
      message: `حذف الدفعة «${payment.type}» بمبلغ $${formatMoney(Number(payment.amount || 0))} من السجل؟`,
    });
    if (!ok) return;
    onPaymentOperation("cancel", payment.type, {}, payment.id);
  };

  if (payments.length === 0) {
    return (
      <div className="text-center py-8">
        <div className="w-16 h-16 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center mx-auto mb-4">
          <Clock className="w-8 h-8 text-gray-400" />
        </div>
        <p className="text-gray-600 dark:text-gray-400">
          لم يتم تسجيل أي مدفوعات بعد
        </p>
        <p className="text-sm text-gray-500 dark:text-gray-500 mt-1">
          ابدأ بدفع أول دفعة من جدول الدفعات أعلاه
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h4 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
        <Receipt className="w-4 h-4" />
        سجل المدفوعات
        <span className="text-xs font-normal aseel-text-soft">
          ({payments.length} دفعة)
        </span>
      </h4>

      {overpay && (
        <div
          className="flex gap-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-950 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-100"
          role="alert"
        >
          <AlertTriangle className="w-5 h-5 shrink-0 text-rose-600 dark:text-rose-400" />
          <div>
            <p className="font-semibold">مجموع المدفوعات يتجاوز إجمالي الصفقة</p>
            <p className="mt-1 opacity-90">
              المجموع المسجّل:{" "}
              <span className="font-mono font-medium">
                ${formatMoney(totalSum)}
              </span>
              {" — "}
              إجمالي الصفقة:{" "}
              <span className="font-mono font-medium">
                ${formatMoney(dealCap)}
              </span>
              .
            </p>
          </div>
        </div>
      )}

      <div className="rounded-lg border aseel-border-soft dark:aseel-border-soft overflow-x-auto">
        <table className="w-full text-sm text-right">
          <thead className="aseel-bg-panel dark:aseel-bg-panel text-xs aseel-text-soft">
            <tr className="border-b aseel-border-soft dark:aseel-border-soft">
              <th className={`${cellCls} font-medium w-16`}>القسط</th>
              <th className={`${cellCls} font-medium`}>النوع</th>
              <th className={`${cellCls} font-medium w-24`}>التاريخ</th>
              <th className={`${cellCls} font-medium w-28`}>المبلغ $</th>
              <th className={`${cellCls} font-medium w-20`}>الصرف</th>
              <th className={`${cellCls} font-medium w-24`}>عمولة</th>
              <th className={`${cellCls} font-medium w-24`}>مرفقات</th>
              <th className={`${cellCls} font-medium w-32`}>الحالة</th>
              <th className={`${cellCls} font-medium w-28`}>القيد</th>
              <th className={`${cellCls} font-medium`}>إجراءات</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
            {payments.map((payment) => {
              const jid =
                payment.journalId != null && payment.journalId !== ""
                  ? Number(payment.journalId)
                  : NaN;
              const hasJournalId = Number.isFinite(jid) && jid > 0;
              const deletable = canDeletePayment(payment);
              const dupN =
                duplicateKeyCounts.get(paymentLogicalKey(payment)) ?? 0;
              const badge = statusBadge(payment);
              const needsManualPosting =
                Boolean(deal.id) &&
                payment.confirmedBySupplier &&
                !payment.isPosted;

              return (
                <tr key={payment.id} className="align-middle">
                  <td className={cellCls}>
                    {payment.installmentNumber
                      ? `دفعة ${payment.installmentNumber}`
                      : "عام"}
                  </td>
                  <td className={cellCls}>
                    {payment.type}
                    {dupN > 1 && (
                      <span
                        className="mr-2 inline-flex items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-700 dark:bg-slate-800 dark:text-slate-200"
                        title={`يوجد ${dupN} سجلات بنفس القسط والمبلغ — راجع التكرار قبل الترحيل.`}
                      >
                        <AlertTriangle className="w-3 h-3" /> مكرر ×{dupN}
                      </span>
                    )}
                  </td>
                  <td className={`${cellCls} font-mono text-xs`}>
                    {payment.paymentDate
                      ? new Date(payment.paymentDate).toLocaleDateString("en-GB")
                      : "—"}
                  </td>
                  <td className={`${cellCls} font-mono font-bold`}>
                    ${formatMoney(Number(payment.amount || 0))}
                  </td>
                  <td className={`${cellCls} font-mono text-xs`}>
                    {Number(payment.usdToIls || 0) > 0
                      ? formatMoney(Number(payment.usdToIls))
                      : "—"}
                  </td>
                  <td className={`${cellCls} font-mono text-xs`}>
                    {Number(payment.transferCost || 0) > 0
                      ? `$${formatMoney(Number(payment.transferCost))}`
                      : "—"}
                  </td>
                  <td className={cellCls}>
                    <span className="inline-flex gap-1">
                      {payment.alibabaClaimImage && (
                        <button
                          type="button"
                          className={iconBtnCls}
                          title="صورة المطالبة (Claim)"
                          onClick={() => openImage(payment.alibabaClaimImage)}
                        >
                          <ImageIcon className="w-3.5 h-3.5" /> مطالبة
                        </button>
                      )}
                      {payment.bankSwiftImage && (
                        <button
                          type="button"
                          className={iconBtnCls}
                          title="صورة السليب (Swift)"
                          onClick={() => openImage(payment.bankSwiftImage)}
                        >
                          <ImageIcon className="w-3.5 h-3.5" /> سليب
                        </button>
                      )}
                      {!payment.alibabaClaimImage && !payment.bankSwiftImage && "—"}
                    </span>
                  </td>
                  <td className={cellCls}>
                    <span
                      className={`text-xs px-2 py-1 rounded-full whitespace-nowrap ${badge.cls}`}
                    >
                      {badge.label}
                    </span>
                  </td>
                  <td className={cellCls}>
                    {hasJournalId ? (
                      onOpenAccountingJournal ? (
                        <button
                          type="button"
                          className={iconBtnCls}
                          title="فتح القيد في المحاسبة"
                          onClick={() => onOpenAccountingJournal(jid)}
                        >
                          <BookOpen className="w-3.5 h-3.5" />
                          <span className="font-mono">#{jid}</span>
                        </button>
                      ) : (
                        <span className="font-mono text-xs">#{jid}</span>
                      )
                    ) : payment.isPosted ? (
                      <span
                        className="text-xs text-amber-700 dark:text-amber-300"
                        title="تم الترحيل لكن رقم القيد غير ظاهر في البيانات؛ أعد تحميل الصفقة أو ابحث في قيود اليومية بتاريخ الدفعة."
                      >
                        مرحّل — بلا رقم
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className={cellCls}>
                    <span className="inline-flex flex-wrap gap-1">
                      {needsManualPosting && (
                        <>
                          <button
                            type="button"
                            className={iconBtnCls}
                            title="تأكيد المورد محفوظ — الترحيل يدوي من دفتر اليومية (مدين مورد / دائن صندوق). اضغط لشرح سبب عدم الترحيل التلقائي."
                            onClick={() => void explainPosting(payment)}
                          >
                            <HelpCircle className="w-3.5 h-3.5" /> شرح
                          </button>
                          {!hasJournalId && (
                            <button
                              type="button"
                              className={iconBtnCls}
                              title="إن أنشأت قيداً يدوياً ولم يُربَط تلقائياً بالدفعة"
                              onClick={() => linkManualJournal(payment)}
                            >
                              <Link2 className="w-3.5 h-3.5" /> ربط قيد
                            </button>
                          )}
                        </>
                      )}
                      {payment.isPosted && showManagerUnpost && (
                        <button
                          type="button"
                          className={iconBtnCls}
                          title="يزيل قيد اليومية ويعيد الدفعة قابلة للتعديل (مدير)"
                          onClick={() => unpostPayment(payment)}
                        >
                          <RotateCcw className="w-3.5 h-3.5" /> إلغاء الترحيل
                        </button>
                      )}
                      {deletable && (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 rounded border border-red-200 bg-red-50 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-100 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200 dark:hover:bg-red-900/30"
                          title="حذف الدفعة من السجل"
                          onClick={() => deletePayment(payment)}
                        >
                          <Trash2 className="w-3.5 h-3.5" /> حذف
                        </button>
                      )}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="aseel-bg-panel dark:aseel-bg-panel font-bold border-t aseel-border-soft dark:aseel-border-soft">
              <td className={cellCls} colSpan={3}>
                المجموع
              </td>
              <td className={`${cellCls} font-mono`}>${formatMoney(totalSum)}</td>
              <td className={cellCls} colSpan={2}>
                {dealCap > 0 && (
                  <span className="text-xs font-normal aseel-text-soft">
                    المتبقي:{" "}
                    <span className="font-mono font-bold">
                      ${formatMoney(Math.max(0, dealCap - totalSum))}
                    </span>
                  </span>
                )}
              </td>
              <td className={cellCls} colSpan={4} />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
};
