import React, { useMemo, useState } from "react";
import { PlatformDashboardEmployee } from "../../utils/dashboardRanking";
import { formatNumber } from "../../utils/formatNumber";
// سُلَّمُ العرض صار أداةً مشتركةً حين لزم شريطٌ ثانٍ في «خطّتي» — نسخةٌ
// ثانيةٌ منه تتباعد بصمتٍ فتُخرج شريطين بدقّتين مختلفتين.
import { barWidthClass } from "../../utils/barWidth";

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
export const TeamTargetBars: React.FC<TeamTargetBarsProps> = ({ employees }) => {
  const [showAll, setShowAll] = useState(false);

  const rows = useMemo<TargetRow[]>(() => {
    const withRatios = employees.map((employee) => ({
      employee,
      // `capacity_target === 0` تعني «لم تُضبط» لا «طاقةَ صفر» — لا قسمةَ على صفر.
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
    <div dir="rtl" className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-bold text-slate-800">ملخّص أداء الفريق</h3>
        <span className="text-[11px] text-slate-400 font-medium">استهلاكُ طاقة الإسناد لكلّ موظّف</span>
      </div>

      <div className="space-y-3">
        {visibleRows.map(({ employee, ratio }) => {
          const percent = ratio === null ? 0 : ratio * 100;
          const isOverloaded = ratio !== null && ratio > 1;
          return (
            <div key={employee.id} className="flex items-center gap-3">
              <span className="w-28 shrink-0 truncate text-xs font-semibold text-slate-700" title={employee.name}>
                {employee.name}
              </span>

              {ratio === null ? (
                <span className="flex-1 text-xs text-slate-400">لم تُضبط</span>
              ) : (
                <>
                  <div className="flex-1 h-2.5 rounded-full bg-slate-100 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        isOverloaded ? "bg-amber-500" : "bg-blue-600"
                      } ${barWidthClass(percent)}`}
                    />
                  </div>
                  <span
                    className={`w-16 shrink-0 text-left text-xs font-bold ${
                      isOverloaded ? "text-amber-700" : "text-slate-700"
                    }`}
                  >
                    {formatNumber(percent, { maxDecimals: 0 })}%
                  </span>
                </>
              )}
            </div>
          );
        })}
      </div>

      {rows.length > ROWS_COLLAPSED && (
        <button
          type="button"
          onClick={() => setShowAll((prev) => !prev)}
          className="mt-4 text-xs font-semibold text-blue-600 hover:text-blue-800 transition"
        >
          {showAll ? "عرض أقل" : `الكلّ (${formatNumber(rows.length)})`}
        </button>
      )}
    </div>
  );
};

export default TeamTargetBars;
