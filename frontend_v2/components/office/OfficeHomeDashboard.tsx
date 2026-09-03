import React, { useCallback, useEffect, useState } from 'react';

import { getPracticeDashboard } from '../../services/accountantPracticeApi';
import { useToast } from '../../contexts/ToastContext';
import { formatDateValue } from '../../utils/formatDate';
import { formatNumber } from '../../utils/formatNumber';
import {
  OFFICE_CLIENT_TYPE_LABELS,
  OFFICE_CLIENT_TYPE_TONES,
  summarizeOfficeDashboard,
  type OfficeDashboardPayload,
} from '../../utils/officeDashboardSections';
import { DeadlineRow } from '../accountant/office/OfficeDeadlines';
import { OfficeBadge, OfficeCard, OfficeEmpty, OfficeError, OfficeSkeleton, OfficeStat, OfficeTable } from '../accountant/office/OfficeUi';

/**
 * ISSUE #87 — شاشة بداية قالب «مكتب محاسبة»: تُرسَم داخل شركة المكتب نفسها
 * (لا سطح `/office` المنفصل الذي يديره `AccountantOfficeApp`)، فبلا تنقّلٍ
 * بين شركات هنا — ذاك يبقى في `OfficeDashboardPage`. نفس البيانات حرفياً
 * وبنفس القيد (ثلاثة عناصر لا رابع، القرار 24 في #46): عملاؤك وحالة دفتر
 * كلٍّ منهم · الاستحقاقات القريبة · الأتعاب غير المحصّلة — كلّها من
 * `practice/dashboard/` (ISSUE #58، يعيد استعمال `practice_overview`
 * و`practice_deadlines`) بنداءٍ واحد بعدد استعلامات ثابت مهما كثر العملاء.
 */
export const OfficeHomeDashboard: React.FC = () => {
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

  if (loading) return <OfficeSkeleton rows={6} />;
  if (error) return <OfficeError message={error} onRetry={load} />;
  if (!data) return null;

  const summary = summarizeOfficeDashboard(data);
  const nearDeadlines = data.deadlines.items.slice(0, 5);

  return (
    <div dir="rtl" className="space-y-6 p-4 sm:p-6">
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

      <OfficeCard title="زبائن المكتب">
        {data.clients.length === 0 ? (
          <OfficeEmpty title="لا زبائن بعد" hint="أضِف زبوناً من «زبائني» في مكتبك ليبدأ عملك." />
        ) : (
          <OfficeTable
            columns={[
              { key: 'name', header: 'الزبون' },
              { key: 'state', header: 'حالة الدفتر' },
              { key: 'activity', header: 'آخر نشاط' },
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
            }))}
          />
        )}
      </OfficeCard>

      <OfficeCard
        title="مواعيد قريبة"
        actions={data.deadlines.totals.overdue > 0 ? (
          <OfficeBadge tone="bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200">
            {formatNumber(data.deadlines.totals.overdue)} متأخّر
          </OfficeBadge>
        ) : undefined}
      >
        {nearDeadlines.length === 0 ? (
          <OfficeEmpty title="لا مواعيد قريبة" hint="أضف برنامج مراجعة أو موعداً من ملف الزبون ليظهر هنا." />
        ) : (
          <ul className="space-y-2">
            {nearDeadlines.map((item) => (
              <DeadlineRow key={`${item.kind}-${item.id ?? item.partner_name}-${item.due_date}`} item={item} />
            ))}
          </ul>
        )}
      </OfficeCard>

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

export default OfficeHomeDashboard;
