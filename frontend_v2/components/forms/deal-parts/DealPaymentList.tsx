import React, { useMemo } from "react";
import { Deal, DealPayment } from "@/types";
import { dealsService } from "@/services/dealsService";
import {
  Clock,
  Trash2,
  BookOpen,
  AlertTriangle,
  HelpCircle,
  RotateCcw,
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

export const DealPaymentList: React.FC<DealPaymentListProps> = ({
  deal,
  currentUser,
  onPaymentOperation,
  onOpenAccountingJournal,
}) => {
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

  const totalSum = payments.reduce(
    (s, p) => s + Number(p.amount ?? 0),
    0
  );
  const dealCap = Number(deal.totalAmount ?? 0);
  const overpay = dealCap > 0 && totalSum > dealCap + 0.01;

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
    <div className="space-y-6">
      <h4 className="font-bold text-gray-900 dark:text-white flex items-center gap-2">
        سجل المدفوعات
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
                ${totalSum.toLocaleString()}
              </span>
              {" — "}
              إجمالي الصفقة:{" "}
              <span className="font-mono font-medium">
                ${dealCap.toLocaleString()}
              </span>
              .
            </p>
          </div>
        </div>
      )}

      {payments.map((payment) => {
        const jid =
          payment.journalId != null && payment.journalId !== ""
            ? Number(payment.journalId)
            : NaN;
        const hasJournalId = Number.isFinite(jid) && jid > 0;
        const deletable = canDeletePayment(payment);
        const dupN = duplicateKeyCounts.get(paymentLogicalKey(payment)) ?? 0;

        return (
          <div
            key={payment.id}
            className="border border-gray-200 dark:border-gray-700 rounded-lg p-4"
          >
            {dupN > 1 && (
              <div
                className="mb-3 text-xs text-slate-800 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 dark:bg-slate-900/50 dark:text-slate-200 dark:border-slate-600"
                role="status"
              >
                يوجد {dupN} سجلات بنفس القسط والمبلغ — راجع التكرار قبل الترحيل.
              </div>
            )}
            <div className="flex justify-between items-start mb-3 gap-2 flex-wrap">
              <div>
                <h5 className="font-medium text-gray-900 dark:text-white">
                  {payment.type}
                </h5>
                <p className="text-sm text-gray-500">
                  {new Date(payment.paymentDate).toLocaleDateString("ar-EG")}
                </p>
              </div>
              <div className="text-left sm:text-right flex flex-col items-stretch sm:items-end gap-2 min-w-[10rem]">
                <div className="font-bold text-lg text-gray-900 dark:text-white">
                  ${payment.amount?.toLocaleString()}
                </div>
                <div
                  className={`text-xs px-2 py-1 rounded-full w-fit ${
                    paymentSettled(payment)
                      ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200"
                      : payment.bankSwiftImage
                        ? "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200"
                        : "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200"
                  }`}
                >
                  {payment.isPosted
                    ? "مرحّل / مدفوع"
                    : payment.confirmedBySupplier
                      ? "مؤكدة من المورد"
                      : payment.bankSwiftImage
                        ? "تم الدفع"
                        : "مطالبة"}
                </div>

                {payment.isPosted && showManagerUnpost && (
                  <button
                    type="button"
                    className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
                    title="يزيل قيد اليومية ويعيد الدفعة لقابلة للتعديل"
                    onClick={() => {
                      if (
                        !window.confirm(
                          "إلغاء الترحيل المحاسبي لهذه الدفعة؟\n\n" +
                            "• يُنشأ قيد عكسي مرحّل (مدين/دائن معكوس) فيُحدَّث ميزان المراجعة والأستاذ العام بشكل صحيح.\n" +
                            "• القيد الأصلي يُبقى في النظام لكن يصبح غير مرحّل للتدقيق.\n" +
                            "• يمكنك بعدها تصحيح النسب/المبالغ وحفظ الصفقة.\n" +
                            "• الخادم يقبل مدير التطبيق (دور manager) أو حساب Django Staff.\n\n" +
                            "متابعة؟"
                        )
                      ) {
                        return;
                      }
                      onPaymentOperation("unpost", payment.type, {}, payment.id);
                    }}
                  >
                    <RotateCcw className="w-4 h-4" />
                    إلغاء الترحيل (مدير)
                  </button>
                )}

                {deletable && (
                  <button
                    type="button"
                    className="inline-flex items-center justify-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-100 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200 dark:hover:bg-red-900/30"
                    onClick={() => {
                      if (
                        !window.confirm(
                          `حذف الدفعة «${payment.type}» بمبلغ $${payment.amount?.toLocaleString()} من السجل؟`
                        )
                      )
                        return;
                      onPaymentOperation(
                        "cancel",
                        payment.type,
                        {},
                        payment.id
                      );
                    }}
                  >
                    <Trash2 className="w-4 h-4" />
                    حذف من السجل
                  </button>
                )}

              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-gray-500">الدفعة:</span>
                <span className="font-medium mr-2">
                  {payment.installmentNumber
                    ? `دفعة ${payment.installmentNumber}`
                    : "عام"}
                </span>
              </div>
              <div>
                <span className="text-gray-500">المورد:</span>
                <span
                  className={`font-medium mr-2 ${
                    paymentSettled(payment)
                      ? "text-green-600 dark:text-green-400"
                      : "text-yellow-600 dark:text-yellow-400"
                  }`}
                >
                  {paymentSettled(payment) ? "مكتمل" : "بانتظار"}
                </span>
              </div>
            </div>

            {deal.id &&
              payment.confirmedBySupplier &&
              !payment.isPosted && (
                <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs dark:border-slate-600 dark:bg-slate-900/40">
                  <HelpCircle className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                  <span className="text-slate-600 dark:text-slate-300">
                    تأكيد المورد محفوظ — الترحيل يدوي من دفتر اليومية؛ افتح قيداً جديداً أو أكمل القيد الذي بدأته (مدين مورد / دائن صندوق).
                  </span>
                  <button
                    type="button"
                    className="rounded border border-slate-300 bg-white px-2 py-1 font-medium text-slate-800 hover:bg-slate-100 dark:border-slate-500 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
                    onClick={async () => {
                      try {
                        const d = await dealsService.getPaymentPostingDiagnostics(
                          String(deal.id),
                          String(payment.id)
                        );
                        const lines =
                          d.blockers?.length > 0
                            ? d.blockers
                                .map((b, i) => `${i + 1}. ${b}`)
                                .join("\n\n")
                            : d.can_auto_post
                              ? "الشروط تبدو مستوفاة على الخادم؛ جرّب إعادة تحميل الصفقة. إن استمرت المشكلة راجع سجل الخادم (أخطاء ترحيل الدفعة)."
                              : "لم يُرجع الخادم تفاصيل؛ تحقق من ربط المورد والصندوق في المحاسبة.";
                        window.alert(
                          `شرح عدم الترحيل التلقائي (من الخادم):\n\n${lines}`
                        );
                      } catch {
                        window.alert(
                          "تعذّر جلب التشخيص من الخادم. تحقق من الاتصال ومسار واجهة الـ API."
                        );
                      }
                    }}
                  >
                    شرح عدم الترحيل
                  </button>
                  {!hasJournalId && (
                    <button
                      type="button"
                      className="rounded border border-blue-300 bg-blue-50 px-2 py-1 text-xs font-medium text-blue-900 hover:bg-blue-100 dark:border-blue-600 dark:bg-blue-950/40 dark:text-blue-100 dark:hover:bg-blue-900/30"
                      title="إن أنشأت قيداً يدوياً ولم يُربَط تلقائياً بالدفعة"
                      onClick={() => {
                        const raw = window.prompt(
                          "أدخل رقم قيد اليومية المرحّل (Journal ID) الظاهر في شاشة المحاسبة:",
                          ""
                        );
                        if (raw == null || String(raw).trim() === "") return;
                        const n = parseInt(String(raw).trim(), 10);
                        if (!Number.isFinite(n) || n <= 0) {
                          alert("أدخل رقماً صحيحاً.");
                          return;
                        }
                        onPaymentOperation(
                          "linkJournal",
                          payment.type,
                          { journalId: n },
                          payment.id
                        );
                      }}
                    >
                      ربط قيد يدوي
                    </button>
                  )}
                </div>
              )}

            {payment.isPosted && (
              <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50/80 px-3 py-2 text-sm dark:border-emerald-800 dark:bg-emerald-950/25">
                <div className="flex flex-wrap items-center gap-2">
                  <BookOpen className="w-4 h-4 text-emerald-700 dark:text-emerald-400 shrink-0" />
                  {hasJournalId ? (
                    <>
                      <span className="text-emerald-900 dark:text-emerald-100">
                        قيد محاسبي رقم{" "}
                        <span className="font-mono font-semibold">{jid}</span>
                      </span>
                      {onOpenAccountingJournal && (
                        <button
                          type="button"
                          className="rounded-md bg-emerald-700 px-2 py-1 text-xs font-medium text-white hover:bg-emerald-800 dark:bg-emerald-600 dark:hover:bg-emerald-500"
                          onClick={() => onOpenAccountingJournal(jid)}
                        >
                          فتح في المحاسبة
                        </button>
                      )}
                      {!onOpenAccountingJournal && (
                        <span className="text-xs text-emerald-800/80 dark:text-emerald-300/80">
                          من القائمة: محاسبة ← قيود اليومية ← ابحث برقم القيد.
                        </span>
                      )}
                    </>
                  ) : (
                    <span className="text-amber-900 dark:text-amber-100">
                      تم الترحيل لكن رقم القيد غير ظاهر في البيانات؛ أعد تحميل الصفقة أو افتح قيود اليومية وابحث بتاريخ الدفعة.
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
