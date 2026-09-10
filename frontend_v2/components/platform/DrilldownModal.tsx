import React, { useEffect, useState } from "react";
import { formatDateTimeValue } from "../../utils/formatDate.ts";
import {
  getScopedWorkOrders,
  WorkOrderDrilldownFilter,
  WorkOrderRow,
} from "../../services/platformOpsApi";

interface DrilldownModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  initialFilter: WorkOrderDrilldownFilter;
}

export const DrilldownModal: React.FC<DrilldownModalProps> = ({
  isOpen,
  onClose,
  title,
  initialFilter,
}) => {
  const [workOrders, setWorkOrders] = useState<WorkOrderRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>(initialFilter.status || "");

  useEffect(() => {
    if (!isOpen) return;

    let isMounted = true;
    setLoading(true);

    const filterToApply: WorkOrderDrilldownFilter = {
      ...initialFilter,
      status: statusFilter || undefined,
    };

    getScopedWorkOrders(filterToApply)
      .then((res) => {
        if (!isMounted) return;
        const rows = Array.isArray(res) ? res : res.results || [];
        setWorkOrders(rows);
      })
      .catch(() => {
        if (!isMounted) return;
        setWorkOrders([]);
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, initialFilter, statusFilter]);

  if (!isOpen) return null;

  const filteredOrders = workOrders.filter((wo) => {
    if (!searchTerm.trim()) return true;
    const term = searchTerm.toLowerCase();
    return (
      wo.title?.toLowerCase().includes(term) ||
      wo.company_name?.toLowerCase().includes(term) ||
      wo.assignee_name?.toLowerCase().includes(term) ||
      wo.kind_display?.toLowerCase().includes(term)
    );
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4 overflow-y-auto" dir="rtl">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* شريط العنوان */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
          <div>
            <h3 className="text-lg font-bold text-slate-900">{title}</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              تنقيب أوامر العمل المنصية ضمن النطاق المصرح به تلقائياً (الشركات مشتقة خادمياً)
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 p-2 rounded-lg hover:bg-slate-200 transition"
          >
            <span className="sr-only">إغلاق</span>
            ✕
          </button>
        </div>

        {/* أدوات البحث والفلترة */}
        <div className="p-4 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3 bg-white">
          <div className="flex-1 min-w-[240px]">
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="البحث بالاسم أو الشركة أو الموظف..."
              className="w-full px-3.5 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-600 font-medium">الحالة:</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">كافة الحالات</option>
              <option value="received">مستلم</option>
              <option value="screening">قيد الفرز</option>
              <option value="data_entry">قيد الإدخال</option>
              <option value="review">قيد المراجعة</option>
              <option value="approval">قيد الاعتماد</option>
              <option value="waiting_customer">بانتظار العميل</option>
              <option value="closed">مغلق</option>
              <option value="cancelled">ملغي</option>
            </select>
          </div>
        </div>

        {/* جدول أوامر العمل */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="py-16 text-center text-sm text-slate-400">جاري استرجاع أوامر العمل...</div>
          ) : filteredOrders.length === 0 ? (
            <div className="py-16 text-center text-sm text-slate-400">لا توجد أوامر عمل مطابقة لهذا الفلتر</div>
          ) : (
            <table className="w-full text-right text-sm">
              <thead className="text-xs text-slate-500 bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="px-3 py-2.5 font-semibold">المعرّف</th>
                  <th className="px-3 py-2.5 font-semibold">أمر العمل</th>
                  <th className="px-3 py-2.5 font-semibold">الشركة</th>
                  <th className="px-3 py-2.5 font-semibold">الموظف المسند</th>
                  <th className="px-3 py-2.5 font-semibold">النوع</th>
                  <th className="px-3 py-2.5 font-semibold">الحالة</th>
                  <th className="px-3 py-2.5 font-semibold">الأجل النهائي</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredOrders.map((wo) => {
                  const isOverdue =
                    wo.deadline_at &&
                    new Date(wo.deadline_at) < new Date() &&
                    !["closed", "cancelled", "approval"].includes(wo.status);

                  return (
                    <tr key={wo.id} className="hover:bg-slate-50/70 transition">
                      <td className="px-3 py-3 font-mono text-xs text-slate-400">#{wo.id}</td>
                      <td className="px-3 py-3 font-semibold text-slate-800 max-w-[200px] truncate">
                        {wo.title}
                      </td>
                      <td className="px-3 py-3 text-slate-600 truncate max-w-[150px]">
                        {wo.company_name}
                      </td>
                      <td className="px-3 py-3 text-slate-600">
                        {wo.assignee_name || <span className="text-slate-400">غير مسند</span>}
                      </td>
                      <td className="px-3 py-3 text-xs">
                        <span className="px-2 py-0.5 bg-slate-100 text-slate-700 rounded">
                          {wo.kind_display || wo.kind}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-xs">
                        <span
                          className={`px-2.5 py-0.5 rounded-full font-medium ${
                            wo.status === "closed"
                              ? "bg-slate-100 text-slate-700"
                              : wo.status === "cancelled"
                              ? "bg-rose-100 text-rose-700"
                              : "bg-blue-50 text-blue-700"
                          }`}
                        >
                          {wo.status_display || wo.status}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-xs">
                        {wo.deadline_at ? (
                          <div className="flex items-center gap-1.5">
                            <span className={isOverdue ? "text-rose-600 font-bold" : "text-slate-600"}>
                              {formatDateTimeValue(wo.deadline_at)}
                            </span>
                            {isOverdue && (
                              <span className="px-1.5 py-0.5 text-[10px] font-extrabold bg-rose-100 text-rose-700 rounded border border-rose-200">
                                متأخر
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-slate-400">بدون أجل</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* ذيل النموذج */}
        <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
          <span>إجمالي الصفوف المعروضة: {filteredOrders.length}</span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 font-medium rounded-lg transition"
          >
            إغلاق
          </button>
        </div>
      </div>
    </div>
  );
};
