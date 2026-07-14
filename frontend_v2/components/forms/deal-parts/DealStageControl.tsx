import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Factory,
  CheckCircle,
  AlertCircle,
  Truck,
  Package,
  Anchor,
  Ship,
  ExternalLink,
  ArrowLeft,
  DollarSign,
} from "lucide-react";
import type { ShippingWorkflowStatus } from "@/types/deal";
import { SHIPPING_WORKFLOW_LABELS } from "@/utils/shippingWorkflowLabels";
import { useConfirm } from "@/contexts/ConfirmContext";
import { formatMoney } from "@/utils/formatNumber";

const WF_LABELS: Record<string, string> = SHIPPING_WORKFLOW_LABELS;

/** ترتيب المسار الكامل صفقة→فاتورة (ج7): الثلاث الأولى يدوية، والبقية
    يضبطها النظام (ضم لشحنة / تخليص / حفظ فاتورة مرتبطة). */
const JOURNEY: {
  code: ShippingWorkflowStatus;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  manual: boolean;
  autoHint?: string;
}[] = [
  { code: "sw_mfg_start", label: "بدء التصنيع", icon: Factory, manual: true },
  { code: "sw_wait_agent_ship", label: "تم التصنيع — بانتظار الشحن للوكيل", icon: Package, manual: true },
  { code: "sw_wait_intl_ship", label: "تم الشحن للوكيل", icon: Truck, manual: true },
  {
    code: "sw_wait_arrival", label: "الشحن الدولي — بانتظار الوصول", icon: Ship, manual: false,
    autoHint: "تلقائياً عند ضمّ الصفقة لشحنة في رحلة الاستيراد",
  },
  {
    code: "sw_wait_clearance", label: "التخليص الجمركي", icon: Anchor, manual: false,
    autoHint: "تلقائياً عند تسجيل تخليص جمركي للشحنة",
  },
  {
    code: "sw_released", label: "محوّلة إلى فاتورة (مفرج عنها)", icon: CheckCircle, manual: false,
    autoHint: "تلقائياً عند حفظ فاتورة شراء مرتبطة بالصفقة",
  },
];

const WF_ORDER: Record<string, number> = Object.fromEntries(
  JOURNEY.map((s, i) => [s.code, i])
);

interface StageProps {
  data: any;
  setData: (data: any) => void;
  currentUser: { id: string; name: string; role: string };
  onStatusChange: (newStatus: string, notes?: string) => Promise<void>;
  onShippingWorkflowChange: (code: ShippingWorkflowStatus) => Promise<void>;
}

/** حالة الدفع بُعد مالي مستقل عن مسار الشحن — تُعرض كشارة ولا تقفل المراحل. */
function paymentSummary(data: any): { label: string; cls: string } {
  const total = Number(data?.totalAmount || 0);
  const paid = (data?.payments || []).reduce(
    (s: number, p: any) => s + Number(p?.amount || 0),
    0
  );
  if (total <= 0 || paid <= 0)
    return { label: "غير مدفوعة", cls: "bg-gray-100 text-gray-700 border-gray-300 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-600" };
  if (paid >= total - 0.01)
    return { label: `مدفوعة كلياً — $${formatMoney(paid)}`, cls: "bg-emerald-50 text-emerald-800 border-emerald-300 dark:bg-emerald-900/20 dark:text-emerald-300 dark:border-emerald-800" };
  return {
    label: `مدفوعة جزئياً — $${formatMoney(paid)} من $${formatMoney(total)}`,
    cls: "bg-amber-50 text-amber-900 border-amber-300 dark:bg-amber-900/20 dark:text-amber-300 dark:border-amber-800",
  };
}

export const DealStageControl: React.FC<StageProps> = ({
  data,
  currentUser: _currentUser,
  onStatusChange,
  onShippingWorkflowChange,
}) => {
  const confirm = useConfirm();
  const navigate = useNavigate();
  const [wfLoading, setWfLoading] = useState(false);

  const wf = (data.shippingWorkflowStatus || null) as ShippingWorkflowStatus | null;
  const isCancelled = data.status === "cancelled";
  const isReleased = wf === "sw_released";
  const currentIdx = wf ? (WF_ORDER[wf] ?? -1) : -1;
  const inAutoPhase = currentIdx >= WF_ORDER.sw_wait_arrival;
  const pay = paymentSummary(data);
  const shipment = data.linkedShipment || null;

  /* ج8 (M5): «الخطوة التالية» — زر واحد يقود الرحلة من الصفقة للأمام دون أن
     يبحث المستخدم عن الشاشة. بلا شحنة: يفتح رحلة استيراد جديدة مع فاتح ضمّ
     الصفقة جاهزاً. مع شحنة: يقفز لتبويب الإجراء التالي (تخليص/الحسابات). */
  const nextStep: { label: string; hint: string; go: () => void } | null =
    isReleased || isCancelled || !data.id
      ? null
      : shipment
        ? {
            label: `متابعة رحلة الاستيراد — ${shipment.shipmentName || shipment.shipmentNumber || `#${shipment.id}`}`,
            hint:
              currentIdx >= WF_ORDER.sw_wait_clearance
                ? "أكمل التخليص ثم حوّل إلى فاتورة شراء دولية."
                : "تابع الشحن الدولي والتخليص حتى تحويلها إلى فاتورة.",
            go: () => {
              const tab =
                currentIdx >= WF_ORDER.sw_wait_clearance ? "clearance" : "deals";
              navigate(`/import-flow/${shipment.id}?tab=${tab}`);
            },
          }
        : {
            label: "ابدأ الشحن الدولي — اضمم الصفقة إلى شحنة",
            hint: "تُفتح رحلة استيراد جديدة وفاتح ضمّ الصفقات جاهز — اختر هذه الصفقة.",
            go: () =>
              navigate(
                `/import-flow/new?tab=deals&join_deal=${encodeURIComponent(String(data.id))}`
              ),
          };

  const handleCancelDeal = async () => {
    const ok = await confirm({
      title: "إلغاء الصفقة",
      message: "هل أنت متأكد من إلغاء هذه الصفقة؟ سيتم الاحتفاظ بالسجلات والدفعات المرحّلة كما هي.",
      danger: true,
      confirmText: "إلغاء الصفقة",
    });
    if (ok) await onStatusChange("cancelled", "تم إلغاء الصفقة بواسطة المستخدم");
  };

  const handleStageClick = async (code: ShippingWorkflowStatus) => {
    if (!data.id || wfLoading || code === wf) return;
    try {
      setWfLoading(true);
      await onShippingWorkflowChange(code);
    } finally {
      setWfLoading(false);
    }
  };

  if (isCancelled) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center gap-4">
          <div className="p-4 rounded-xl bg-red-100 text-red-800 border border-red-300">
            <AlertCircle className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-xl font-bold text-gray-900 dark:text-white">ملغاة</h3>
            <p className="text-gray-600 dark:text-gray-400">تم إلغاء الصفقة.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6 space-y-6">
      {/* حالتان مستقلتان: الدفع (مالي) × المرحلة (تشغيلي) */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-sm font-medium ${pay.cls}`}>
            <DollarSign className="w-4 h-4" />
            الدفع: {pay.label}
          </span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-sm font-medium bg-blue-50 text-blue-800 border-blue-300 dark:bg-blue-900/20 dark:text-blue-300 dark:border-blue-800">
            <Truck className="w-4 h-4" />
            المرحلة: {wf ? WF_LABELS[wf] : "لم تُحدد بعد"}
          </span>
        </div>
        <div className="text-xs text-gray-500">
          آخر تحديث:{" "}
          {new Date(data.updatedAt || data.createdAt).toLocaleDateString("ar-EG")}
        </div>
      </div>
      <p className="text-xs text-gray-500 dark:text-gray-400 -mt-3">
        حالة الدفع مستقلة عن مرحلة الشحن — الدفعات لا تمنع تقدّم المراحل، والمراحل لا تمنع الدفع.
      </p>

      {/* ج8 (M5): الخطوة التالية — CTA الرحلة الواحدة */}
      {nextStep && (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border-2 border-blue-300 dark:border-blue-700 bg-blue-50/70 dark:bg-blue-900/20 px-4 py-3">
          <div className="text-sm text-blue-900 dark:text-blue-100">
            <span className="font-bold block">الخطوة التالية</span>
            <span className="text-xs opacity-90">{nextStep.hint}</span>
          </div>
          <button
            type="button"
            onClick={nextStep.go}
            className="shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold shadow-sm shadow-blue-500/30"
          >
            {nextStep.label}
            <ArrowLeft className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* خريطة المسار الموحّدة صفقة → فاتورة */}
      <div className="border-t border-gray-200 dark:border-gray-700 pt-5">
        <h4 className="font-bold text-gray-900 dark:text-white mb-1 flex items-center gap-2">
          <Ship className="w-5 h-5 text-blue-600" />
          خريطة رحلة الاستيراد
        </h4>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          اضغط إحدى المراحل الثلاث الأولى لتحديدها يدوياً. المراحل التالية يضبطها
          النظام تلقائياً (ضمّ لشحنة ← تخليص ← نقل محلي اختياري ← فاتورة).
        </p>

        <ol className="space-y-2">
          {JOURNEY.map((step, i) => {
            const Icon = step.icon;
            const isDone = currentIdx > i || (isReleased && i <= currentIdx);
            const isCurrent = currentIdx === i;
            const clickable =
              step.manual && !inAutoPhase && !isReleased && !wfLoading && Boolean(data.id);
            const stateCls = isCurrent
              ? "border-blue-400 bg-blue-50 dark:bg-blue-900/20 dark:border-blue-700"
              : isDone
                ? "border-emerald-200 bg-emerald-50/60 dark:bg-emerald-900/10 dark:border-emerald-800"
                : "border-gray-200 dark:border-gray-700";
            return (
              <React.Fragment key={step.code}>
                {/* النقل المحلي: خطوة اختيارية تُدار من رحلة الاستيراد — قبل الفاتورة */}
                {step.code === "sw_released" && (
                  <li className="flex items-center gap-3 rounded-lg border border-dashed border-gray-300 dark:border-gray-600 px-3 py-2 opacity-80">
                    <Truck className="w-4 h-4 text-gray-400 shrink-0" />
                    <span className="text-sm text-gray-500 dark:text-gray-400">
                      النقل المحلي <span className="text-[11px]">(اختياري — يُدار من تبويب «النقل المحلي» في رحلة الاستيراد)</span>
                    </span>
                  </li>
                )}
                <li>
                  <button
                    type="button"
                    disabled={!clickable}
                    onClick={() => clickable && void handleStageClick(step.code)}
                    className={`w-full flex items-center gap-3 rounded-lg border px-3 py-2.5 text-right transition-colors ${stateCls} ${clickable ? "hover:border-blue-400 cursor-pointer" : "cursor-default"}`}
                    title={step.manual ? (clickable ? "اضغط لتحديد هذه المرحلة" : undefined) : step.autoHint}
                  >
                    <span className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center border ${isDone ? "bg-emerald-100 text-emerald-700 border-emerald-300" : isCurrent ? "bg-blue-100 text-blue-700 border-blue-300" : "bg-gray-50 text-gray-400 border-gray-200 dark:bg-gray-700 dark:border-gray-600"}`}>
                      {isDone ? <CheckCircle className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
                    </span>
                    <span className="flex-1">
                      <span className={`block text-sm font-semibold ${isCurrent ? "text-blue-900 dark:text-blue-200" : isDone ? "text-emerald-800 dark:text-emerald-300" : "text-gray-600 dark:text-gray-300"}`}>
                        {step.label}
                        {isCurrent && <span className="mr-2 text-[11px] font-normal">● الحالية</span>}
                      </span>
                      {!step.manual && !isDone && !isCurrent && (
                        <span className="block text-[11px] text-gray-400 mt-0.5">{step.autoHint}</span>
                      )}
                    </span>
                    {step.manual && !inAutoPhase && !isReleased && (
                      <span className="text-[10px] text-gray-400 border border-gray-200 dark:border-gray-600 rounded px-1.5 py-0.5 shrink-0">يدوي</span>
                    )}
                  </button>
                </li>
              </React.Fragment>
            );
          })}
        </ol>

        {!data.id && (
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-3">
            احفظ الصفقة أولاً لتفعيل اختيار مرحلة الشحن.
          </p>
        )}
        {inAutoPhase && !isReleased && (
          <p className="text-xs text-blue-700 dark:text-blue-300 mt-3">
            الصفقة الآن ضمن شحنة — المراحل التالية تتقدم تلقائياً من رحلة الاستيراد.
          </p>
        )}
      </div>

      {/* رابط رحلة الاستيراد للشحنة المرتبطة */}
      {shipment && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 px-4 py-3">
          <div className="text-sm text-blue-900 dark:text-blue-200">
            <span className="font-semibold">الشحنة المرتبطة: </span>
            {shipment.shipmentName || shipment.shipmentNumber || `#${shipment.id}`}
          </div>
          <button
            type="button"
            onClick={() => window.open(`/import-flow/${shipment.id}`, "_blank", "noopener,noreferrer")}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium"
          >
            <ExternalLink className="w-4 h-4" />
            فتح رحلة الاستيراد
          </button>
        </div>
      )}

      {isReleased ? (
        <div className="flex items-center gap-3 rounded-lg border border-emerald-300 bg-emerald-50 dark:bg-emerald-900/20 dark:border-emerald-800 px-4 py-3">
          <CheckCircle className="w-5 h-5 text-emerald-600 shrink-0" />
          <p className="text-sm text-emerald-900 dark:text-emerald-200">
            اكتملت الرحلة — الصفقة محوّلة إلى فاتورة شراء (مفرج عنها).
          </p>
        </div>
      ) : (
        <div className="pt-2 border-t border-gray-200 dark:border-gray-700">
          <button
            type="button"
            onClick={() => void handleCancelDeal()}
            className="px-6 py-3 bg-red-600 hover:bg-red-700 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
          >
            <AlertCircle className="w-5 h-5" />
            إلغاء الصفقة
          </button>
          <p className="text-xs text-gray-500 mt-2">
            الإلغاء متاح في أي مرحلة — يُحتفظ بالسجلات، ولا يمسّ القيود المرحّلة.
          </p>
        </div>
      )}
    </div>
  );
};
