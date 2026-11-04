import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import {
  getOfficeSettings,
  getOfficeToday,
  type OfficeSettingsPayload,
  type TodayCounters,
  type TodayFilter,
  type TodayPayload,
} from '../../services/accountingOfficeApi';
import {
  clientFilePath,
  officeSizeOf,
  readTodayFilter,
  showsOfficeAssignment,
  todayFilterParams,
} from '../../utils/accountingOffice';
import { formatDateLocalized } from '../../utils/formatDate';
import { humanizeThrown } from '../../utils/drfError';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import { OfficeObligationRow } from './OfficeObligationRow';
import {
  OfficeEmpty,
  OfficeError,
  OfficeSkeleton,
  officeSecondaryButtonClass,
} from './OfficeUi';

type CounterKey = keyof TodayCounters;

/** العدّاداتُ الأربعة (#276) — كبسةٌ تُفلتر، والعددُ من الخادم **قبل** الفلتر. */
const COUNTERS: { filter: TodayFilter; label: string; counter: CounterKey }[] = [
  { filter: 'late', label: 'متأخّر رسمي', counter: 'late' },
  { filter: 'late_internal', label: 'متأخّر داخلي', counter: 'late_internal' },
  { filter: 'week', label: 'قريب هالأسبوع', counter: 'week' },
  { filter: '', label: 'الكل', counter: 'all' },
];

/** الرقائقُ الثلاث — و«شغلي» تُخفى في مكتب «شخص واحد» (لا موظفَ غيره). */
const CHIPS: { filter: TodayFilter; label: string }[] = [
  { filter: 'mine', label: 'شغلي' },
  { filter: 'week', label: 'هالأسبوع' },
  { filter: 'late', label: 'متأخّر رسمي' },
];

/**
 * ISSUE #275 — شاشةُ «اليوم»: ما حان وقتُه من التزاماتٍ على زبائن العضو.
 *
 * **الخادمُ يعمل قبل الشاشة**: أوّلُ طلبٍ في اليوم يُشغّل `ensure_office_refreshed`
 * (سجلُّ `OfficeRefreshRun` يمنع التكرار)، فما ظهر هنا محفوظٌ لا محسوب.
 *
 * **والفلترُ في العنوان** (`?filter=`) عبر `useSearchParams`: يبقى بعد التحديث
 * وبعد العودة من ملفّ الزبون. والعدّاداتُ تُحسب على كلّ الميل قبل الفلتر — فلا
 * تُصفّر كبسةُ «متأخّر رسمي» عدّادَ «قريب».
 *
 * **والمشتقُّ من الخادم**: الشاراتُ تُحسب على يوم الطلب ولا تُخزَّن، وتسمياتُ
 * الحالة والاتجاه والشارة تصل نصوصاً — لا جدولَ تسمياتٍ هنا. وردُّ الطلب القديم
 * يُتجاهَل عند تغيّر الفلتر (علمُ `cancelled`)، فلا يكتب فوق أحدث منه.
 */
export const OfficeTodayScreen: React.FC = () => {
  const navigate = useNavigate();
  const toast = useToast();
  // الخادمُ هو الحكم: هذه الأعلام تُخفي ولا تحمي.
  const { can } = usePermissions();
  const canWrite = can('office.clients.write');
  const canSeeAmounts = can('office.amounts.view');
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = readTodayFilter(`?${searchParams.toString()}`);
  const [settings, setSettings] = useState<OfficeSettingsPayload | null>(null);
  const [payload, setPayload] = useState<TodayPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshToken, setRefreshToken] = useState(0);

  const officeSize = settings ? officeSizeOf(settings.settings) : null;
  const showsAssignment = showsOfficeAssignment(officeSize);
  const counters = payload?.counters ?? { late: 0, late_internal: 0, week: 0, all: 0 };
  const rows = payload?.rows ?? [];
  const day = payload?.day ?? '';
  const directionChoices = payload?.direction_choices ?? [];

  // حجمُ المكتب مرّةً واحدة: يخفي «شغلي» واسمَ المحوَّل إليه في «شخص واحد».
  useEffect(() => {
    let cancelled = false;
    getOfficeSettings()
      .then((data) => {
        if (!cancelled) setSettings(data);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    getOfficeToday(filter)
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch((failure) => {
        if (!cancelled) {
          // لا تُعرض صفوفُ طلبٍ سابق مع رسالة الفشل.
          setPayload(null);
          setError(humanizeThrown(failure, 'تعذّر تحميل التزامات اليوم.'));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filter, refreshToken]);

  const reload = useCallback(() => setRefreshToken((token) => token + 1), []);
  const setFilter = useCallback(
    (next: TodayFilter) => setSearchParams(todayFilterParams(next)),
    [setSearchParams],
  );

  return (
    <div className="space-y-4">
      <header className="rounded-xl border border-slate-200 bg-white p-4 md:p-5 dark:border-slate-700 dark:bg-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-[20px] font-bold text-slate-900 dark:text-slate-100">اليوم</h1>
            <p className="mt-1 text-[12px] text-slate-500 dark:text-slate-400">
              {day ? `${formatDateLocalized(day)} — ` : ''}
              الالتزامات التي حان وقتُها على زبائنك.
            </p>
          </div>
          <button type="button" onClick={reload} className={officeSecondaryButtonClass}>
            حدّث
          </button>
        </div>

        {/* العدّاداتُ صفّاً أفقياً يتمرّر على الجوال (كالنموذج): العددُ على كلّ
            الميل قبل الفلتر، والكبسةُ تُفلتر. حوافُّ الحاوية تُعاكس حشوةَ الرأس
            كي يبلغ التمريرُ الحافّة ولا يُقصّ أوّلُ عدّاد. */}
        <div className="-mx-4 mt-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] md:-mx-5 md:px-5">
          {COUNTERS.map((entry) => (
            <button
              key={entry.label}
              type="button"
              onClick={() => setFilter(entry.filter)}
              aria-pressed={filter === entry.filter}
              className={`shrink-0 rounded-xl border px-3 py-2 text-center transition ${
                filter === entry.filter
                  ? 'border-teal-300 bg-teal-50 dark:border-teal-800 dark:bg-teal-950/40'
                  : 'border-slate-200 bg-white hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800'
              }`}
            >
              <span
                className={`block text-[17px] font-bold leading-6 tabular-nums ${
                  entry.counter === 'late'
                    ? 'text-rose-600 dark:text-rose-400'
                    : entry.counter === 'late_internal'
                      ? 'text-amber-600 dark:text-amber-400'
                      : 'text-slate-900 dark:text-slate-100'
                }`}
              >
                {counters[entry.counter]}
              </span>
              <span className="mt-0.5 block whitespace-nowrap text-[10px] font-medium text-slate-500 dark:text-slate-400">
                {entry.label}
              </span>
            </button>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {CHIPS.filter((entry) => showsAssignment || entry.filter !== 'mine').map((entry) => (
            <button
              key={entry.label}
              type="button"
              onClick={() => setFilter(entry.filter)}
              aria-pressed={filter === entry.filter}
              className={
                filter === entry.filter
                  ? 'rounded-full bg-teal-700 px-3 py-1 text-[11.5px] font-semibold text-white'
                  : 'rounded-full border border-slate-200 px-3 py-1 text-[11.5px] font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300'
              }
            >
              {entry.label}
            </button>
          ))}
        </div>
      </header>

      {error ? <OfficeError message={error} onRetry={reload} /> : null}

      {loading ? (
        <OfficeSkeleton rows={5} />
      ) : !error && rows.length === 0 ? (
        <OfficeEmpty
          title="لا التزامات في هذا الفلتر"
          hint="جرّب «الكل»، أو افتح ملفّ زبونٍ لتضيف له خدمةً تُولّد التزاماتها."
        />
      ) : (
        <div className="space-y-3">
          {rows.map((row) => (
            <article
              key={row.id}
              className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
            >
              <OfficeObligationRow
                obligation={row}
                day={day}
                directionChoices={directionChoices}
                canWrite={canWrite}
                canSeeAmounts={canSeeAmounts}
                onChanged={reload}
                onError={(message) => toast(message, 'error')}
                showClient
                showAssignee={showsAssignment}
                onOpenClient={() => navigate(clientFilePath(row.client.id))}
              />
            </article>
          ))}
        </div>
      )}
    </div>
  );
};
