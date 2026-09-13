import React, { useEffect, useState } from 'react';
import { CalendarClock, TrendingDown, TrendingUp } from 'lucide-react';

import { getPresenceLog, type PresenceLog } from '../../../services/platformPresenceApi';
import { formatDateValue } from '../../../utils/formatDate';
import { formatNumber } from '../../../utils/formatNumber';
import { formatPresenceClock } from '../../../utils/presenceClock';

/**
 * سجلُّ الحضورِ اليوميّ وأثرُه في التقييم (#212 212-D).
 *
 * المالكُ طلب ثلاثةَ أشياءَ عن العدّاد: أن يظهر على الموظّف · أن يكون **في
 * السجلّ يوميّاً بمجموع اليوم** · وأن يكون **واضحاً في التقييم**. والأوّلُ في
 * الشريط العلويّ، وهذان هنا.
 *
 * و«واضحٌ في التقييم» تعني الرقمَ **قبل وبعد**: خصمٌ لا يرى صاحبُه مقدارَه ولا
 * سببَه شكوى قادمةٌ لا تقييم. ولذلك تُعرَض العتبةُ والسقفُ من السياسة أيضاً —
 * فالموظّفُ يعرف القاعدةَ التي حُوسِب بها لا نتيجتَها وحدَها.
 */
export const StaffPresencePanel: React.FC = () => {
  const [log, setLog] = useState<PresenceLog | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const next = await getPresenceLog();
        if (alive) { setLog(next); setError(''); }
      } catch (caught: unknown) {
        if (alive) setError(caught instanceof Error ? caught.message : 'تعذر تحميل سجل حضورك.');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  if (loading) {
    return (
      <p className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 text-sm text-[var(--staff-muted)]" role="status">
        جارٍ تحميل سجل حضورك...
      </p>
    );
  }
  if (error) {
    return (
      <p className="rounded-2xl border border-rose-400/40 bg-[var(--staff-panel)] p-5 text-sm text-rose-300" role="alert">
        {error}
      </p>
    );
  }
  if (!log) return null;

  // المعامِلُ واحدٌ = لا خصمَ ولا زيادة؛ وأكبرُ من واحدٍ = ترقية.
  const isDeduction = log.is_applicable && log.factor < 1;
  const isBonus = log.is_applicable && log.factor > 1;

  return (
    <section
      className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30"
      aria-label="سجل الحضور وأثره في التقييم"
    >
      <h2 className="flex items-center gap-2 text-base font-extrabold text-[var(--staff-text)]">
        <CalendarClock className="h-5 w-5 text-cyan-300" />
        حضورك على المنصة
      </h2>
      <p className="mt-1 text-sm text-[var(--staff-muted)]">
        المطلوب {formatNumber(log.min_hours_per_day)} ساعات في اليوم — وما زاد يرفع درجتك حتى{' '}
        {formatNumber(log.day_cap_percent)}٪، وما قلّ يخصم منها.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <article className="rounded-xl border border-[var(--staff-line)] bg-black/15 p-4">
          <p className="text-xs font-semibold text-[var(--staff-muted)]">اليوم</p>
          <p className="mt-1 font-mono text-2xl font-extrabold text-cyan-300" dir="ltr">
            {formatPresenceClock(log.today.active_seconds)}
          </p>
        </article>
        <article className="rounded-xl border border-[var(--staff-line)] bg-black/15 p-4">
          <p className="text-xs font-semibold text-[var(--staff-muted)]">مجموع الشهر</p>
          <p className="mt-1 text-2xl font-extrabold text-[var(--staff-text)]">
            {formatNumber(log.total_hours)} <span className="text-sm font-bold">ساعة</span>
          </p>
          <p className="mt-1 text-xs text-[var(--staff-muted)]">
            في {formatNumber(log.days_counted)} يوم عمل
          </p>
        </article>
        <article className="rounded-xl border border-[var(--staff-line)] bg-black/15 p-4">
          <p className="text-xs font-semibold text-[var(--staff-muted)]">أثره في درجتك</p>
          {!log.is_applicable ? (
            <p className="mt-2 text-sm text-[var(--staff-muted)]">
              لا سجلَ بعد هذا الشهر — فلا خصمَ ولا زيادة.
            </p>
          ) : (
            <p className={`mt-1 flex items-center gap-1 text-2xl font-extrabold ${isDeduction ? 'text-rose-300' : isBonus ? 'text-emerald-300' : 'text-[var(--staff-text)]'}`}>
              {isDeduction ? <TrendingDown className="h-5 w-5" /> : isBonus ? <TrendingUp className="h-5 w-5" /> : null}
              ×{formatNumber(log.factor)}
            </p>
          )}
          {log.score_before !== null && log.score_before !== undefined && log.score_after !== null && log.score_after !== undefined && (
            // **الرقمان معاً**: الدرجةُ قبل الحضور وبعده، فلا خصمَ مجهولَ المقدار.
            <p className="mt-2 text-xs text-[var(--staff-muted)]">
              {formatNumber(log.score_before)} ← <strong className="text-[var(--staff-text)]">{formatNumber(log.score_after)}</strong>
            </p>
          )}
        </article>
      </div>

      {log.days.length > 0 && (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-bold text-cyan-300">
            التفصيل اليومي ({formatNumber(log.days.length)} يوم)
          </summary>
          <ul className="mt-3 divide-y divide-[var(--staff-line)]">
            {log.days.map((day) => {
              const met = day.hours >= log.min_hours_per_day;
              return (
                <li key={day.date} className="flex items-center justify-between py-2 text-sm">
                  <span className="text-[var(--staff-muted)]">{formatDateValue(day.date)}</span>
                  <span className={`font-mono font-bold ${met ? 'text-emerald-300' : 'text-amber-300'}`} dir="ltr">
                    {formatNumber(day.hours)}
                  </span>
                </li>
              );
            })}
          </ul>
        </details>
      )}
    </section>
  );
};
