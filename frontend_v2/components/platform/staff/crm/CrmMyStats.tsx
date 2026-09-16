import React, { useEffect, useState } from 'react';

import { getMyCrmStats, type CrmStats } from '../../../../services/platformCrmApi';
import type { CcTone } from '../../../../utils/ccTone';
import { CcCard, CcStatTile } from '../../ui';

/**
 * عدّاداتُ الموظّف عن عملائه — من `stats/me/` **مجموعةً في الخادم**.
 *
 * ولا تُحسَب من صفوف القائمة المعروضة: القائمةُ مُصفَّحةٌ وتُرشَّح بالحالة، فعدُّ
 * ما في الشاشة يعطي رقماً يصغُر كلّما رشّح الموظّفُ — رقمٌ يتغيّر بالنظر إليه.
 */
const CARDS: Array<{ key: keyof CrmStats; label: string; tone: CcTone }> = [
  { key: 'assigned', label: 'كل عملائي', tone: 'accent' },
  { key: 'contacted', label: 'تم الاتصال', tone: 'accent' },
  { key: 'interested', label: 'مهتم', tone: 'success' },
  { key: 'follow_up', label: 'متابعة', tone: 'warning' },
  { key: 'customer', label: 'صار عميلاً', tone: 'success' },
  { key: 'not_interested', label: 'غير مهتم', tone: 'danger' },
  { key: 'overdue', label: 'متأخرة', tone: 'danger' },
];

interface CrmMyStatsProps {
  /** يتغيّر بعد كلّ فعلٍ يبدّل الملكيّة أو الحالة، فتُعاد القراءة. */
  refreshKey: number;
}

export const CrmMyStats: React.FC<CrmMyStatsProps> = ({ refreshKey }: CrmMyStatsProps) => {
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
      <p className="rounded-2xl border border-cc-border bg-cc-surface p-4 text-sm text-cc-text-muted">
        {error}
      </p>
    );
  }

  return (
    <section
      className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-3"
      aria-label="عدّاداتي في العملاء"
    >
      {CARDS.map((card) => (
        <CcCard
          key={card.key}
          className="p-3.5 transition-all hover:border-cc-border-strong"
        >
          <CcStatTile
            label={card.label}
            value={stats ? stats[card.key] : '—'}
            tone={card.tone}
          />
        </CcCard>
      ))}
    </section>
  );
};
