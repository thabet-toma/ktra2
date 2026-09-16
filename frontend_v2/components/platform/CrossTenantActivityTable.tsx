import React, { useEffect, useState } from "react";
import { formatDateTimeValue } from "../../utils/formatDate.ts";
import { formatNumber } from "../../utils/formatNumber";
import {
  getEmployeeActivity,
  getPlatformActivityLogs,
  PlatformActivityLog,
} from "../../services/platformOpsApi";
import { CcEmpty, CcPill, CcSkeleton, CcTable, CcTd, CcTh, CcThead, CcTr } from "./ui";

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
}: CrossTenantActivityTableProps) => {
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 overflow-y-auto" dir="rtl">
      <div className="bg-cc-surface rounded-2xl shadow-cc-card border border-cc-border w-full max-w-5xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* شريط العنوان */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-cc-border bg-cc-surface-2">
          <div>
            <h3 className="text-base sm:text-lg font-bold text-cc-text">
              {employeeName
                ? `سجل النشاط العابر للشركات — ${employeeName}`
                : "سجل نشاط عمليات المنصة العابر للشركات"}
            </h3>
            <p className="text-xs text-cc-text-muted mt-0.5">
              سجل مستقل بالكامل (PlatformActivityLog) يعبر الشركات زمنياً دون المساس بجدول ActivityLog المستأجر
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-cc-text-muted hover:text-cc-text p-2 rounded-lg hover:bg-cc-surface transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
          >
            ✕
          </button>
        </div>

        {/* الجدول */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="p-8 space-y-3">
              <CcSkeleton variant="line" count={5} />
            </div>
          ) : logs.length === 0 ? (
            <CcEmpty
              title="لا يوجد نشاط مسجل حتى الآن"
              hint="لم يتم رصد أي عمليات عابرة للشركات في هذه الفترة."
            />
          ) : (
            <CcTable>
              <CcThead>
                <tr>
                  <CcTh>التوقيت</CcTh>
                  <CcTh>الموظف</CcTh>
                  <CcTh>الشركة</CcTh>
                  <CcTh>الحدث</CcTh>
                  <CcTh>الوصف</CcTh>
                  <CcTh>الكيان</CcTh>
                </tr>
              </CcThead>
              <tbody>
                {logs.map((log) => (
                  <CcTr key={log.id}>
                    <CcTd className="text-xs text-cc-text-muted whitespace-nowrap">
                      {formatDateTimeValue(log.created_at)}
                    </CcTd>
                    <CcTd className="font-semibold text-cc-text whitespace-nowrap">
                      {log.employee_name}
                    </CcTd>
                    <CcTd>
                      {log.company_name ? (
                        <CcPill tone="neutral">
                          {log.company_name}
                        </CcPill>
                      ) : (
                        <span className="text-xs text-cc-text-muted">نشاط عام للمنصة</span>
                      )}
                    </CcTd>
                    <CcTd className="text-xs">
                      <span className="font-mono text-sky-400 bg-sky-500/10 px-1.5 py-0.5 rounded border border-sky-500/20">
                        {log.action_display || log.action}
                      </span>
                    </CcTd>
                    <CcTd className="text-cc-text max-w-[280px]">
                      {log.description}
                    </CcTd>
                    <CcTd className="text-xs text-cc-text-muted whitespace-nowrap">
                      {log.entity_type} {log.entity_id ? `#${log.entity_id}` : ""}
                    </CcTd>
                  </CcTr>
                ))}
              </tbody>
            </CcTable>
          )}
        </div>

        {/* الذيل */}
        <div className="px-6 py-3 border-t border-cc-border bg-cc-surface-2 flex items-center justify-between text-xs text-cc-text-muted">
          <span>عدد الأنشطة: {formatNumber(logs.length)}</span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 bg-cc-surface hover:bg-cc-surface-2 text-cc-text border border-cc-border font-medium rounded-lg transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
          >
            إغلاق
          </button>
        </div>
      </div>
    </div>
  );
};

