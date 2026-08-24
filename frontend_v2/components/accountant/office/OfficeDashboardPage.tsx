import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CalendarClock, Receipt, TrendingUp, Users } from 'lucide-react';

import { getPracticeOverview, type PracticeClientRow } from '../../../services/accountantApi';
import {
  getPracticeDeadlines,
  type PracticeDeadlineItem,
  type PracticeDeadlines,
} from '../../../services/accountantPracticeApi';
import { formatNumber } from '../../../utils/formatNumber';
import { DeadlinesStrip } from './OfficeDeadlines';
import { OfficeCard, OfficeEmpty, OfficeError, OfficeSkeleton, OfficeStat } from './OfficeUi';

/**
 * لوحة المكتب — الشاشة التي يفتحها المحاسب صباحاً: أرقام الشهر لكل الزبائن،
 * ومَن يحتاج انتباهاً، وكم بقي على موعد التقديم. نمط لوحات المكاتب المهنية
 * (Karbon/Canopy/TaxDome): العمل أولاً، لا قوائم جوفاء.
 */
export const OfficeDashboardPage: React.FC<{
  onOpenClient: (client: { tenant_id: number; company_name: string }) => void;
  onGoToClients: () => void;
  onGoToAgenda: () => void;
  onOpenPracticeClient: (clientId: number) => void;
}> = ({ onOpenClient, onGoToClients, onGoToAgenda, onOpenPracticeClient }) => {
  const [data, setData] = useState<Awaited<ReturnType<typeof getPracticeOverview>> | null>(null);
  const [deadlines, setDeadlines] = useState<PracticeDeadlines | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    // الأجندة قسمٌ مستقل من اللوحة: تعثّرها لا يُسقط أرقام الشهر كلها، فتُبتلع
    // هنا ويبقى الشريط فارغاً بدل شاشة خطأ كاملة.
    Promise.all([
      getPracticeOverview(),
      getPracticeDeadlines().catch(() => null),
    ])
      .then(([overview, agenda]) => { setData(overview); setDeadlines(agenda); })
      .catch(() => setError('تعذّر تحميل لوحة المكتب.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const openDeadline = (item: PracticeDeadlineItem) => {
    if (item.kind === 'filing' && item.tenant_id) {
      onOpenClient({ tenant_id: item.tenant_id, company_name: item.client_name });
      return;
    }
    if (item.client_id) onOpenPracticeClient(item.client_id);
  };

  if (loading) return <OfficeSkeleton rows={6} />;
  if (error) return <OfficeError message={error} onRetry={load} />;
  if (!data) return null;

  const attention = data.clients.filter((client) => client.needs_attention || client.days_to_filing <= 5);

  const dueTone = (client: PracticeClientRow) =>
    client.days_to_filing < 0
      ? 'bg-red-100 text-red-800'
      : client.days_to_filing <= 5
        ? 'bg-amber-100 text-amber-800'
        : 'bg-slate-100 text-slate-700';

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <OfficeStat label="عدد الزبائن" value={formatNumber(data.totals.clients)} hint="ملفات نشطة تحت يدك" />
        <OfficeStat
          label="ضريبة الشهر المستحقة"
          value={formatNumber(data.totals.vat_due)}
          hint={`${data.period_from} → ${data.period_to}`}
          tone="accent"
        />
        <OfficeStat
          label="أرباح الزبائن هذا الشهر"
          value={formatNumber(data.totals.profit)}
          tone={Number(data.totals.profit) >= 0 ? 'positive' : 'negative'}
        />
        <OfficeStat
          label="ملفات تحتاج انتباهاً"
          value={formatNumber(data.totals.needs_attention)}
          hint={`${formatNumber(data.totals.draft_documents)} مستند غير مرحَّل`}
          tone={data.totals.needs_attention > 0 ? 'negative' : 'positive'}
        />
      </div>

      {/* الفحص على الشكل لا على الصدق: استجابةٌ **ناجحة** بشكلٍ غير متوقّع
          (قائمة فارغة بدل كائن) تجعل `deadlines` صادقاً و`totals` معدوماً،
          فتنهار اللوحة كلها بيضاء — وهو نقيض ما يقوله التعليق أعلاه. */}
      {Array.isArray(deadlines?.items) && deadlines?.totals && (
        <DeadlinesStrip
          items={deadlines.items}
          overdue={deadlines.totals.overdue ?? 0}
          onOpen={openDeadline}
          onSeeAll={onGoToAgenda}
        />
      )}

      {attention.length > 0 && (
        <OfficeCard title="يحتاج انتباهك الآن">
          <ul className="space-y-2">
            {attention.map((client) => (
              <li key={client.tenant_id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-900 dark:bg-amber-950">
                <span className="flex items-center gap-2 font-bold text-amber-900 dark:text-amber-100">
                  <AlertTriangle className="h-4 w-4" />
                  {client.company_name}
                </span>
                <span className="text-sm text-amber-900 dark:text-amber-200">
                  {client.draft_documents > 0 && `${formatNumber(client.draft_documents)} مستند غير مرحَّل`}
                  {client.draft_documents > 0 && client.days_to_filing <= 5 ? ' · ' : ''}
                  {client.days_to_filing < 0
                    ? `فات موعد التقديم بـ${formatNumber(Math.abs(client.days_to_filing))} يوم`
                    : client.days_to_filing <= 5
                      ? `التقديم بعد ${formatNumber(client.days_to_filing)} يوم`
                      : ''}
                </span>
                <button
                  type="button"
                  onClick={() => onOpenClient(client)}
                  className="rounded-lg bg-amber-700 px-4 py-2 text-sm font-bold text-white"
                >
                  افتح الملف
                </button>
              </li>
            ))}
          </ul>
        </OfficeCard>
      )}

      <OfficeCard
        title="زبائن المكتب هذا الشهر"
        actions={(
          <button type="button" onClick={onGoToClients} className="rounded-xl border border-indigo-600 px-4 py-2 text-sm font-bold text-indigo-700 dark:text-indigo-300">
            إدارة الزبائن وطلب ملف جديد
          </button>
        )}
      >
        {data.clients.length === 0 ? (
          <OfficeEmpty title="لا زبائن بعد" hint="اطلب ملف شركة من «زبائني» ليبدأ عملك." />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-right text-sm">
              <thead className="bg-slate-50 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                <tr>
                  <th className="px-4 py-3 font-bold">الزبون</th>
                  <th className="px-4 py-3 font-bold">الإيرادات</th>
                  <th className="px-4 py-3 font-bold">المصاريف</th>
                  <th className="px-4 py-3 font-bold">الربح</th>
                  <th className="px-4 py-3 font-bold">ضريبة مستحقة</th>
                  <th className="px-4 py-3 font-bold">موعد التقديم</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {data.clients.map((client) => (
                  <tr key={client.tenant_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/60">
                    <td className="px-4 py-3">
                      <button type="button" onClick={() => onOpenClient(client)} className="font-bold text-indigo-700 hover:underline dark:text-indigo-300">
                        {client.company_name}
                      </button>
                    </td>
                    <td className="px-4 py-3 font-mono" style={{ direction: 'ltr', textAlign: 'left' }}>{formatNumber(client.revenue)}</td>
                    <td className="px-4 py-3 font-mono" style={{ direction: 'ltr', textAlign: 'left' }}>{formatNumber(client.expenses)}</td>
                    <td className={`px-4 py-3 font-mono font-bold ${Number(client.profit) >= 0 ? 'text-emerald-700' : 'text-red-700'}`} style={{ direction: 'ltr', textAlign: 'left' }}>
                      {formatNumber(client.profit)}
                    </td>
                    <td className="px-4 py-3 font-mono" style={{ direction: 'ltr', textAlign: 'left' }}>{formatNumber(client.vat_due)}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-lg px-2 py-1 text-xs font-bold ${dueTone(client)}`}>
                        {client.filing_due_date}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button type="button" onClick={() => onOpenClient(client)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-bold dark:border-slate-700">
                        فتح
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </OfficeCard>

      <div className="grid gap-4 sm:grid-cols-3">
        <p className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
          <Users className="h-4 w-4 text-indigo-600" />كل شركة وافقت على طلبك تظهر هنا تلقائياً.
        </p>
        <p className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
          <Receipt className="h-4 w-4 text-indigo-600" />الضريبة المستحقة = ضريبة المبيعات − ضريبة المشتريات.
        </p>
        <p className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
          <CalendarClock className="h-4 w-4 text-indigo-600" />موعد التقديم يُحسب من نهاية الشهر + مهلة الشركة.
        </p>
      </div>

      <p className="flex items-center justify-center gap-2 text-xs text-slate-500">
        <TrendingUp className="h-4 w-4" />الأرقام من القيود المرحّلة والفواتير الفعلية — لا تقديرات.
      </p>
    </div>
  );
};

export default OfficeDashboardPage;
