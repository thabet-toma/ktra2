import React, { useEffect, useMemo, useState } from 'react';
import { Building2, CalendarDays, ClipboardList, SearchX, TimerReset } from 'lucide-react';

import type { MyPlatformEmployeeProfile } from '../../../services/platformEmployeeSpaceApi';
import { listMyEngagedCompanies } from '../../../services/platformEmployeeSpaceApi';
import { getEmployeeWorkOrderQueue, type WorkOrderDetailRow } from '../../../services/platformWorkOrdersApi';
import { listPlatformMeetings } from '../../../services/platformMeetingsApi';
import { formatDateTimeValue, formatDateValue, formatWeekdayName } from '../../../utils/formatDate';
import { formatNumber } from '../../../utils/formatNumber';
import { CcAvatar, CcCard, CcGauge, CcPill, CcStatTile } from '../ui';

interface StaffHomeDashboardProps {
  profile: MyPlatformEmployeeProfile | null;
  searchTerm: string;
  onOpenTasks: () => void;
}

/**
 * **مرحلةٌ مُرقَّمةٌ لا نسبةٌ مئويّةٌ مخترَعة.** كان هنا جدولٌ يعطي `data_entry`
 * «٥٠٪» و`review` «٧٠٪» — أرقامٌ لم يقلها الخادمُ قطّ ولا تقيس شيئاً، وتُقرأ على
 * الشاشة إنجازاً محسوباً. آلةُ حالات أمر العمل ستُّ محطّاتٍ معلومة، فالصادقُ أن
 * يُقال «المرحلة ٣ من ٦ — إدخال بيانات».
 */
const STAGE_ORDER = ['received', 'screening', 'data_entry', 'review', 'approval', 'closed'] as const;

const STAGE_LABELS: Record<WorkOrderDetailRow['status'], string> = {
  received: 'وارد',
  screening: 'فرز',
  data_entry: 'إدخال بيانات',
  review: 'مراجعة',
  approval: 'اعتماد',
  closed: 'مُغلق',
  waiting_customer: 'بانتظار العميل',
  cancelled: 'ملغى',
};

/** موضعُ الحالة في الخطّ المستقيم، أو `null` للتفريعتين اللتين ليستا محطّةً فيه. */
const stageIndexOf = (status: WorkOrderDetailRow['status']): number | null => {
  const index = STAGE_ORDER.indexOf(status as (typeof STAGE_ORDER)[number]);
  return index === -1 ? null : index + 1;
};

const isOpen = (status: WorkOrderDetailRow['status']) => !['closed', 'cancelled'].includes(status);

export const StaffHomeDashboard: React.FC<StaffHomeDashboardProps> = ({
  profile,
  searchTerm,
  onOpenTasks,
}: StaffHomeDashboardProps) => {
  const [companies, setCompanies] = useState<Awaited<ReturnType<typeof listMyEngagedCompanies>>>([]);
  const [tasks, setTasks] = useState<WorkOrderDetailRow[]>([]);
  const [meetings, setMeetings] = useState<Awaited<ReturnType<typeof listPlatformMeetings>>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    void Promise.all([listMyEngagedCompanies(), getEmployeeWorkOrderQueue(), listPlatformMeetings()]).then(([nextCompanies, nextTasks, nextMeetings]) => {
      if (!active) return;
      setCompanies(nextCompanies);
      setTasks(nextTasks);
      setMeetings(nextMeetings);
    }).catch(() => {
      if (!active) return;
      setCompanies([]);
      setTasks([]);
      setMeetings([]);
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const now = new Date();
  const weekStart = new Date(now);
  weekStart.setDate(now.getDate() - now.getDay());
  weekStart.setHours(0, 0, 0, 0);
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekStart.getDate() + 7);
  const meetingsThisWeek = meetings.filter((meeting) => {
    const start = new Date(meeting.start);
    return start >= weekStart && start < weekEnd;
  });
  const term = searchTerm.trim().toLowerCase();
  const matchingCompanies = term ? companies.filter((company) => `${company.company_name} ${company.phone || ''}`.toLowerCase().includes(term)) : [];
  const matchingTasks = term ? tasks.filter((task) => `${task.title} ${task.company_name} ${task.id}`.toLowerCase().includes(term)) : [];
  const todayTasks = useMemo(() => tasks.filter((task) => isOpen(task.status)).slice(0, 5), [tasks]);
  const hasNoData = !loading && companies.length === 0 && tasks.length === 0 && meetings.length === 0;
  const performance = (profile as (MyPlatformEmployeeProfile & { performance?: { composite_score?: number } }) | null)?.performance?.composite_score;
  const score = typeof performance === 'number' ? Math.max(0, Math.min(100, performance)) : null;

  if (hasNoData) {
    return (
      <CcCard className="p-10 text-center shadow-lg shadow-black/30">
        <ClipboardList className="mx-auto h-10 w-10 text-sky-400" />
        <h1 className="mt-3 text-lg font-extrabold text-cc-text">لا توجد متابعة معلّقة الآن</h1>
        <p className="mt-1 text-sm text-cc-text-muted">ستظهر مهامك وشركاتك واجتماعاتك هنا فور إسنادها إليك.</p>
        <button
          type="button"
          onClick={onOpenTasks}
          className="mt-5 rounded-xl bg-gradient-to-l from-cyan-500 to-blue-600 px-4 py-2 text-sm font-bold text-white shadow-lg shadow-cyan-500/20 hover:from-cyan-400 hover:to-blue-500 transition"
        >
          اذهب إلى مهامي
        </button>
      </CcCard>
    );
  }

  return (
    <div className="space-y-6">
      <CcCard className="flex items-center justify-between gap-4 bg-gradient-to-l from-blue-950/40 via-cc-surface to-cc-surface p-5 shadow-lg shadow-cyan-500/10">
        <div>
          <h1 className="text-2xl font-extrabold text-cc-text">مرحباً {profile?.username || 'بك'}</h1>
          <p className="mt-1 text-sm text-cc-text-muted">{formatWeekdayName(now)}، {formatDateValue(now)}</p>
        </div>
        <CcAvatar
          name={profile?.username || 'موظف كترا'}
          photoUrl={profile?.photo_url}
          size="lg"
          presence="online"
        />
      </CcCard>

      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <CcCard className="p-4 shadow-lg shadow-black/30">
          <CcStatTile
            label="شركاتي"
            value={companies.length}
            icon={<Building2 className="h-5 w-5 text-sky-400" />}
            tone="accent"
          />
        </CcCard>
        <CcCard className="p-4 shadow-lg shadow-black/30">
          <CcStatTile
            label="مهامي المفتوحة"
            value={tasks.filter((task) => isOpen(task.status)).length}
            icon={<ClipboardList className="h-5 w-5 text-purple-400" />}
            tone="violet"
          />
        </CcCard>
        <CcCard className="p-4 shadow-lg shadow-black/30">
          <CcStatTile
            label="اجتماعاتي هذا الأسبوع"
            value={meetingsThisWeek.length}
            icon={<CalendarDays className="h-5 w-5 text-emerald-400" />}
            tone="success"
          />
        </CcCard>
      </section>

      {score !== null ? (
        <CcCard className="p-5 shadow-lg shadow-black/30">
          <div className="flex flex-col items-center gap-6 sm:flex-row sm:justify-start">
            <CcGauge
              value={score}
              size="lg"
              caption="الأداء العام"
              displayValue={`${formatNumber(score)}%`}
            />
            <div className="text-center sm:text-right">
              <h2 className="text-lg font-extrabold text-cc-text">الأداء العام</h2>
              <p className="mt-1 text-sm text-cc-text-muted">تقييمك المعتمد في المنصة.</p>
              <div className="mt-3 flex items-center justify-center sm:justify-start gap-2">
                <CcPill tone="accent" dot>
                  التقييم الحالي: {formatNumber(score)}%
                </CcPill>
              </div>
            </div>
          </div>
        </CcCard>
      ) : (
        <CcCard className="p-5 shadow-lg shadow-black/30">
          <p className="font-extrabold text-cc-text">الأداء العام</p>
          <p className="mt-1 text-sm text-cc-text-muted">لم يصدر تقييم معتمد لعرضه بعد.</p>
        </CcCard>
      )}

      {term && (
        <CcCard className="p-5 shadow-lg shadow-black/30">
          <h2 className="text-base font-extrabold text-cc-text">نتائج البحث</h2>
          {matchingCompanies.length === 0 && matchingTasks.length === 0 ? (
            <p className="mt-3 flex items-center gap-2 text-sm text-cc-text-muted">
              <SearchX className="h-4 w-4" />لا نتائج في شركاتك أو أوامر عملك.
            </p>
          ) : (
            <div className="mt-3 space-y-2 text-sm">
              {matchingCompanies.map((company) => (
                <p key={`company-${company.tenant_id}`} className="rounded-xl bg-cc-surface-2 px-3 py-2 text-cc-text">
                  شركة: {company.company_name}
                </p>
              ))}
              {matchingTasks.map((task) => (
                <p key={`task-${task.id}`} className="rounded-xl bg-cc-surface-2 px-3 py-2 text-cc-text">
                  أمر {formatNumber(task.id)}: {task.title}
                </p>
              ))}
            </div>
          )}
        </CcCard>
      )}

      <CcCard className="p-5 shadow-lg shadow-black/30">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div>
            <h2 className="text-lg font-extrabold text-cc-text">متابعاتي اليوم</h2>
            <p className="text-sm text-cc-text-muted">أقرب خمسة أوامر عمل مفتوحة.</p>
          </div>
          <TimerReset className="h-5 w-5 text-sky-400" />
        </div>

        <div className="space-y-4">
          {loading ? (
            <p className="py-5 text-sm text-cc-text-muted">جارٍ التحميل...</p>
          ) : todayTasks.length === 0 ? (
            <p className="py-5 text-sm text-cc-text-muted">لا توجد أوامر عمل مفتوحة اليوم.</p>
          ) : (
            todayTasks.map((task) => {
              const stage = stageIndexOf(task.status);
              const priorityTone =
                task.priority === 'urgent'
                  ? 'danger'
                  : task.priority === 'high'
                  ? 'warning'
                  : task.priority === 'normal'
                  ? 'accent'
                  : 'neutral';

              return (
                <CcCard key={task.id} className="p-4 bg-cc-surface-2/40 hover:border-cc-border-strong transition">
                  <div className="flex flex-wrap items-start justify-between gap-3 mb-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-sm font-bold text-cc-text truncate">{task.title}</h3>
                        {/* الاسمُ من الخادم لا من خريطةٍ هنا — هي القاعدةُ نفسُها
                            المكتوبةُ فوق `PRIORITY_OPTION_LABELS` في `WorkOrdersPanel`:
                            «ألوانٌ فقط — لا تسميات». والخريطةُ المحلّيّةُ تنحرف:
                            قالت «عاجل» والخادمُ يقول «عاجلة». */}
                        <CcPill tone={priorityTone} dot>{task.priority_display}</CcPill>
                      </div>
                      <p className="mt-1 text-xs text-cc-text-muted">
                        {task.company_name} · آخر تحديث {formatDateTimeValue(task.updated_at)} · أمر #{formatNumber(task.id)}
                      </p>
                    </div>

                    <span className="shrink-0 text-xs font-bold text-sky-400">
                      {stage === null
                        ? STAGE_LABELS[task.status]
                        : `المرحلة ${formatNumber(stage)} من ${formatNumber(STAGE_ORDER.length)} · ${STAGE_LABELS[task.status]}`}
                    </span>
                  </div>

                  {/* خطُّ محطّاتٍ لا شريطُ نسبة: ستُّ محطّاتٍ تُملأ حتى الحاليّة.
                      كان هنا جدولٌ يعطي `data_entry` «٥٠٪» و`review` «٧٠٪» — أرقامٌ
                      لم يقلها الخادمُ قطّ وتُقرأ على الشاشة إنجازاً محسوباً. وصورةُ
                      المالك (اللوحة 5) دوائرُ مرقّمةٌ موصولةٌ بخطّ، وهي الصادقةُ
                      هنا لأنّها تعدّ المحطّاتِ ولا تدّعي كسراً. */}
                  <div className="mt-4 pt-3 border-t border-cc-border">
                    <div className="flex items-center justify-between gap-1 w-full" aria-label="خط مراحل أمر العمل">
                      {STAGE_ORDER.map((stName, idx) => {
                        const stepNum = idx + 1;
                        const isReached = stage !== null && stage >= stepNum;
                        const isCurrent = stage !== null && stage === stepNum;
                        const hasNext = idx < STAGE_ORDER.length - 1;
                        const isLineActive = stage !== null && stage > stepNum;

                        return (
                          <React.Fragment key={stName}>
                            <div className="flex flex-col items-center">
                              <div
                                className={`flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold transition-colors ${
                                  isCurrent
                                    ? 'bg-emerald-500 text-slate-950 ring-2 ring-emerald-400/50'
                                    : isReached
                                    ? 'bg-sky-500 text-slate-950'
                                    : 'bg-cc-surface-2 border border-cc-border text-cc-text-muted'
                                }`}
                                title={`${STAGE_LABELS[stName]} (${formatNumber(stepNum)})`}
                              >
                                {formatNumber(stepNum)}
                              </div>
                              <span
                                className={`text-[10px] mt-1 whitespace-nowrap ${
                                  isCurrent
                                    ? 'font-bold text-emerald-400'
                                    : isReached
                                    ? 'text-sky-300 font-medium'
                                    : 'text-cc-text-muted'
                                }`}
                              >
                                {STAGE_LABELS[stName]}
                              </span>
                            </div>
                            {hasNext && (
                              <div
                                className={`h-0.5 flex-1 mx-1 rounded-full transition-colors ${
                                  isLineActive ? 'bg-sky-500' : 'bg-cc-border'
                                }`}
                                aria-hidden="true"
                              />
                            )}
                          </React.Fragment>
                        );
                      })}
                    </div>
                  </div>
                </CcCard>
              );
            })
          )}
        </div>
      </CcCard>
    </div>
  );
};

export default StaffHomeDashboard;
