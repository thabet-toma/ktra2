import React from "react";
import {
  getAnomalyMeta,
  PlatformAnomaly,
  sortAnomaliesWorstFirst,
} from "../../utils/interventionAnomalies";

interface InterventionRailProps {
  anomalies: PlatformAnomaly[];
  onSelectAnomaly?: (anomaly: PlatformAnomaly) => void;
}

export const InterventionRail: React.FC<InterventionRailProps> = ({
  anomalies,
  onSelectAnomaly,
}) => {
  const sortedAnomalies = sortAnomaliesWorstFirst(anomalies);
  const count = sortedAnomalies.length;

  if (count === 0) {
    return (
      <div className="bg-emerald-50/60 border border-emerald-200 rounded-xl p-4 flex items-center justify-between" dir="rtl">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold">
            ✓
          </div>
          <div>
            <h4 className="text-sm font-bold text-emerald-900">العمليات تسير بصورة طبيعية</h4>
            <p className="text-xs text-emerald-700 mt-0.5">
              لا توجد شذوذات تشغيلية حرجة أو تأخيرات معلقة تتطلب تدخلاً فورياً.
            </p>
          </div>
        </div>
        <span className="text-xs font-semibold px-2.5 py-1 bg-emerald-100 text-emerald-800 rounded-full">
          0 تنبيهات
        </span>
      </div>
    );
  }

  return (
    <div className="bg-white border border-rose-200 rounded-xl p-4 shadow-sm" dir="rtl">
      <div className="flex items-center justify-between mb-3 border-b border-rose-100 pb-2.5">
        <div className="flex items-center gap-2.5">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-rose-500"></span>
          </span>
          <h3 className="text-base font-bold text-slate-900">شريط التدخل السريع (الشذوذات الحرجة)</h3>
          <span className="text-xs text-slate-500">مرتبة بحسب الأولوية والحدة (الأسوأ أولاً)</span>
        </div>
        <span className="text-xs font-bold px-2.5 py-1 bg-rose-100 text-rose-800 rounded-full border border-rose-200">
          {count} حالات تستوجب التدخل
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        {sortedAnomalies.map((item, idx) => {
          const typeStr = (item.type || item.anomaly_type || "").toString();
          const meta = getAnomalyMeta(typeStr);

          return (
            <div
              key={`${typeStr}-${item.employee_id}-${item.work_order_id}-${idx}`}
              onClick={() => onSelectAnomaly && onSelectAnomaly(item)}
              className={`p-3 rounded-lg border transition cursor-pointer hover:shadow-md ${meta.bgClass} ${meta.borderClass}`}
            >
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <span className={`px-2 py-0.5 text-xs font-bold rounded-md border ${meta.badgeClass}`}>
                  {meta.label}
                </span>
                {item.severity === "critical" && (
                  <span className="text-[10px] font-extrabold text-rose-600 uppercase tracking-wider">
                    حرج جداً
                  </span>
                )}
              </div>

              <p className="text-xs font-semibold text-slate-800 leading-snug mb-2 line-clamp-2">
                {item.message}
              </p>

              <div className="flex items-center justify-between text-[11px] text-slate-600 pt-1.5 border-t border-slate-200/50">
                <span className="truncate max-w-[120px] font-medium">
                  {item.employee_name || "بدون موظف"}
                </span>
                {item.tenant_name && (
                  <span className="truncate max-w-[100px] text-slate-500">
                    {item.tenant_name}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
