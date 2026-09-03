import React, { useCallback, useEffect, useState } from 'react';

import { getPracticeDashboard, type PracticeDeadlineItem } from '../../../services/accountantPracticeApi';
import { useToast } from '../../../contexts/ToastContext';
import { formatDateValue } from '../../../utils/formatDate';
import { formatNumber } from '../../../utils/formatNumber';
import {
  OFFICE_CLIENT_TYPE_LABELS,
  OFFICE_CLIENT_TYPE_TONES,
  summarizeOfficeDashboard,
  type OfficeDashboardPayload,
} from '../../../utils/officeDashboardSections';
import { DeadlinesStrip } from './OfficeDeadlines';
import { OfficeBadge, OfficeCard, OfficeEmpty, OfficeError, OfficeSkeleton, OfficeStat, OfficeTable } from './OfficeUi';

/**
 * ISSUE #58 — لوحة المكتب: أول ما يراه صاحب المكتب (أو موظفٌ مُسنَد إلى بعض
 * زبائنه، القرار 7) حين يدخل. ثلاثة عناصر لا رابع — عمداً لا شكل اللوحة
 * القديمة (قيد المالك): قائمة الزبائن وحالة كل دفتر وآخر نشاط، الاستحقاقات
 * القريبة، والأتعاب غير المحصّلة. كل الأرصدة من `practice/dashboard/` بنداء
 * واحد بعدد استعلامات ثابت مهما كثر الزبائن.
 */
export const OfficeDashboardPage: React.FC<{
  onOpenClient: (client: { tenant_id: number; company_name: string }) => void;
  onGoToClients: () => void;
  onGoToAgenda: () => void;
  onOpenPracticeClient: (clientId: number) => void;
}> = ({ onOpenClient, onGoToClients, onGoToAgenda, onOpenPracticeClient }) => {
  const toast = useToast();
  const [data, setData] = useState<OfficeDashboardPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    getPracticeDashboard()
      .then(setData)
      .catch(() => {
        setError('تعذّر تحميل لوحة المكتب.');
        toast('تعذّر تحميل لوحة المكتب.', 'error');
      })
      .finally(() => setLoading(false));
  }, [toast]);

  useEffect(load, [load]);

  // نفس منطق فتح بند الأجندة في `OfficeAgendaPage`: موعد تقديمٍ يفتح دفاتر
  // الشركة، وبرنامج أو موعد مكتب يفتح ملف الزبون.
  const openDeadline = (item: PracticeDeadlineItem) => {
    if (item.kind === 'filing' && item.tenant_id) {
      onOpenClient({ tenant_id: item.tenant_id, company_name: item.partner_name });
      return;
    }
    if (item.partner_id) onOpenPracticeClient(item.partner_id);
  };

  if (loading) return <OfficeSkeleton rows={6} />;
  if (error) return <OfficeError message={error} onRetry={load} />;
  if (!data) return null;

  const summary = summarizeOfficeDashboard(data);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <OfficeStat label="عدد الزبائن الظاهرين لك" value={formatNumber(summary.clientsTotal)} />
        <OfficeStat
          label="استحقاقات قريبة"
          value={formatNumber(data.deadlines.totals.due_soon)}
          hint={`${formatNumber(data.deadlines.totals.overdue)} متأخّرة`}
          tone={data.deadlines.totals.overdue > 0 ? 'negative' : 'neutral'}
        />
        <OfficeStat
          label="أتعاب غير محصّلة"
          value={formatNumber(summary.unpaidFeesTotal)}
          hint={`${formatNumber(summary.unpaidFeesCount)} فاتورة`}
          tone={summary.unpaidFeesCount > 0 ? 'accent' : 'positive'}
        />
      </div>

      <OfficeCard
        title="زبائن المكتب"
        actions={(
          <button type="button" onClick={onGoToClients} className="rounded-xl border border-indigo-600 px-4 py-2 text-sm font-bold text-indigo-700 dark:text-indigo-300">
            كل الزبائن
          </button>
        )}
      >
        {data.clients.length === 0 ? (
          <OfficeEmpty title="لا زبائن بعد" hint="اطلب ملف شركة أو أضِف زبوناً من «زبائني» ليبدأ عملك." />
        ) : (
          <OfficeTable
            columns={[
              { key: 'name', header: 'الزبون' },
              { key: 'state', header: 'حالة الدفتر' },
              { key: 'activity', header: 'آخر نشاط' },
              { key: 'open', header: '' },
            ]}
            rows={data.clients.map((client) => ({
              __key: client.id,
              name: <span className="font-bold text-slate-900 dark:text-white">{client.trade_name}</span>,
              state: (
                <OfficeBadge tone={OFFICE_CLIENT_TYPE_TONES[client.client_type]}>
                  {OFFICE_CLIENT_TYPE_LABELS[client.client_type]}
                </OfficeBadge>
              ),
              activity: formatDateValue(client.last_activity),
              open: (
                <button
                  type="button"
                  onClick={() => onOpenPracticeClient(client.id)}
                  className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-bold dark:border-slate-700"
                >
                  افتح الملف
                </button>
              ),
            }))}
          />
        )}
      </OfficeCard>

      <DeadlinesStrip
        items={data.deadlines.items}
        overdue={data.deadlines.totals.overdue}
        onOpen={openDeadline}
        onSeeAll={onGoToAgenda}
      />

      <OfficeCard title="الأتعاب غير المحصّلة">
        {data.unpaid_fees.invoices.length === 0 ? (
          <OfficeEmpty title="لا أتعاب غير محصّلة" hint="كل فواتير الأتعاب المرحّلة مُسدَّدة بالكامل." />
        ) : (
          <OfficeTable
            columns={[
              { key: 'number', header: 'الفاتورة' },
              { key: 'customer', header: 'الزبون' },
              { key: 'date', header: 'التاريخ' },
              { key: 'remaining', header: 'المتبقّي', numeric: true },
            ]}
            rows={data.unpaid_fees.invoices.map((invoice) => ({
              __key: invoice.invoice_id,
              number: invoice.invoice_number,
              customer: invoice.customer_name,
              date: formatDateValue(invoice.invoice_date),
              remaining: formatNumber(invoice.remaining),
            }))}
            footer={{ number: 'الإجمالي', remaining: formatNumber(data.unpaid_fees.total) }}
          />
        )}
      </OfficeCard>
    </div>
  );
};

export default OfficeDashboardPage;
