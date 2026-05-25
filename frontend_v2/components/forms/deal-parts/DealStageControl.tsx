import React, { useState } from "react";
import {
  Factory,
  CheckCircle,
  AlertCircle,
  DollarSign,
  Truck,
  Package,
  Anchor,
  FileText,
  Ship,
} from "lucide-react";
import type { ShippingWorkflowStatus } from "@/types/deal";
import { SHIPPING_WORKFLOW_LABELS } from "@/utils/shippingWorkflowLabels";

const WF_LABELS: Record<string, string> = SHIPPING_WORKFLOW_LABELS;

const MANUAL_WF: { value: ShippingWorkflowStatus; label: string }[] = [
  { value: "sw_mfg_start", label: WF_LABELS.sw_mfg_start },
  { value: "sw_wait_agent_ship", label: WF_LABELS.sw_wait_agent_ship },
  { value: "sw_wait_intl_ship", label: WF_LABELS.sw_wait_intl_ship },
];

const AUTO_WF = new Set<ShippingWorkflowStatus>([
  "sw_wait_arrival",
  "sw_wait_clearance",
]);

interface StageProps {
  data: any;
  setData: (data: any) => void;
  currentUser: { id: string; name: string; role: string };
  onStatusChange: (newStatus: string, notes?: string) => Promise<void>;
  onShippingWorkflowChange: (code: ShippingWorkflowStatus) => Promise<void>;
}

/** ملخص مرحلة الدفع (عرض فقط — لا أزرار انتقال قديمة) */
const paymentPhaseCopy: Record<
  string,
  { title: string; description: string; icon: React.ReactNode; color: string }
> = {
  initial: {
    title: "مسودة / بداية الصفقة",
    description: "أكمل بيانات الصفقة والدفعات، ثم اختر مرحلة الشحن من القائمة أدناه.",
    icon: <FileText className="w-6 h-6" />,
    color: "bg-gray-100 text-gray-800 border-gray-300",
  },
  first_payment_pending: {
    title: "إجراءات الدفع",
    description: "بانتظار الدفع وتأكيد المورد. يمكنك تحديد مرحلة الشحن/التصنيع من القائمة عند الجاهزية.",
    icon: <DollarSign className="w-6 h-6" />,
    color: "bg-blue-100 text-blue-800 border-blue-300",
  },
  first_payment_done: {
    title: "بانتظار تأكيد المورد",
    description: "تم الدفع. بعد التأكيد، حدّث مرحلة الشحن من القائمة.",
    icon: <DollarSign className="w-6 h-6" />,
    color: "bg-[var(--color-surface-2)] text-[var(--color-primary)] border-[var(--color-border)]",
  },
  first_payment_confirmed: {
    title: "تم تأكيد المورد",
    description: "يمكنك متابعة مراحل الشحن من القائمة أدناه.",
    icon: <CheckCircle className="w-6 h-6" />,
    color: "bg-emerald-100 text-emerald-800 border-emerald-300",
  },
  second_payment_pending: {
    title: "دفعة لاحقة",
    description: "متابعة الدفعات. مرحلة الشحن تُدار من القائمة.",
    icon: <DollarSign className="w-6 h-6" />,
    color: "bg-amber-100 text-amber-900 border-amber-300",
  },
  second_payment_done: {
    title: "دفعة لاحقة — بانتظار التأكيد",
    description: "متابعة الدفعات. مرحلة الشحن تُدار من القائمة.",
    icon: <DollarSign className="w-6 h-6" />,
    color: "bg-amber-100 text-amber-900 border-amber-300",
  },
  second_payment_confirmed: {
    title: "تم تأكيد دفعة لاحقة",
    description: "يمكنك متابعة مراحل الشحن من القائمة.",
    icon: <CheckCircle className="w-6 h-6" />,
    color: "bg-emerald-100 text-emerald-800 border-emerald-300",
  },
};

export const DealStageControl: React.FC<StageProps> = ({
  data,
  currentUser: _currentUser,
  onStatusChange,
  onShippingWorkflowChange,
}) => {
  const [wfLoading, setWfLoading] = useState(false);

  const currentStatus = data.status || "initial";
  const wf = (data.shippingWorkflowStatus || null) as ShippingWorkflowStatus | null;

  const paymentCopy =
    paymentPhaseCopy[currentStatus] || {
      title: "الصفقة",
      description: "اختر مرحلة الشحن والتصنيع من القائمة.",
      icon: <Package className="w-6 h-6" />,
      color: "bg-slate-100 text-slate-800 border-slate-300",
    };

  const handleCancelDeal = async () => {
    if (window.confirm("هل أنت متأكد من إلغاء هذه الصفقة؟")) {
      await onStatusChange("cancelled", "تم إلغاء الصفقة بواسطة المستخدم");
    }
  };

  const handleWfSelect = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const v = e.target.value as ShippingWorkflowStatus;
    if (!v || !data.id) return;
    try {
      setWfLoading(true);
      await onShippingWorkflowChange(v);
    } catch (err) {
      // console suppressed
    } finally {
      setWfLoading(false);
    }
  };

  if (currentStatus === "cancelled") {
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

  const isReleased =
    wf === "sw_released" ||
    data.status === "shipped" ||
    data.status === "completed";

  if (isReleased) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center gap-4">
          <div className="p-4 rounded-xl bg-green-100 text-green-800 border border-green-300">
            <CheckCircle className="w-6 h-6 text-green-600" />
          </div>
          <div>
            <h3 className="text-xl font-bold text-gray-900 dark:text-white">
              {wf === "sw_released" ? WF_LABELS.sw_released : "مكتملة"}
            </h3>
            <p className="text-gray-600 dark:text-gray-400">
              {wf === "sw_released"
                ? "تم حفظ فاتورة مرتبطة أو إكمال الإجراءات — الحالة: مفرج عنها."
                : "تم إغلاق/شحن الصفقة حسب النظام السابق."}
            </p>
          </div>
        </div>
      </div>
    );
  }

  const isAuto = wf != null && AUTO_WF.has(wf);
  const wfProgress = [
    { id: "m", label: "تصنيع/وكيل", icon: Factory },
    { id: "i", label: "شحن دولي", icon: Ship },
    { id: "a", label: "وصول", icon: Anchor },
    { id: "c", label: "تخليص", icon: FileText },
    { id: "r", label: "إفراج", icon: CheckCircle },
  ];
  let stepIdx = 0;
  if (wf === "sw_mfg_start") stepIdx = 0;
  else if (wf === "sw_wait_agent_ship") stepIdx = 0;
  else if (wf === "sw_wait_intl_ship") stepIdx = 1;
  else if (wf === "sw_wait_arrival") stepIdx = 2;
  else if (wf === "sw_wait_clearance") stepIdx = 3;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6 space-y-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className={`p-4 rounded-xl border ${paymentCopy.color}`}>{paymentCopy.icon}</div>
          <div>
            <h3 className="text-xl font-bold text-gray-900 dark:text-white">{paymentCopy.title}</h3>
            <p className="text-gray-600 dark:text-gray-400 text-sm">{paymentCopy.description}</p>
          </div>
        </div>
        <div className="text-xs text-gray-500">
          آخر تحديث:{" "}
          {new Date(data.updatedAt || data.createdAt).toLocaleDateString("ar-EG")}
        </div>
      </div>

      <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
        <h4 className="font-bold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
          <Truck className="w-5 h-5 text-blue-600" />
          مسار الشحن والتصنيع
        </h4>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          اختر واحدة من المراحل الثلاث الأولى يدوياً. عند ربط الصفقة بشحنة تتحدّث تلقائياً إلى «بانتظار وصول الشحنة»، وعند تسجيل تخليص جمركي للشحنة
          إلى «بانتظار إجراءات التخليص»، وعند حفظ فاتورة مرتبطة بالصفقة إلى «مفرج عنها».
        </p>

        <div className="mb-6">
          <div className="flex justify-between mb-2">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">التقدم</span>
          </div>
          <div className="flex justify-between gap-1">
            {wfProgress.map((s, i) => {
              const Icon = s.icon;
              const active = i <= stepIdx;
              return (
                <div
                  key={s.id}
                  className={`flex-1 flex flex-col items-center gap-1 ${active ? "text-blue-600" : "text-gray-300"}`}
                >
                  <Icon className="w-5 h-5" />
                  <span className="text-[10px] text-center leading-tight">{s.label}</span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="space-y-3">
          <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300">
            المرحلة الحالية (اختيار يدوي للمراحل الثلاث الأولى)
          </label>

          {isAuto && wf ? (
            <div className="rounded-lg border border-blue-200 bg-blue-50 dark:bg-blue-900/20 dark:border-blue-800 p-4">
              <p className="font-bold text-blue-900 dark:text-blue-200">{WF_LABELS[wf]}</p>
              <p className="text-sm text-blue-800/80 dark:text-blue-300/90 mt-1">
                تم ضبط هذه المرحلة تلقائياً من النظام (شحنة أو تخليص). لا يمكن تغييرها من هنا حتى تكتمل الخطوة التالية.
              </p>
            </div>
          ) : (
            <select
              value={wf || ""}
              onChange={handleWfSelect}
              disabled={wfLoading || !data.id}
              className="w-full max-w-xl h-12 px-4 rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm font-medium focus:ring-2 focus:ring-blue-500"
            >
              <option value="">— اختر المرحلة —</option>
              {MANUAL_WF.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          )}

          {wf && !isAuto && (
            <p className="text-xs text-gray-500">
              المعروض: <span className="font-medium text-gray-700 dark:text-gray-300">{WF_LABELS[wf]}</span>
            </p>
          )}

          {!data.id && (
            <p className="text-xs text-gray-500 dark:text-gray-400">احفظ الصفقة أولاً لتفعيل اختيار مرحلة الشحن.</p>
          )}
        </div>
      </div>

      <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
        <button
          type="button"
          onClick={handleCancelDeal}
          className="px-6 py-3 bg-red-600 hover:bg-red-700 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
        >
          <AlertCircle className="w-5 h-5" />
          إلغاء الصفقة
        </button>
        <p className="text-xs text-gray-500 mt-2">سيتم الإلغاء مع الاحتفاظ بالسجلات.</p>
      </div>
    </div>
  );
};
