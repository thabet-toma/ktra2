import React, { useState } from "react";
import {
  Calendar,
  Package,
  Truck,
  Factory,
  CheckCircle,
  Clock,
  AlertCircle,
  DollarSign,
  ChevronRight,
  ArrowRight,
  Users,
  Eye,
  FileText,
} from "lucide-react";

interface StageProps {
  data: any;
  setData: (data: any) => void;
  currentUser: { id: string; name: string; role: string };
  onStatusChange: (newStatus: string, notes?: string) => Promise<void>;
}

export const DealStageControl: React.FC<StageProps> = ({
  data,
  currentUser,
  onStatusChange,
}) => {
  const [showActionModal, setShowActionModal] = useState(false);
  const [selectedAction, setSelectedAction] = useState<any>(null);
  const [actionNotes, setActionNotes] = useState("");
  const [loading, setLoading] = useState(false);

  // تعريف حالات الصفقة (مبسطة)
  const statusConfig = {
    initial: {
      title: "مسودة",
      icon: <FileText className="w-6 h-6" />,
      color: "bg-gray-100 text-gray-800 border-gray-300",
      description: "تم إنشاء الصفقة، بانتظار بدء إجراءات الدفع",
      nextActions: [
        {
          id: "manufacturing_started",
          label: "بدء التصنيع",
          color: "bg-blue-600 hover:bg-blue-700",
          icon: <Factory className="w-5 h-5" />,
          description: "تأكيد بدء تصنيع المنتجات",
        },
      ],
    },
    first_payment_pending: {
      title: "إجراءات الدفع",
      icon: <DollarSign className="w-6 h-6" />,
      color: "bg-blue-100 text-blue-800 border-blue-300",
      description: "بانتظار إتمام الدفع وتأكيد المورد",
      nextActions: [
        {
          id: "manufacturing_started",
          label: "بدء التصنيع",
          color: "bg-blue-600 hover:bg-blue-700",
          icon: <Factory className="w-5 h-5" />,
          description: "تأكيد بدء تصنيع المنتجات بعد الدفع",
        },
      ],
    },
    first_payment_done: {
      title: "بانتظار تأكيد المورد",
      icon: <Clock className="w-6 h-6" />,
      color: "bg-indigo-100 text-indigo-800 border-indigo-300",
      description: "تم الدفع، بانتظار مراجعة المورد وتأكيد الاستلام",
      nextActions: [
        {
          id: "manufacturing_started",
          label: "بدء التصنيع",
          color: "bg-blue-600 hover:bg-blue-700",
          icon: <Factory className="w-5 h-5" />,
          description: "تأكيد بدء التصنيع بعد تأكيد المورد",
        },
      ],
    },
    manufacturing_started: {
      title: "قيد التصنيع",
      icon: <Factory className="w-6 h-6" />,
      color: "bg-orange-100 text-orange-800 border-orange-300",
      description: "الصفقة في مرحلة التصنيع",
      nextActions: [
        {
          id: "production_completed",
          label: "تم الانتهاء من التصنيع",
          color: "bg-purple-600 hover:bg-purple-700",
          icon: <CheckCircle className="w-5 h-5" />,
          description: "تأكيد الانتهاء من تصنيع جميع المنتجات",
        },
      ],
    },
    production_completed: {
      title: "تم التصنيع",
      icon: <CheckCircle className="w-6 h-6" />,
      color: "bg-purple-100 text-purple-800 border-purple-300",
      description: "تم الانتهاء من تصنيع جميع المنتجات",
      nextActions: [
        {
          id: "shipping_preparation",
          label: "بدء تجهيز الشحن",
          color: "bg-amber-600 hover:bg-amber-700",
          icon: <Package className="w-5 h-5" />,
          description: "البدء في تجهيز المنتجات للشحن",
        },
      ],
    },
    shipping_preparation: {
      title: "تجهيز الشحن",
      icon: <Package className="w-6 h-6" />,
      color: "bg-amber-100 text-amber-800 border-amber-300",
      description: "يتم الآن تجهيز البضائع للشحن",
      nextActions: [
        {
          id: "shipping_in_progress",
          label: "بدء الشحن",
          color: "bg-teal-600 hover:bg-teal-700",
          icon: <Truck className="w-5 h-5" />,
          description: "تأكيد بدء عملية الشحن",
        },
      ],
    },
    shipping_in_progress: {
      title: "جاري الشحن",
      icon: <Truck className="w-6 h-6" />,
      color: "bg-teal-100 text-teal-800 border-teal-300",
      description: "الشحنة في طريقها إليك",
      nextActions: [
        {
          id: "shipped",
          label: "تم الشحن",
          color: "bg-green-600 hover:bg-green-700",
          icon: <CheckCircle className="w-5 h-5" />,
          description: "تأكيد إتمام عملية الشحن",
        },
      ],
    },
    shipped: {
      title: "تم الشحن (مكتملة)",
      icon: <CheckCircle className="w-6 h-6 text-green-500" />,
      color: "bg-green-100 text-green-800 border-green-300",
      description: "تم شحن المنتجات بنجاح - الصفقة مكتملة",
      nextActions: [], // لا إجراءات بعد الاكتمال
    },
    cancelled: {
      title: "ملغاة",
      icon: <AlertCircle className="w-6 h-6" />,
      color: "bg-red-100 text-red-800 border-red-300",
      description: "تم إلغاء الصفقة",
      nextActions: [],
    },
  };

  const currentStatus = data.status || "initial";
  const config =
    statusConfig[currentStatus as keyof typeof statusConfig] ||
    statusConfig.initial;

  // تتبع مراحل التقدم (مبسطة)
  const progressStages = [
    { id: "initial", label: "مسودة" },
    { id: "manufacturing", label: "التصنيع" },
    { id: "preparing", label: "التجهيز" },
    { id: "shipping", label: "الشحن" },
    { id: "completed", label: "مكتملة" },
  ];

  const getStageIndex = (status: string) => {
    if (status === "shipped") return 4; // أصبحت مكتملة
    if (status === "shipping_in_progress") return 3;
    if (status === "shipping_preparation") return 2;
    if (status === "production_completed") return 2;
    if (status === "manufacturing_started") return 1;
    if (status === "first_payment_pending" || status === "first_payment_done")
      return 1;
    return 0;
  };

  const currentStageIndex = getStageIndex(currentStatus);
  const progressPercentage =
    (currentStageIndex / (progressStages.length - 1)) * 100;

  const handleActionClick = (action: any) => {
    setSelectedAction(action);
    setShowActionModal(true);
  };

  const handleConfirmAction = async () => {
    if (!selectedAction) return;

    try {
      setLoading(true);
      await onStatusChange(selectedAction.id, actionNotes);
      setShowActionModal(false);
      setSelectedAction(null);
      setActionNotes("");
    } catch (error) {
      console.error("Error changing status:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleCancelDeal = async () => {
    if (window.confirm("هل أنت متأكد من إلغاء هذه الصفقة؟")) {
      await onStatusChange("cancelled", "تم إلغاء الصفقة بواسطة المستخدم");
    }
  };

  // إذا كانت الصفقة ملغاة أو مكتملة
  if (currentStatus === "cancelled" || currentStatus === "shipped") {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <div className={`p-4 rounded-xl ${config.color}`}>
              {config.icon}
            </div>
            <div>
              <h3 className="text-xl font-bold text-gray-900 dark:text-white">
                {config.title}
              </h3>
              <p className="text-gray-600 dark:text-gray-400">
                {config.description}
              </p>
            </div>
          </div>
          <div className="text-sm text-gray-500">
            {new Date(data.updatedAt || data.createdAt).toLocaleDateString(
              "ar-EG"
            )}
          </div>
        </div>

        <div className="bg-gray-50 dark:bg-gray-900/50 p-4 rounded-lg">
          <p className="text-gray-700 dark:text-gray-300">
            {currentStatus === "shipped"
              ? "✅ تم إتمام الصفقة بنجاح. المنتجات تم شحنها بنجاح."
              : "❌ تم إلغاء الصفقة. لمزيد من التفاصيل راجع سجل النشاطات."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6">
        {/* الهيدر */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
          <div className="flex items-center gap-4">
            <div className={`p-4 rounded-xl ${config.color}`}>
              {config.icon}
            </div>
            <div>
              <h3 className="text-xl font-bold text-gray-900 dark:text-white">
                {config.title}
              </h3>
              <p className="text-gray-600 dark:text-gray-400">
                {config.description}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="text-sm text-gray-500">
              آخر تحديث:{" "}
              {new Date(data.updatedAt || data.createdAt).toLocaleDateString(
                "ar-EG"
              )}
            </div>
            <div
              className={`px-3 py-1 rounded-full ${config.color} text-sm font-medium`}
            >
              {config.title}
            </div>
          </div>
        </div>

        {/* شريط التقدم */}
        <div className="mb-8">
          <div className="flex justify-between items-center mb-2">
            <h4 className="font-bold text-gray-900 dark:text-white">
              تقدم الصفقة
            </h4>
            <span className="text-sm text-gray-500">
              {Math.round(progressPercentage)}%
            </span>
          </div>
          <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-600 transition-all duration-300"
              style={{ width: `${progressPercentage}%` }}
            />
          </div>
          <div className="flex justify-between mt-2">
            {progressStages.map((stage, index) => (
              <div
                key={stage.id}
                className={`text-xs ${
                  index <= currentStageIndex
                    ? "text-blue-600 font-bold"
                    : "text-gray-400"
                }`}
              >
                {stage.label}
              </div>
            ))}
          </div>
        </div>

        {/* الإجراءات المتاحة */}
        {config.nextActions.length > 0 && (
          <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
            <h4 className="font-bold text-gray-900 dark:text-white mb-4">
              الإجراءات المتاحة:
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {config.nextActions.map((action) => (
                <button
                  key={action.id}
                  onClick={() => handleActionClick(action)}
                  className={`p-4 rounded-lg text-white ${action.color} transition-all hover:shadow-lg hover:scale-[1.02] flex flex-col items-start gap-3`}
                >
                  <div className="flex items-center gap-2">
                    {action.icon}
                    <span className="font-bold">{action.label}</span>
                  </div>
                  <p className="text-sm text-white/80 text-right">
                    {action.description}
                  </p>
                  <div className="flex items-center gap-1 text-xs opacity-75">
                    <ArrowRight className="w-3 h-3" />
                    انقر للتنفيذ
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* زر الإلغاء */}
        {currentStatus !== "cancelled" && currentStatus !== "shipped" && (
          <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
            <button
              onClick={handleCancelDeal}
              className="px-6 py-3 bg-red-600 hover:bg-red-700 text-white font-medium rounded-lg transition-colors flex items-center gap-2"
            >
              <AlertCircle className="w-5 h-5" />
              إلغاء الصفقة
            </button>
            <p className="text-xs text-gray-500 mt-2">
              سيتم إلغاء الصفقة مع الاحتفاظ بجميع السجلات
            </p>
          </div>
        )}
      </div>

      {/* Modal تأكيد الإجراء */}
      {showActionModal && selectedAction && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-w-md w-full p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                {selectedAction.icon}
              </div>
              <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                {selectedAction.label}
              </h3>
            </div>

            <p className="text-gray-600 dark:text-gray-400 mb-6">
              {selectedAction.description}
            </p>

            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                ملاحظات إضافية (اختياري)
              </label>
              <textarea
                value={actionNotes}
                onChange={(e) => setActionNotes(e.target.value)}
                className="w-full p-3 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                rows={3}
                placeholder="أضف أي ملاحظات حول هذا الإجراء..."
              />
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowActionModal(false);
                  setSelectedAction(null);
                  setActionNotes("");
                }}
                className="flex-1 py-3 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                إلغاء
              </button>
              <button
                onClick={handleConfirmAction}
                disabled={loading}
                className="flex-1 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {loading ? (
                  <>
                    <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    جاري التنفيذ...
                  </>
                ) : (
                  <>
                    <CheckCircle className="w-5 h-5" />
                    تأكيد التنفيذ
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
