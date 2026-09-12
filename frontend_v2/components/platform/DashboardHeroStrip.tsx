import React, { useMemo } from "react";
import { PlatformDashboardEmployee } from "../../utils/dashboardRanking";
import { formatNumber } from "../../utils/formatNumber";

interface DashboardHeroStripProps {
  employees: PlatformDashboardEmployee[];
  /** المتّصلون الآن — `countPresent(roomOccupants)` من `roomPresence.ts`، محسوبٌ سلفاً في اللوحة. */
  presentCount: number;
  /** المقام — `roomOccupants.length` نفسُه، لا عددُ موظّفين آخر. */
  totalCount: number;
}

const RADIUS = 36;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/** شريطُ الأرقام العلويّ: رقمٌ كبيرٌ، بطاقةُ تنبيه، ودونات حضور — كلُّها من حمولة اللوحة. */
export const DashboardHeroStrip: React.FC<DashboardHeroStripProps> = ({
  employees,
  presentCount,
  totalCount,
}) => {
  const totalActiveWorkOrders = useMemo(
    () => employees.reduce((sum, employee) => sum + (employee.active_work_orders_count || 0), 0),
    [employees]
  );
  const totalOverdueWorkOrders = useMemo(
    () => employees.reduce((sum, employee) => sum + (employee.overdue_work_orders_count || 0), 0),
    [employees]
  );
  const hasOverdue = totalOverdueWorkOrders > 0;

  // نسبةُ الحضور لرسم الحلقة؛ مقامٌ صفريٌّ يعني لا موظّفين في الغرفة أصلاً —
  // لا قسمةَ على صفر، وتُرسم حلقةٌ فارغةٌ بلا شريط تقدّم.
  const presenceRatio = totalCount > 0 ? Math.min(1, presentCount / totalCount) : 0;
  const dashOffset = CIRCUMFERENCE * (1 - presenceRatio);

  return (
    <div dir="rtl" className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm flex flex-col items-center justify-center text-center">
        <span className="text-xs font-bold text-slate-500 mb-1">أمر عمل نشط الآن</span>
        <span className="text-4xl font-black text-slate-900">{formatNumber(totalActiveWorkOrders)}</span>
      </div>

      <div
        className={`rounded-xl border p-5 shadow-sm flex flex-col items-center justify-center text-center ${
          hasOverdue ? "bg-rose-50 border-rose-300" : "bg-white border-slate-200"
        }`}
      >
        <span className={`text-xs font-bold mb-1 ${hasOverdue ? "text-rose-700" : "text-slate-500"}`}>
          متأخّر
        </span>
        <span className={`text-4xl font-black ${hasOverdue ? "text-rose-700" : "text-slate-900"}`}>
          {formatNumber(totalOverdueWorkOrders)}
        </span>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm flex flex-col items-center justify-center gap-2">
        <span className="text-xs font-bold text-slate-500">متّصلون الآن</span>
        <div className="relative h-24 w-24">
          <svg viewBox="0 0 84 84" className="h-24 w-24 -rotate-90">
            <circle
              cx="42"
              cy="42"
              r={RADIUS}
              fill="none"
              stroke="currentColor"
              strokeWidth="8"
              className="text-slate-100"
            />
            {totalCount > 0 && (
              <circle
                cx="42"
                cy="42"
                r={RADIUS}
                fill="none"
                stroke="currentColor"
                strokeWidth="8"
                strokeLinecap="round"
                className="text-blue-600"
                strokeDasharray={CIRCUMFERENCE}
                strokeDashoffset={dashOffset}
              />
            )}
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-sm font-black text-slate-900">
              {totalCount > 0 ? `${formatNumber(presentCount)}/${formatNumber(totalCount)}` : "—"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardHeroStrip;
