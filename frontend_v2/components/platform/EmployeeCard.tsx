import React from "react";
import { PlatformDashboardEmployee } from "../../utils/dashboardRanking";
import { getLastActiveBadge } from "../../utils/lastActiveFormat";

interface EmployeeCardProps {
  employee: PlatformDashboardEmployee;
  onDrilldown: (filter: { assignee: number; metric?: "active" | "overdue"; status?: string }) => void;
  onViewActivity: (employeeId: number, employeeName: string) => void;
}

export const EmployeeCard: React.FC<EmployeeCardProps> = ({
  employee,
  onDrilldown,
  onViewActivity,
}) => {
  const lastActiveBadge = getLastActiveBadge(employee.last_active_at);
  const isOverloaded = employee.active_work_orders_count > employee.capacity_target;
  const hasOverdue = employee.overdue_work_orders_count > 0;
  const score = employee.performance?.composite_score;

  return (
    <div
      className={`bg-white rounded-xl border transition shadow-sm hover:shadow-md p-5 flex flex-col justify-between ${
        hasOverdue
          ? "border-rose-300 ring-1 ring-rose-200"
          : isOverloaded
          ? "border-orange-300 ring-1 ring-orange-200"
          : "border-slate-200"
      }`}
      dir="rtl"
    >
      {/* الرأس: اسم الموظف والتخصص وحالة النشاط */}
      <div>
        <div className="flex items-start justify-between gap-2 mb-2.5">
          <div className="flex-1 min-w-0">
            <h4 className="text-base font-bold text-slate-900 truncate">{employee.name}</h4>
            <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
              <span className="font-mono text-slate-400">@{employee.username}</span>
              <span>•</span>
              <span className="px-2 py-0.5 font-medium bg-slate-100 text-slate-700 rounded-md">
                {employee.specialty}
              </span>
            </div>
          </div>

          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full border ${lastActiveBadge.className}`}
          >
            {/* لا مصباحَ نابضاً: المواصفةُ أسقطته لأنّه «يَعِد بدقّةٍ لا يملكها
                النظام» — المصدرُ نافذةُ خمسِ دقائقَ على `UserDevice`. والنصُّ
                يحمل الساعةَ الحقيقيّةَ وهي أصدقُ من لون. */}
            {lastActiveBadge.label}
          </span>
        </div>

        {/* شبكة المقاييس والأرقام المنقور عليها (Drilldown) */}
        <div className="grid grid-cols-2 gap-2.5 my-4">
          <button
            type="button"
            onClick={() => onDrilldown({ assignee: employee.id, metric: "active" })}
            className="p-3 bg-slate-50 hover:bg-blue-50 border border-slate-200 hover:border-blue-300 rounded-lg text-right transition group"
          >
            <span className="text-xs text-slate-500 group-hover:text-blue-700 block">أوامر العمل النشطة</span>
            <div className="flex items-baseline justify-between mt-1">
              <span className="text-xl font-black text-slate-900 group-hover:text-blue-700">
                {employee.active_work_orders_count}
              </span>
              <span className="text-[11px] text-slate-400">
                الهدف: {employee.capacity_target}
              </span>
            </div>
          </button>

          <button
            type="button"
            onClick={() => onDrilldown({ assignee: employee.id, metric: "overdue" })}
            className={`p-3 rounded-lg text-right border transition group ${
              hasOverdue
                ? "bg-rose-50/80 hover:bg-rose-100/90 border-rose-200 hover:border-rose-300"
                : "bg-slate-50 hover:bg-slate-100 border-slate-200"
            }`}
          >
            <span
              className={`text-xs block ${
                hasOverdue ? "text-rose-700 font-bold" : "text-slate-500"
              }`}
            >
              أوامر متأخرة
            </span>
            <div className="flex items-baseline justify-between mt-1">
              <span
                className={`text-xl font-black ${
                  hasOverdue ? "text-rose-700" : "text-slate-700"
                }`}
              >
                {employee.overdue_work_orders_count}
              </span>
              {hasOverdue && (
                <span className="text-[10px] font-bold text-rose-600 bg-rose-200/70 px-1.5 py-0.5 rounded">
                  تأخر حرج
                </span>
              )}
            </div>
          </button>
        </div>

        {/* مؤشر الأداء والسعة */}
        <div className="space-y-2 bg-slate-50/70 p-3 rounded-lg border border-slate-100 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-slate-600">درجة الأداء المركبة:</span>
            {score !== null && score !== undefined ? (
              <span
                className={`font-bold ${
                  score >= 80
                    ? "text-emerald-700"
                    : score >= 60
                    ? "text-blue-700"
                    : "text-rose-700"
                }`}
              >
                {score}%
              </span>
            ) : (
              <span className="text-slate-400 font-medium">
                {employee.performance?.status_message || "بيانات غير كافية"}
              </span>
            )}
          </div>

          <div className="flex items-center justify-between">
            <span className="text-slate-600">حمل السعة:</span>
            <span
              className={`font-bold ${
                isOverloaded ? "text-orange-700" : "text-slate-700"
              }`}
            >
              {employee.active_work_orders_count} / {employee.capacity_target}
              {isOverloaded && " (حمل مفرط)"}
            </span>
          </div>
        </div>

        {/* الشركات المرتبطة */}
        {employee.companies && employee.companies.length > 0 && (
          <div className="mt-3">
            <span className="text-[11px] text-slate-500 block mb-1">الشركات المرتبطة ({employee.companies.length}):</span>
            <div className="flex flex-wrap gap-1">
              {employee.companies.slice(0, 3).map((comp) => (
                <span
                  key={comp.id}
                  className="px-2 py-0.5 text-[11px] bg-white text-slate-700 border border-slate-200 rounded"
                >
                  {comp.name}
                </span>
              ))}
              {employee.companies.length > 3 && (
                <span className="px-1.5 py-0.5 text-[10px] text-slate-400">
                  +{employee.companies.length - 3} أخرى
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* زر سجل النشاط العابر */}
      <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
        <button
          type="button"
          onClick={() => onViewActivity(employee.id, employee.name)}
          className="text-xs font-semibold text-blue-600 hover:text-blue-800 transition flex items-center gap-1"
        >
          <span>عرض سجل النشاط العابر للشركات</span>
          <span>←</span>
        </button>

        <button
          type="button"
          onClick={() => onDrilldown({ assignee: employee.id })}
          className="text-xs text-slate-500 hover:text-slate-800 transition"
        >
          كل الأوامر
        </button>
      </div>
    </div>
  );
};
