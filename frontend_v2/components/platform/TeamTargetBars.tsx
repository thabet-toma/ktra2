import React, { useMemo, useState } from "react";
import { PlatformDashboardEmployee } from "../../utils/dashboardRanking";
import { formatNumber } from "../../utils/formatNumber";
// سُلَّمُ العرض صار أداةً مشتركةً حين لزم شريطٌ ثانٍ في «خطّتي» — نسخةٌ
// ثانيةٌ منه تتباعد بصمتٍ فتُخرج شريطين بدقّتين مختلفتين.
import { barWidthClass } from "../../utils/barWidth";
import { CcCard, CcProgress, CcSectionTitle } from "./ui";

interface TeamTargetBarsProps {
  employees: PlatformDashboardEmployee[];
}

const ROWS_COLLAPSED = 8;

interface TargetRow {
  employee: PlatformDashboardEmployee;
  /** `active_work_orders_count / capacity_target` — أو `null` حين `capacity_target === 0` («لم تُضبط» لا «طاقةَ صفر»). */
  ratio: number | null;
}

/** بطاقةُ «ملخّص أداء الفريق»: نسبةُ استهلاك طاقة الإسناد لكلّ موظّف. */
export const TeamTargetBars: React.FC<TeamTargetBarsProps> = ({
  employees,
}: TeamTargetBarsProps) => {
  const [showAll, setShowAll] = useState(false);

  const rows = useMemo<TargetRow[]>(() => {
    const withRatios = employees.map((employee) => ({
      employee,
      ratio:
        employee.capacity_target > 0
          ? employee.active_work_orders_count / employee.capacity_target
          : null,
    }));
    return withRatios.sort((a, b) => {
      if (a.ratio === null && b.ratio === null) return 0;
      if (a.ratio === null) return 1;
      if (b.ratio === null) return -1;
      return b.ratio - a.ratio;
    });
  }, [employees]);

  const visibleRows = showAll ? rows : rows.slice(0, ROWS_COLLAPSED);

  if (rows.length === 0) {
    return null;
  }

  return (
    <CcCard className="p-5 mb-6" dir="rtl">
      <CcSectionTitle
        title="ملخّص أداء الفريق"
        subtitle="استهلاكُ طاقة الإسناد لكلّ موظّف"
        className="mb-4"
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {visibleRows.map(({ employee, ratio }) => {
          const percent = ratio === null ? 0 : ratio * 100;
          const isOverloaded = ratio !== null && ratio > 1;

          if (ratio === null) {
            return (
              <div
                key={employee.id}
                className="p-3 rounded-lg bg-cc-surface-2/40 border border-cc-border flex items-center justify-between"
              >
                <span className="text-xs font-semibold text-cc-text truncate" title={employee.name}>
                  {employee.name}
                </span>
                <span className="text-xs text-cc-text-muted">لم تُضبط المستهدفات</span>
              </div>
            );
          }

          return (
            <div
              key={employee.id}
              className={`p-3 rounded-lg bg-cc-surface-2/40 border border-cc-border ${barWidthClass(percent) ? "" : ""}`}
            >
              <CcProgress
                value={employee.active_work_orders_count}
                max={employee.capacity_target}
                tone={isOverloaded ? "warning" : "accent"}
                label={employee.name}
                valueLabel={`${formatNumber(percent, { maxDecimals: 0 })}% (${formatNumber(employee.active_work_orders_count)} / ${formatNumber(employee.capacity_target)})`}
              />
            </div>
          );
        })}
      </div>

      {rows.length > ROWS_COLLAPSED && (
        <button
          type="button"
          onClick={() => setShowAll((prev) => !prev)}
          className="mt-4 text-xs font-semibold text-sky-400 hover:text-sky-300 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 rounded px-2 py-1"
        >
          {showAll ? "عرض أقل" : `الكلّ (${formatNumber(rows.length)})`}
        </button>
      )}
    </CcCard>
  );
};

export default TeamTargetBars;
