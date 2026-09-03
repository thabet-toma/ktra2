import React, { useCallback, useEffect, useState } from 'react';

import {
  getPracticeDeadlines,
  listPracticeClients,
  type PracticeDeadlineItem,
  type PracticeDeadlines,
} from '../../../services/accountantPracticeApi';
import { formatDateValue } from '../../../utils/formatDate';
import { formatNumber } from '../../../utils/formatNumber';
import { TasksPanel } from './OfficeClientWork';
import { DeadlineRow } from './OfficeDeadlines';
import { OfficeCard, OfficeEmpty, OfficeError, OfficeSkeleton, OfficeStat } from './OfficeUi';

type Filter = 'all' | 'overdue' | 'soon';

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'الكل' },
  { key: 'overdue', label: 'متأخّر' },
  { key: 'soon', label: 'خلال أسبوع' },
];

const matches = (item: PracticeDeadlineItem, filter: Filter) => {
  if (filter === 'overdue') return item.is_overdue;
  if (filter === 'soon') return item.days_left >= 0 && item.days_left <= 7;
  return true;
};

/**
 * «المواعيد والمهام» — أجندة المكتب كاملةً: برامج المراجعة ومواعيد المكتب
 * ومواعيد تقديم إقرارات الشركات المرتبطة، مدموجةً في الخادم ومرتّبة بالاستحقاق.
 * هذه هي الشاشة التي تجيب سؤال المحاسب الأول في يومه: **ما الذي يستحق اليوم؟**
 */
export const OfficeAgendaPage: React.FC<{
  onOpenPlatformClient: (client: { tenant_id: number; company_name: string }) => void;
  onOpenPracticeClient: (clientId: number) => void;
}> = ({ onOpenPlatformClient, onOpenPracticeClient }) => {
  const [data, setData] = useState<PracticeDeadlines | null>(null);
  const [clients, setClients] = useState<{ id: number; name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<Filter>('all');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([getPracticeDeadlines(), listPracticeClients()])
      .then(([deadlines, clientsRes]) => {
        setData(deadlines);
        setClients(clientsRes.results.map((client) => ({ id: client.id, name: client.trade_name })));
      })
      .catch(() => setError('تعذّر تحميل أجندة المكتب.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const open = (item: PracticeDeadlineItem) => {
    if (item.kind === 'filing' && item.tenant_id) {
      onOpenPlatformClient({ tenant_id: item.tenant_id, company_name: item.partner_name });
      return;
    }
    if (item.partner_id) onOpenPracticeClient(item.partner_id);
  };

  if (loading) return <OfficeSkeleton rows={6} />;
  if (error) return <OfficeError message={error} onRetry={load} />;
  if (!data) return null;

  const visible = data.items.filter((item) => matches(item, filter));

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <OfficeStat label="كل الاستحقاقات" value={formatNumber(data.totals.count)} hint={`محسوبة على ${formatDateValue(data.today)}`} />
        <OfficeStat label="متأخّر" value={formatNumber(data.totals.overdue)} tone={data.totals.overdue > 0 ? 'negative' : 'positive'} />
        <OfficeStat label="خلال أسبوع" value={formatNumber(data.totals.due_soon)} tone="accent" />
      </div>

      <OfficeCard
        title={`الأجندة (${formatNumber(visible.length)})`}
        actions={(
          <div className="flex flex-wrap gap-2" role="group" aria-label="تصفية الأجندة">
            {FILTERS.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setFilter(item.key)}
                aria-pressed={filter === item.key}
                className={`rounded-lg px-3 py-1.5 text-sm font-bold ${
                  filter === item.key ? 'bg-indigo-700 text-white' : 'border border-slate-300 dark:border-slate-700'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}
      >
        {visible.length === 0 ? (
          <OfficeEmpty
            title={filter === 'all' ? 'لا استحقاقات' : 'لا شيء في هذه التصفية'}
            hint={filter === 'all'
              ? 'برامج المراجعة ومواعيدك ومواعيد تقديم الشركات المرتبطة تظهر هنا كلها.'
              : 'جرّب «الكل» لرؤية بقية الأجندة.'}
          />
        ) : (
          <ul className="space-y-2">
            {visible.map((item) => (
              <DeadlineRow key={`${item.kind}-${item.id ?? item.partner_name}-${item.due_date}`} item={item} onOpen={open} />
            ))}
          </ul>
        )}
      </OfficeCard>

      <TasksPanel clients={clients} onChanged={load} />
    </div>
  );
};

export default OfficeAgendaPage;
