import React, { useState } from "react";
import { PlatformDashboardCompany } from "../../utils/dashboardRanking";
import { CompanyHealthPanel } from "./CompanyHealthPanel";
import { Activity, ChevronDown, ChevronUp } from "lucide-react";
import { formatNumber } from "../../utils/formatNumber";

interface CompanyCardProps {
  company: PlatformDashboardCompany;
  onDrilldown: (filter: { metric?: "active" | "overdue"; status?: string }) => void;
}

export const CompanyCard: React.FC<CompanyCardProps> = ({
  company,
  onDrilldown,
}) => {
  const [showHealth, setShowHealth] = useState<boolean>(false);
  const hasOverdue = company.overdue_work_orders_count > 0;

  return (
    <div
      className={`bg-white rounded-xl border transition shadow-sm hover:shadow-md p-5 flex flex-col justify-between ${
        hasOverdue ? "border-rose-300 ring-1 ring-rose-200" : "border-slate-200"
      }`}
      dir="rtl"
    >
      <div>
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex-1 min-w-0">
            <h4 className="text-base font-bold text-slate-900 truncate">{company.name}</h4>
            <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
              <span className="px-2 py-0.5 font-medium bg-slate-100 text-slate-700 rounded-md">
                الباقة: {company.subscription_plan || "غير محددة"}
              </span>
            </div>
          </div>

          <span
            className={`px-2.5 py-1 text-xs font-semibold rounded-full border ${
              company.subscription_status === "active"
                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                : "bg-amber-50 text-amber-700 border-amber-200"
            }`}
          >
            {company.subscription_status === "active" ? "اشتراك نشط" : company.subscription_status}
          </span>
        </div>

        {/* شبكة الأرقام المنقور عليها (Drilldown) */}
        <div className="grid grid-cols-2 gap-2.5 my-4">
          <button
            type="button"
            onClick={() => onDrilldown({ metric: "active" })}
            className="p-3 bg-slate-50 hover:bg-blue-50 border border-slate-200 hover:border-blue-300 rounded-lg text-right transition group"
          >
            <span className="text-xs text-slate-500 group-hover:text-blue-700 block">أوامر العمل النشطة</span>
            <div className="flex items-baseline justify-between mt-1">
              <span className="text-xl font-black text-slate-900 group-hover:text-blue-700">
                {formatNumber(company.active_work_orders_count)}
              </span>
            </div>
          </button>

          <button
            type="button"
            onClick={() => onDrilldown({ metric: "overdue" })}
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
                {formatNumber(company.overdue_work_orders_count)}
              </span>
              {hasOverdue && (
                <span className="text-[10px] font-bold text-rose-600 bg-rose-200/70 px-1.5 py-0.5 rounded">
                  تأخر حرج
                </span>
              )}
            </div>
          </button>
        </div>

        {/* الموظف المنصي المسند */}
        <div className="bg-slate-50 p-3 rounded-lg border border-slate-100 text-xs">
          <span className="text-slate-500 block mb-1">الموظف المنصي المكلَّف:</span>
          {company.assigned_employee ? (
            <div className="flex items-center justify-between font-medium text-slate-800">
              <span className="font-bold">{company.assigned_employee.name}</span>
              <span className="text-[11px] bg-white px-2 py-0.5 rounded border border-slate-200 text-slate-600">
                {company.assigned_employee.specialty}
              </span>
            </div>
          ) : (
            <span className="text-amber-700 font-medium">غير مسند لموظف بعد</span>
          )}
        </div>

        {/* مؤشرات صحة الخدمة وتعاون الزبون (تُطلب عند النقر) */}
        <div className="mt-3 pt-2 border-t border-slate-100">
          <button
            type="button"
            onClick={() => setShowHealth((prev) => !prev)}
            className="w-full py-1.5 px-2.5 rounded-lg text-xs font-semibold text-slate-700 hover:text-emerald-700 hover:bg-emerald-50 border border-slate-200 hover:border-emerald-300 flex items-center justify-between transition"
          >
            <span className="flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-emerald-600" />
              مؤشرات صحة الخدمة والتعاون
            </span>
            {showHealth ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
          {showHealth && <CompanyHealthPanel tenantId={company.id} onDrilldown={onDrilldown} />}
        </div>
      </div>
    </div>
  );
};
