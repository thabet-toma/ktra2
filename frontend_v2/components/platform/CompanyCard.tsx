import React, { useState } from "react";
import { PlatformDashboardCompany } from "../../utils/dashboardRanking";
import { CompanyHealthPanel } from "./CompanyHealthPanel";
import { Activity, ChevronDown, ChevronUp } from "lucide-react";
import { formatNumber } from "../../utils/formatNumber";
import { CcCard, CcPill, CcStatTile } from "./ui";

interface CompanyCardProps {
  company: PlatformDashboardCompany;
  onDrilldown: (filter: { metric?: "active" | "overdue"; status?: string }) => void;
}

export const CompanyCard: React.FC<CompanyCardProps> = ({
  company,
  onDrilldown,
}: CompanyCardProps) => {
  const [showHealth, setShowHealth] = useState<boolean>(false);
  const hasOverdue = company.overdue_work_orders_count > 0;

  return (
    <CcCard tone={hasOverdue ? "danger" : "default"} className="p-4 flex flex-col justify-between" dir="rtl">
      <div>
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex-1 min-w-0">
            <h4 className="text-sm sm:text-base font-bold text-cc-text truncate">{company.name}</h4>
            <div className="flex items-center gap-2 mt-1 text-xs text-cc-text-muted flex-wrap">
              <CcPill tone="neutral">
                الباقة: {company.subscription_plan || "غير محددة"}
              </CcPill>
            </div>
          </div>

          <CcPill
            tone={company.subscription_status === "active" ? "success" : "warning"}
            dot={true}
          >
            {company.subscription_status === "active" ? "اشتراك نشط" : company.subscription_status}
          </CcPill>
        </div>

        {/* شبكة الأرقام المنقور عليها (Drilldown) */}
        <div className="grid grid-cols-2 gap-2.5 my-3">
          <button
            type="button"
            onClick={() => onDrilldown({ metric: "active" })}
            className="p-2.5 rounded-lg bg-cc-surface-2/60 hover:bg-cc-surface-2 border border-cc-border hover:border-cc-border-strong text-right transition group focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
          >
            <CcStatTile
              label="أوامر العمل النشطة"
              value={company.active_work_orders_count}
              tone="neutral"
            />
          </button>

          <button
            type="button"
            onClick={() => onDrilldown({ metric: "overdue" })}
            className={`p-2.5 rounded-lg border text-right transition group focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 ${
              hasOverdue
                ? "bg-rose-500/10 border-rose-500/30 hover:border-rose-500/50"
                : "bg-cc-surface-2/60 hover:bg-cc-surface-2 border-cc-border hover:border-cc-border-strong"
            }`}
          >
            <CcStatTile
              label="أوامر متأخرة"
              value={company.overdue_work_orders_count}
              tone={hasOverdue ? "danger" : "neutral"}
              hint={hasOverdue ? "تأخر حرج" : undefined}
            />
          </button>
        </div>

        {/* الموظف المنصي المسند */}
        <div className="bg-cc-surface-2/60 p-3 rounded-lg border border-cc-border text-xs">
          <span className="text-cc-text-muted block mb-1">الموظف المنصي المكلَّف:</span>
          {company.assigned_employee ? (
            <div className="flex items-center justify-between font-medium text-cc-text">
              <span className="font-bold">{company.assigned_employee.name}</span>
              <CcPill tone="neutral">
                {company.assigned_employee.specialty}
              </CcPill>
            </div>
          ) : (
            <span className="text-amber-400 font-medium">غير مسند لموظف بعد</span>
          )}
        </div>

        {/* مؤشرات صحة الخدمة وتعاون الزبون */}
        <div className="mt-3 pt-2 border-t border-cc-border">
          <button
            type="button"
            onClick={() => setShowHealth((prev) => !prev)}
            className="w-full py-1.5 px-2.5 rounded-lg text-xs font-semibold text-cc-text hover:text-emerald-400 hover:bg-cc-surface-2 border border-cc-border hover:border-emerald-500/30 flex items-center justify-between transition focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
          >
            <span className="flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-emerald-400" />
              مؤشرات صحة الخدمة والتعاون
            </span>
            {showHealth ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
          {showHealth && <CompanyHealthPanel tenantId={company.id} onDrilldown={onDrilldown} />}
        </div>
      </div>
    </CcCard>
  );
};

