import React from "react";
import {
  getAnomalyMeta,
  PlatformAnomaly,
  sortAnomaliesWorstFirst,
} from "../../utils/interventionAnomalies";
import { formatNumber } from "../../utils/formatNumber";
import { formatTimeValue } from "../../utils/formatDate";
import { CcTone } from "../../utils/ccTone";
import { CcCard, CcPill } from "./ui";
import { AlertCircle, AlertTriangle, Layers, TrendingDown, Bell } from "lucide-react";

interface InterventionRailProps {
  anomalies: PlatformAnomaly[];
  onSelectAnomaly?: (anomaly: PlatformAnomaly) => void;
}

function getAnomalyTone(type: string): CcTone {
  const norm = (type || "").toLowerCase();
  if (norm === "critical_delay") return "danger";
  if (norm === "absent_with_work") return "warning";
  if (norm === "overloaded") return "warning";
  if (norm === "low_score") return "violet";
  return "neutral";
}

function getAnomalyIcon(type: string) {
  const norm = (type || "").toLowerCase();
  if (norm === "critical_delay") return <AlertCircle className="w-4 h-4 text-rose-400" />;
  if (norm === "absent_with_work") return <AlertTriangle className="w-4 h-4 text-amber-400" />;
  if (norm === "overloaded") return <Layers className="w-4 h-4 text-amber-400" />;
  if (norm === "low_score") return <TrendingDown className="w-4 h-4 text-purple-400" />;
  return <Bell className="w-4 h-4 text-sky-400" />;
}

export const InterventionRail: React.FC<InterventionRailProps> = ({
  anomalies,
  onSelectAnomaly,
}: InterventionRailProps) => {
  const sortedAnomalies = sortAnomaliesWorstFirst(anomalies);
  const count = sortedAnomalies.length;

  if (count === 0) {
    return (
      <CcCard tone="success" className="p-4" dir="rtl">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold">
              ✓
            </div>
            <div>
              <h4 className="text-sm font-bold text-cc-text">العمليات تسير بصورة طبيعية</h4>
              <p className="text-xs text-cc-text-muted mt-0.5">
                لا توجد شذوذات تشغيلية حرجة أو تأخيرات معلقة تتطلب تدخلاً فورياً.
              </p>
            </div>
          </div>
          <CcPill tone="success">0 تنبيهات</CcPill>
        </div>
      </CcCard>
    );
  }

  return (
    <CcCard tone="danger" className="p-4" dir="rtl">
      <div className="flex items-center justify-between mb-3 border-b border-cc-border pb-2.5">
        <div className="flex items-center gap-2.5">
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75 motion-reduce:animate-none" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-rose-500" />
          </span>
          <h3 className="text-sm sm:text-base font-bold text-cc-text">شريط التدخل السريع (الشذوذات الحرجة)</h3>
          <span className="text-xs text-cc-text-muted hidden sm:inline">مرتبة بحسب الأولوية والحدة (الأسوأ أولاً)</span>
        </div>
        <CcPill tone="danger">
          {formatNumber(count)} حالات تستوجب التدخل
        </CcPill>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        {sortedAnomalies.map((item, idx) => {
          const typeStr = (item.type || item.anomaly_type || "").toString();
          const meta = getAnomalyMeta(typeStr);
          const tone = getAnomalyTone(typeStr);
          const icon = getAnomalyIcon(typeStr);

          return (
            <button
              key={`${typeStr}-${item.employee_id}-${item.work_order_id}-${idx}`}
              type="button"
              onClick={() => onSelectAnomaly && onSelectAnomaly(item)}
              className="p-3 rounded-lg border text-right transition group bg-cc-surface-2/60 hover:bg-cc-surface-2 border-cc-border hover:border-cc-border-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-1.5">
                    <span className="p-1 rounded-md bg-cc-surface border border-cc-border shrink-0">
                      {icon}
                    </span>
                    <CcPill tone={tone}>
                      {meta.label}
                    </CcPill>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {item.severity === "critical" && (
                      <span className="text-[10px] font-extrabold text-rose-400 uppercase tracking-wider">
                        حرج جداً
                      </span>
                    )}
                    {item.created_at && (
                      <span className="text-[10px] font-mono text-cc-text-muted">
                        {formatTimeValue(item.created_at)}
                      </span>
                    )}
                  </div>
                </div>

                <p className="text-xs font-semibold text-cc-text leading-snug mb-2 line-clamp-2">
                  {item.message}
                </p>
              </div>

              <div className="flex items-center justify-between text-[11px] text-cc-text-muted pt-1.5 border-t border-cc-border w-full">
                <span className="truncate max-w-[120px] font-medium text-cc-text">
                  {item.employee_name || "بدون موظف"}
                </span>
                {item.tenant_name && (
                  <span className="truncate max-w-[100px] text-cc-text-muted">
                    {item.tenant_name}
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </CcCard>
  );
};

