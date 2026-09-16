import React from "react";
import { PlatformDashboardEmployee } from "../../utils/dashboardRanking";
import { formatNumber } from "../../utils/formatNumber";
import { getLastActiveBadge } from "../../utils/lastActiveFormat";
import { PresenceClockChip } from "./PresenceClockChip";
import { ccPresenceTone, ccScoreTone } from "../../utils/ccTone";
import { CcAvatar, CcCard, CcGauge, CcPill, CcStatTile } from "./ui";

interface EmployeeCardProps {
  employee: PlatformDashboardEmployee;
  onDrilldown: (filter: { assignee: number; metric?: "active" | "overdue"; status?: string }) => void;
  onViewActivity: (employeeId: number, employeeName: string) => void;
  onEditTargets: (employeeId: number, employeeName: string) => void;
  /** نقرةٌ على الوجه تفتح ملفّ الموظّف الـ360 (211-J). */
  onOpenProfile: (employeeId: number) => void;
  /** فتحُ الملفّ على تبويب المهامّ مباشرةً — «أسند مهمّة» لهذا الشخص (212-O1). */
  onOpenTasks: (employeeId: number) => void;
}

export const EmployeeCard: React.FC<EmployeeCardProps> = ({
  employee,
  onDrilldown,
  onViewActivity,
  onEditTargets,
  onOpenProfile,
  onOpenTasks,
}: EmployeeCardProps) => {
  const lastActiveBadge = getLastActiveBadge(employee.last_active_at);
  const isOverloaded = employee.active_work_orders_count > employee.capacity_target;
  const hasOverdue = employee.overdue_work_orders_count > 0;
  const score = employee.performance?.composite_score;

  const cardTone = hasOverdue ? "danger" : isOverloaded ? "warning" : "default";

  return (
    <CcCard tone={cardTone} className="p-4 flex flex-col justify-between" dir="rtl">
      <div>
        {/* الرأس: الصورة، تفاصيل الموظف، وحلقة الأداء المركبة */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <button
            type="button"
            onClick={() => onOpenProfile(employee.id)}
            title="فتح ملف الموظّف"
            className="flex flex-1 min-w-0 items-center gap-3 text-right focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 rounded-lg group"
          >
            <span className="flex shrink-0 flex-col items-center gap-1">
              <PresenceClockChip
                seconds={employee.presence_seconds_today}
                targetHours={employee.presence_target_hours}
              />
              <CcAvatar
                name={employee.name}
                photoUrl={employee.photo_url}
                size="md"
                presence={ccPresenceTone(employee.is_active_now, employee.is_in_meeting)}
              />
            </span>
            <span className="flex-1 min-w-0">
              <h4 className="text-sm sm:text-base font-bold text-cc-text truncate group-hover:text-sky-400 transition-colors">
                {employee.name}
              </h4>
              <div className="flex items-center gap-2 mt-1 text-xs text-cc-text-muted flex-wrap">
                {employee.username && (
                  <span className="font-mono text-cc-text-muted">@{employee.username}</span>
                )}
                {employee.username && <span>•</span>}
                {/* التخصّصُ لا المسمّى: مصفاةُ اللوحة تُصفّي بـ`specialty`،
                    فعرضُ `job_title` يجعل المعروضَ غيرَ المبحوثِ به. */}
                <CcPill tone="neutral">
                  {employee.specialty}
                </CcPill>
              </div>
            </span>
          </button>

          <div className="shrink-0 flex items-center justify-center">
            <CcGauge
              value={typeof score === "number" ? score : 0}
              size="sm"
              tone={ccScoreTone(score)}
              displayValue={typeof score === "number" ? `${formatNumber(Math.round(score))}%` : "—"}
              caption="الدرجة"
            />
          </div>
        </div>

        {/* شرائح الحالة والحضور */}
        <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
          {/* لا مصباحَ ولا نقطةَ حالة: المواصفةُ أسقطتهما لأنّهما «يَعِدان بدقّةٍ لا
              يملكها النظام» — المصدرُ نافذةُ خمسِ دقائقَ على `UserDevice`. والنصُّ
              يحمل الساعةَ الحقيقيّةَ وهي أصدقُ من لون. */}
          <CcPill tone={lastActiveBadge.active ? "success" : "neutral"}>
            {lastActiveBadge.label}
          </CcPill>
          {isOverloaded && (
            <CcPill tone="warning" dot={true}>
              حمل مفرط ({formatNumber(employee.active_work_orders_count)} / {formatNumber(employee.capacity_target)})
            </CcPill>
          )}
          {hasOverdue && (
            <CcPill tone="danger" dot={true}>
              تأخر حرج ({formatNumber(employee.overdue_work_orders_count)})
            </CcPill>
          )}
        </div>

        {/* صف الأرقام الإحصائية المنقور عليها (CcStatTile) */}
        <div className="grid grid-cols-3 gap-2 my-2">
          <button
            type="button"
            onClick={() => onDrilldown({ assignee: employee.id, metric: "active" })}
            className="p-2.5 rounded-lg bg-cc-surface-2/60 hover:bg-cc-surface-2 border border-cc-border hover:border-cc-border-strong text-right transition group focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
          >
            <CcStatTile
              label="أوامر نشطة"
              value={employee.active_work_orders_count}
              hint={`الهدف: ${formatNumber(employee.capacity_target)}`}
              tone={isOverloaded ? "warning" : "neutral"}
            />
          </button>

          <button
            type="button"
            onClick={() => onDrilldown({ assignee: employee.id, metric: "overdue" })}
            className={`p-2.5 rounded-lg border text-right transition group focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 ${
              hasOverdue
                ? "bg-rose-500/10 border-rose-500/30 hover:border-rose-500/50"
                : "bg-cc-surface-2/60 hover:bg-cc-surface-2 border-cc-border hover:border-cc-border-strong"
            }`}
          >
            <CcStatTile
              label="أوامر متأخرة"
              value={employee.overdue_work_orders_count}
              hint={hasOverdue ? "تأخر حرج" : "لا تأخير"}
              tone={hasOverdue ? "danger" : "neutral"}
            />
          </button>

          {/* **مهامُّ المنصّة** (212-O2) — وهي غيرُ أوامر العمل المجاورة: نظامان
              لا يلتقيان، ورقمٌ واحدٌ عنهما كان يكذب. والزرُّ نفسُه بابُ «أسند
              مهمّة» لهذا الشخص (212-O1) بدل نموذجٍ مركزيٍّ يُختار منه اسمُه. */}
          <button
            type="button"
            onClick={() => onOpenTasks(employee.id)}
            className="p-2.5 rounded-lg bg-cc-surface-2/60 hover:bg-cc-surface-2 border border-cc-border hover:border-cc-border-strong text-right transition group focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
          >
            <CcStatTile
              label="مهام مفتوحة"
              value={formatNumber(employee.open_platform_tasks_count ?? 0, { maxDecimals: 0 })}
              hint="أسند مهمة"
              tone={(employee.open_platform_tasks_count ?? 0) > 0 ? "accent" : "neutral"}
            />
          </button>
        </div>

        {(score === null || score === undefined) && employee.performance?.status_message && (
          <div className="text-xs text-cc-text-muted mt-1 px-1">
            {employee.performance.status_message}
          </div>
        )}

        {/* الشركات المرتبطة */}
        {employee.companies && employee.companies.length > 0 && (
          <div className="mt-2.5 pt-2 border-t border-cc-border">
            <span className="text-[11px] text-cc-text-muted block mb-1">
              الشركات المرتبطة ({formatNumber(employee.companies.length)}):
            </span>
            <div className="flex flex-wrap gap-1">
              {employee.companies.slice(0, 3).map((comp) => (
                <CcPill key={comp.id} tone="neutral">
                  {comp.name}
                </CcPill>
              ))}
              {employee.companies.length > 3 && (
                <span className="text-[10px] text-cc-text-muted self-center">
                  +{formatNumber(employee.companies.length - 3)} أخرى
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* زر سجل النشاط والروابط السفلية */}
      <div className="mt-3 pt-2.5 border-t border-cc-border flex items-center justify-between text-xs">
        <button
          type="button"
          onClick={() => onViewActivity(employee.id, employee.name)}
          className="font-semibold text-sky-400 hover:text-sky-300 transition flex items-center gap-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 rounded"
        >
          <span>سجل النشاط العابر</span>
          <span>←</span>
        </button>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onEditTargets(employee.id, employee.name)}
            className="text-cc-text-muted hover:text-cc-text transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 rounded px-1.5 py-0.5"
          >
            ضبط المستهدفات
          </button>
          <button
            type="button"
            onClick={() => onDrilldown({ assignee: employee.id })}
            className="text-cc-text-muted hover:text-cc-text transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 rounded px-1.5 py-0.5"
          >
            كل الأوامر
          </button>
        </div>
      </div>
    </CcCard>
  );
};

