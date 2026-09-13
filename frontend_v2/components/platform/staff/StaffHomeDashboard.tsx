import React, { useEffect, useMemo, useState } from 'react';
import { Building2, CalendarDays, ClipboardList, SearchX, TimerReset } from 'lucide-react';

import type { MyPlatformEmployeeProfile } from '../../../services/platformEmployeeSpaceApi';
import { listMyEngagedCompanies } from '../../../services/platformEmployeeSpaceApi';
import { getEmployeeWorkOrderQueue, type WorkOrderDetailRow } from '../../../services/platformWorkOrdersApi';
import { listPlatformMeetings } from '../../../services/platformMeetingsApi';
import { formatDateTimeValue, formatDateValue, formatWeekdayName } from '../../../utils/formatDate';
import { formatNumber } from '../../../utils/formatNumber';

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
const priorityClass = (priority: WorkOrderDetailRow['priority']) => priority === 'urgent' ? 'bg-rose-400' : priority === 'high' ? 'bg-amber-400' : priority === 'normal' ? 'bg-cyan-400' : 'bg-slate-400';

export const StaffHomeDashboard: React.FC<StaffHomeDashboardProps> = ({ profile, searchTerm, onOpenTasks }) => {
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
  const circumference = 2 * Math.PI * 44;
  const score = typeof performance === 'number' ? Math.max(0, Math.min(100, performance)) : null;

  if (hasNoData) return <section className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-10 text-center shadow-lg shadow-black/30"><ClipboardList className="mx-auto h-10 w-10 text-cyan-300" /><h1 className="mt-3 text-lg font-extrabold text-slate-50">لا توجد متابعة معلّقة الآن</h1><p className="mt-1 text-sm text-[var(--staff-muted)]">ستظهر مهامك وشركاتك واجتماعاتك هنا فور إسنادها إليك.</p><button type="button" onClick={onOpenTasks} className="mt-5 rounded-xl bg-gradient-to-l from-cyan-500 to-blue-600 px-4 py-2 text-sm font-bold text-white shadow-lg shadow-cyan-500/20 hover:from-cyan-400 hover:to-blue-500">اذهب إلى مهامي</button></section>;

  return <div className="space-y-6">
    <section className="flex items-center justify-between gap-4 rounded-2xl border border-[var(--staff-line)] bg-gradient-to-l from-blue-900/50 via-[var(--staff-panel)] to-[var(--staff-panel)] p-5 shadow-lg shadow-cyan-500/10"><div><h1 className="text-2xl font-extrabold text-slate-50">مرحباً {profile?.username || 'بك'}</h1><p className="mt-1 text-sm text-[var(--staff-muted)]">{formatWeekdayName(now)}، {formatDateValue(now)}</p></div><span className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-full bg-cyan-500/15 text-xl font-extrabold text-cyan-300 ring-2 ring-cyan-400/30">{profile?.photo_url ? <img src={profile.photo_url} alt="" className="h-full w-full object-cover" /> : (profile?.username || 'ك').slice(0, 1)}</span></section>

    <section className="grid grid-cols-2 gap-4 lg:grid-cols-3">
      <article className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-4 shadow-lg shadow-black/30"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-cyan-300"><Building2 className="h-5 w-5" /></span><p className="mt-4 text-2xl font-extrabold text-slate-50">{formatNumber(companies.length)}</p><p className="text-xs font-semibold text-[var(--staff-muted)]">شركاتي</p></article>
      <article className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-4 shadow-lg shadow-black/30"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-500/15 text-violet-300"><ClipboardList className="h-5 w-5" /></span><p className="mt-4 text-2xl font-extrabold text-slate-50">{formatNumber(tasks.filter((task) => isOpen(task.status)).length)}</p><p className="text-xs font-semibold text-[var(--staff-muted)]">مهامي المفتوحة</p></article>
      <article className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-4 shadow-lg shadow-black/30"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/15 text-emerald-300"><CalendarDays className="h-5 w-5" /></span><p className="mt-4 text-2xl font-extrabold text-slate-50">{formatNumber(meetingsThisWeek.length)}</p><p className="text-xs font-semibold text-[var(--staff-muted)]">اجتماعاتي هذا الأسبوع</p></article>
    </section>

    {score !== null ? <section className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30"><div className="flex flex-col items-center gap-5 sm:flex-row"><svg viewBox="0 0 112 112" className="h-36 w-36" aria-label="حلقة الأداء العام"><g transform="rotate(-90 56 56)"><circle cx="56" cy="56" r="44" fill="none" stroke="currentColor" strokeWidth="10" className="stroke-[var(--staff-line)]" /><circle cx="56" cy="56" r="44" fill="none" stroke="currentColor" strokeWidth="10" strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={circumference * (1 - score / 100)} className="stroke-cyan-400" /></g><text x="56" y="61" textAnchor="middle" className="fill-slate-50 text-xl font-extrabold">{formatNumber(score)}%</text></svg><div><h2 className="text-lg font-extrabold text-slate-50">الأداء العام</h2><p className="mt-1 text-sm text-[var(--staff-muted)]">تقييمك المعتمد في المنصة.</p><p className="mt-3 flex items-center gap-2 text-xs font-semibold text-[var(--staff-muted)]"><span className="h-2 w-2 rounded-full bg-cyan-400" />التقييم الحالي</p></div></div></section> : <section className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30"><p className="font-extrabold text-slate-50">الأداء العام</p><p className="mt-1 text-sm text-[var(--staff-muted)]">لم يصدر تقييم معتمد لعرضه بعد.</p></section>}

    {term && <section className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30"><h2 className="text-base font-extrabold text-slate-50">نتائج البحث</h2>{matchingCompanies.length === 0 && matchingTasks.length === 0 ? <p className="mt-3 flex items-center gap-2 text-sm text-[var(--staff-muted)]"><SearchX className="h-4 w-4" />لا نتائج في شركاتك أو أوامر عملك.</p> : <div className="mt-3 space-y-2 text-sm">{matchingCompanies.map((company) => <p key={`company-${company.tenant_id}`} className="rounded-xl bg-white/5 px-3 py-2 text-slate-50">شركة: {company.company_name}</p>)}{matchingTasks.map((task) => <p key={`task-${task.id}`} className="rounded-xl bg-white/5 px-3 py-2 text-slate-50">أمر {formatNumber(task.id)}: {task.title}</p>)}</div>}</section>}

    <section className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30"><div className="flex items-center justify-between gap-3"><div><h2 className="text-lg font-extrabold text-slate-50">متابعاتي اليوم</h2><p className="text-sm text-[var(--staff-muted)]">أقرب خمسة أوامر عمل مفتوحة.</p></div><TimerReset className="h-5 w-5 text-cyan-300" /></div><div className="mt-4 divide-y divide-[var(--staff-line)]">{loading ? <p className="py-5 text-sm text-[var(--staff-muted)]">جارٍ التحميل...</p> : todayTasks.map((task) => {
      const stage = stageIndexOf(task.status);
      return (
        <article key={task.id} className="py-4 first:pt-0">
          <div className="flex items-start gap-3">
            <span className={`mt-1 h-3 w-3 shrink-0 rounded ${priorityClass(task.priority)}`} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-3">
                <h3 className="truncate text-sm font-bold text-slate-50">{task.title}</h3>
                <span className="shrink-0 text-xs font-bold text-cyan-300">
                  {stage === null
                    ? STAGE_LABELS[task.status]
                    : `المرحلة ${formatNumber(stage)} من ${formatNumber(STAGE_ORDER.length)} · ${STAGE_LABELS[task.status]}`}
                </span>
              </div>
              <p className="mt-1 text-xs text-[var(--staff-muted)]">{task.company_name} · آخر تحديث {formatDateTimeValue(task.updated_at)}</p>
              {/* شريطُ محطّاتٍ لا شريطُ نسبة: ستُّ خاناتٍ تُملأ حتى المحطّة الحاليّة. */}
              <div className="mt-2 flex gap-1" aria-hidden="true">
                {STAGE_ORDER.map((name, index) => (
                  <span
                    key={name}
                    className={`h-1.5 flex-1 rounded-full ${stage !== null && index < stage ? 'bg-cyan-400' : 'bg-white/10'}`}
                  />
                ))}
              </div>
              <p className="mt-2 text-xs text-[var(--staff-muted)]">أمر #{formatNumber(task.id)}</p>
            </div>
          </div>
        </article>
      );
    })}</div></section>
  </div>;
};

export default StaffHomeDashboard;
