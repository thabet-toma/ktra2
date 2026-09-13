import React, { useEffect, useState } from 'react';

import { getMyCrmStats, type CrmStats } from '../../../../services/platformCrmApi';
import { formatNumber } from '../../../../utils/formatNumber';

/**
 * عدّاداتُ الموظّف عن عملائه — من `stats/me/` **مجموعةً في الخادم**.
 *
 * ولا تُحسَب من صفوف القائمة المعروضة: القائمةُ مُصفَّحةٌ وتُرشَّح بالحالة، فعدُّ
 * ما في الشاشة يعطي رقماً يصغُر كلّما رشّح الموظّفُ — رقمٌ يتغيّر بالنظر إليه.
 */
const CARDS: Array<{ key: keyof CrmStats; label: string; tone: string }> = [
  { key: 'assigned', label: 'كل عملائي', tone: 'text-cyan-300' },
  { key: 'contacted', label: 'تم الاتصال', tone: 'text-sky-300' },
  { key: 'interested', label: 'مهتم', tone: 'text-emerald-300' },
  { key: 'follow_up', label: 'متابعة', tone: 'text-amber-300' },
  { key: 'customer', label: 'صار عميلاً', tone: 'text-emerald-200' },
  { key: 'not_interested', label: 'غير مهتم', tone: 'text-rose-300' },
  { key: 'overdue', label: 'متأخرة', tone: 'text-rose-300' },
];

interface CrmMyStatsProps {
  /** يتغيّر بعد كلّ فعلٍ يبدّل الملكيّة أو الحالة، فتُعاد القراءة. */
  refreshKey: number;
}

export const CrmMyStats: React.FC<CrmMyStatsProps> = ({ refreshKey }) => {
  const [stats, setStats] = useState<CrmStats | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const next = await getMyCrmStats();
        if (alive) { setStats(next); setError(''); }
      } catch (caught: unknown) {
        // الفشلُ هنا لا يحجب الشاشة: العدّاداتُ ملخَّصٌ لا شرطُ عمل.
        if (alive) { setStats(null); setError(caught instanceof Error ? caught.message : 'تعذر تحميل عدّاداتك.'); }
      }
    })();
    return () => { alive = false; };
  }, [refreshKey]);

  if (error) {
    return (
      <p className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-4 text-sm text-[var(--staff-muted)]">
        {error}
      </p>
    );
  }

  return (
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6" aria-label="عدّاداتي في العملاء">
      {CARDS.map((card) => (
        <article
          key={card.key}
          className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-4 shadow-lg shadow-black/30"
        >
          <p className={`text-2xl font-extrabold ${card.tone}`}>
            {stats ? formatNumber(stats[card.key]) : '—'}
          </p>
          <p className="mt-1 text-xs font-semibold text-[var(--staff-muted)]">{card.label}</p>
        </article>
      ))}
    </section>
  );
};
