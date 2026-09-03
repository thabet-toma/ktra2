import React from 'react';

import type { PracticeDeadlineItem } from '../../../services/accountantPracticeApi';
import { formatDateValue } from '../../../utils/formatDate';
import { formatNumber } from '../../../utils/formatNumber';
import { OfficeBadge, OfficeCard, OfficeEmpty } from './OfficeUi';

export const DEADLINE_KIND_LABELS: Record<PracticeDeadlineItem['kind'], string> = {
  program: 'برنامج مراجعة',
  appointment: 'موعد',
  deadline: 'استحقاق',
  filing: 'تقديم إقرار',
};

const KIND_TONES: Record<PracticeDeadlineItem['kind'], string> = {
  program: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200',
  appointment: 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200',
  deadline: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200',
  filing: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
};

/** نصّ المهلة بلغة المكتب: المتأخر يقول كم تأخّر، لا «‎-3 يوم». */
export function deadlineDueLabel(item: Pick<PracticeDeadlineItem, 'days_left'>): string {
  if (item.days_left < 0) return `تأخّر ${formatNumber(Math.abs(item.days_left))} يوماً`;
  if (item.days_left === 0) return 'اليوم';
  if (item.days_left === 1) return 'غداً';
  return `بعد ${formatNumber(item.days_left)} يوماً`;
}

export const DeadlineRow: React.FC<{
  item: PracticeDeadlineItem;
  onOpen?: (item: PracticeDeadlineItem) => void;
}> = ({ item, onOpen }) => (
  <li
    className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3 ${
      item.is_overdue
        ? 'border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950'
        : 'border-slate-200 dark:border-slate-800'
    }`}
  >
    <div className="min-w-0">
      <p className="font-bold text-slate-900 dark:text-white">{item.title}</p>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        {item.partner_name || 'المكتب'} · {formatDateValue(item.due_date)}
      </p>
    </div>
    <div className="flex flex-wrap items-center gap-2">
      <OfficeBadge tone={KIND_TONES[item.kind]}>{DEADLINE_KIND_LABELS[item.kind]}</OfficeBadge>
      <span className={`text-sm font-bold ${item.is_overdue ? 'text-red-700 dark:text-red-300' : 'text-slate-600 dark:text-slate-300'}`}>
        {deadlineDueLabel(item)}
      </span>
      {onOpen && (item.partner_id || item.tenant_id) && (
        <button type="button" onClick={() => onOpen(item)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-bold dark:border-slate-700">
          افتح الملف
        </button>
      )}
    </div>
  </li>
);

/** شريط «مواعيد قريبة» على لوحة المكتب — أقرب ما يستحق، لا الأجندة كلها. */
export const DeadlinesStrip: React.FC<{
  items: PracticeDeadlineItem[];
  overdue: number;
  onOpen?: (item: PracticeDeadlineItem) => void;
  onSeeAll: () => void;
  limit?: number;
}> = ({ items, overdue, onOpen, onSeeAll, limit = 5 }) => (
  <OfficeCard
    title="مواعيد قريبة"
    actions={(
      <div className="flex items-center gap-3">
        {overdue > 0 && (
          <OfficeBadge tone="bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200">
            {formatNumber(overdue)} متأخّر
          </OfficeBadge>
        )}
        <button type="button" onClick={onSeeAll} className="rounded-xl border border-indigo-600 px-4 py-2 text-sm font-bold text-indigo-700 dark:text-indigo-300">
          كل المواعيد
        </button>
      </div>
    )}
  >
    {items.length === 0 ? (
      <OfficeEmpty title="لا مواعيد قريبة" hint="أضف برنامج مراجعة أو موعداً من ملف الزبون ليظهر هنا." />
    ) : (
      <ul className="space-y-2">
        {items.slice(0, limit).map((item) => (
          <DeadlineRow key={`${item.kind}-${item.id ?? item.partner_name}-${item.due_date}`} item={item} onOpen={onOpen} />
        ))}
      </ul>
    )}
  </OfficeCard>
);
