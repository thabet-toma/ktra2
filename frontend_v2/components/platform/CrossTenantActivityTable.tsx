import React, { useEffect, useState } from "react";
import { formatDateTimeValue } from "../../utils/formatDate.ts";
import {
  getEmployeeActivity,
  getPlatformActivityLogs,
  PlatformActivityLog,
} from "../../services/platformOpsApi";

interface CrossTenantActivityTableProps {
  isOpen: boolean;
  onClose: () => void;
  employeeId?: number | null;
  employeeName?: string | null;
}

export const CrossTenantActivityTable: React.FC<CrossTenantActivityTableProps> = ({
  isOpen,
  onClose,
  employeeId,
  employeeName,
}) => {
  const [logs, setLogs] = useState<PlatformActivityLog[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    if (!isOpen) return;

    let isMounted = true;
    setLoading(true);

    const request = employeeId
      ? getEmployeeActivity(employeeId)
      : getPlatformActivityLogs();

    request
      .then((res) => {
        if (!isMounted) return;
        const items = Array.isArray(res) ? res : res.results || [];
        setLogs(items);
      })
      .catch(() => {
        if (!isMounted) return;
        setLogs([]);
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, employeeId]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4 overflow-y-auto" dir="rtl">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-5xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* شريط العنوان */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
          <div>
            <h3 className="text-lg font-bold text-slate-900">
              {employeeName
                ? `سجل النشاط العابر للشركات — ${employeeName}`
                : "سجل نشاط عمليات المنصة العابر للشركات"}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              سجل مستقل بالكامل (PlatformActivityLog) يعبر الشركات زمنياً دون المساس بجدول ActivityLog المستأجر
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 p-2 rounded-lg hover:bg-slate-200 transition"
          >
            ✕
          </button>
        </div>

        {/* الجدول */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="py-16 text-center text-sm text-slate-400">جاري تحميل سجل النشاط...</div>
          ) : logs.length === 0 ? (
            <div className="py-16 text-center text-sm text-slate-400">لا يوجد نشاط مسجل حتى الآن</div>
          ) : (
            <table className="w-full text-right text-sm">
              <thead className="text-xs text-slate-500 bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="px-3 py-2.5 font-semibold">التوقيت</th>
                  <th className="px-3 py-2.5 font-semibold">الموظف</th>
                  <th className="px-3 py-2.5 font-semibold">الشركة</th>
                  <th className="px-3 py-2.5 font-semibold">الحدث</th>
                  <th className="px-3 py-2.5 font-semibold">الوصف</th>
                  <th className="px-3 py-2.5 font-semibold">الكيان</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {logs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-50/70 transition">
                    <td className="px-3 py-3 text-xs text-slate-500 whitespace-nowrap">
                      {formatDateTimeValue(log.created_at)}
                    </td>
                    <td className="px-3 py-3 font-semibold text-slate-800 whitespace-nowrap">
                      {log.employee_name}
                    </td>
                    <td className="px-3 py-3 text-slate-600">
                      {log.company_name ? (
                        <span className="px-2 py-0.5 bg-slate-100 text-slate-700 rounded text-xs">
                          {log.company_name}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-400">نشاط عام للمنصة</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-xs">
                      <span className="font-mono text-slate-500">{log.action_display || log.action}</span>
                    </td>
                    <td className="px-3 py-3 text-slate-700 max-w-[280px]">
                      {log.description}
                    </td>
                    <td className="px-3 py-3 text-xs text-slate-400 whitespace-nowrap">
                      {log.entity_type} {log.entity_id ? `#${log.entity_id}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* الذيل */}
        <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
          <span>عدد الأنشطة: {logs.length}</span>
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
