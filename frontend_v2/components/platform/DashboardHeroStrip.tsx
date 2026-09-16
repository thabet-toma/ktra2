import React, { useMemo } from "react";
import { PlatformDashboardEmployee } from "../../utils/dashboardRanking";
import { formatNumber } from "../../utils/formatNumber";
import { CcCard, CcStatTile, CcGauge } from "./ui";

interface DashboardHeroStripProps {
  employees: PlatformDashboardEmployee[];
  /** المتّصلون الآن — `countPresent(roomOccupants)` من `roomPresence.ts`، محسوبٌ سلفاً في اللوحة. */
  presentCount: number;
  /** المقام — `roomOccupants.length` نفسُه، لا عددُ موظّفين آخر. */
  totalCount: number;
}

/** شريطُ الأرقام العلويّ: رقمٌ كبيرٌ، بطاقةُ تنبيه، ودونات حضور — كلُّها من حمولة اللوحة عبر مكوّنات مركز القيادة. */
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
  const presencePercent = Math.round(presenceRatio * 100);

  return (
    <div dir="rtl" className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
      <CcCard className="p-5 flex flex-col items-center justify-center text-center">
        <CcStatTile
          label="أمر عمل نشط الآن"
          value={totalActiveWorkOrders}
          tone="accent"
          className="items-center text-center"
        />
      </CcCard>

      <CcCard
        tone={hasOverdue ? "danger" : "default"}
        className="p-5 flex flex-col items-center justify-center text-center"
      >
        <CcStatTile
          label="متأخّر"
          value={totalOverdueWorkOrders}
          tone={hasOverdue ? "danger" : "neutral"}
          className="items-center text-center"
        />
      </CcCard>

      <CcCard className="p-5 flex flex-col items-center justify-center text-center">
        <CcGauge
          value={presencePercent}
          displayValue={totalCount > 0 ? `${formatNumber(presentCount)}/${formatNumber(totalCount)}` : "—"}
          caption="متّصلون الآن"
          tone={presenceRatio > 0.5 ? "success" : presenceRatio > 0 ? "accent" : "neutral"}
          size="md"
        />
      </CcCard>
    </div>
  );
};

export default DashboardHeroStrip;
