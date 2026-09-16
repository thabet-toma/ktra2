import React, { useEffect, useState } from 'react';
import { CalendarClock, TrendingDown, TrendingUp } from 'lucide-react';

import { getPresenceLog, type PresenceLog } from '../../../services/platformPresenceApi';
import { formatDateValue } from '../../../utils/formatDate';
import { formatNumber } from '../../../utils/formatNumber';
import { formatPresenceClock } from '../../../utils/presenceClock';
import { CcCard, CcPill, CcStatTile, CcTable, CcTd, CcTh, CcThead, CcTr } from '../ui';

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
      <p className="rounded-2xl border border-cc-border bg-cc-surface p-5 text-sm text-cc-text-muted" role="status">
        جارٍ تحميل سجل حضورك...
      </p>
    );
  }
  if (error) {
    return (
      <p className="rounded-2xl border border-rose-400/40 bg-cc-surface p-5 text-sm text-rose-300" role="alert">
        {error}
      </p>
    );
  }
  if (!log) return null;

  // المعامِلُ واحدٌ = لا خصمَ ولا زيادة؛ وأكبرُ من واحدٍ = ترقية.
  const isDeduction = log.is_applicable && log.factor < 1;
  const isBonus = log.is_applicable && log.factor > 1;

  return (
    <CcCard
      className="p-5 shadow-lg shadow-black/30"
      aria-label="سجل الحضور وأثره في التقييم"
    >
      <div className="flex items-center gap-2">
        <CalendarClock className="h-5 w-5 text-sky-400" />
        <h2 className="text-base font-extrabold text-cc-text">
          حضورك على المنصة
        </h2>
      </div>
      <p className="mt-1 text-sm text-cc-text-muted">
        المطلوب {formatNumber(log.min_hours_per_day)} ساعات في اليوم — وما زاد يرفع درجتك حتى{' '}
        {formatNumber(log.day_cap_percent)}٪، وما قلّ يخصم منها.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <CcCard className="p-4 bg-cc-surface-2/60">
          <CcStatTile
            label="اليوم"
            value={formatPresenceClock(log.today.active_seconds)}
            tone="accent"
          />
        </CcCard>
        <CcCard className="p-4 bg-cc-surface-2/60">
          <CcStatTile
            label="مجموع الشهر"
            value={log.total_hours}
            unit="ساعة"
            hint={`في ${formatNumber(log.days_counted)} يوم عمل`}
            tone="neutral"
          />
        </CcCard>
        <CcCard className="p-4 bg-cc-surface-2/60">
          <CcStatTile
            label="أثره في درجتك"
            value={!log.is_applicable ? '—' : `×${formatNumber(log.factor)}`}
            // **الرقمان معاً**: الدرجةُ قبل الحضور وبعده، فلا خصمَ مجهولَ المقدار.
            hint={
              log.score_before !== null && log.score_before !== undefined && log.score_after !== null && log.score_after !== undefined
                ? `${formatNumber(log.score_before)} ← ${formatNumber(log.score_after)}`
                : !log.is_applicable
                ? 'لا سجلَ بعد هذا الشهر — فلا خصمَ ولا زيادة.'
                : undefined
            }
            tone={isDeduction ? 'danger' : isBonus ? 'success' : 'neutral'}
            icon={isDeduction ? <TrendingDown className="h-4 w-4 text-rose-400" /> : isBonus ? <TrendingUp className="h-4 w-4 text-emerald-400" /> : undefined}
          />
        </CcCard>
      </div>

      {log.days.length > 0 && (
        <details className="mt-4 group">
          <summary className="cursor-pointer text-sm font-bold text-sky-400 hover:text-sky-300 transition">
            التفصيل اليومي ({formatNumber(log.days.length)} يوم)
          </summary>
          <div className="mt-3">
            <CcTable>
              <CcThead>
                <CcTr>
                  <CcTh>التاريخ</CcTh>
                  <CcTh>ساعات الحضور</CcTh>
                  <CcTh>الحالة</CcTh>
                </CcTr>
              </CcThead>
              <tbody>
                {log.days.map((day) => {
                  const met = day.hours >= log.min_hours_per_day;
                  return (
                    <CcTr key={day.date}>
                      <CcTd className="text-cc-text-muted">{formatDateValue(day.date)}</CcTd>
                      <CcTd className="font-mono font-bold" dir="ltr">
                        {formatNumber(day.hours)}
                      </CcTd>
                      <CcTd>
                        <CcPill tone={met ? 'success' : 'warning'}>
                          {met ? 'مكتمل' : 'دون العتبة'}
                        </CcPill>
                      </CcTd>
                    </CcTr>
                  );
                })}
              </tbody>
            </CcTable>
          </div>
        </details>
      )}
    </CcCard>
  );
};
