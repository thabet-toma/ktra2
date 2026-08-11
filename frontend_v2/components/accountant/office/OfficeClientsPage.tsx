import React, { useCallback, useEffect, useState } from 'react';
import { Building2, Search, UserPlus } from 'lucide-react';

import {
  acceptAccountantInvitation,
  listWorkspaceCompanies,
  lookupCompanyForEngagement,
  requestAccountantEngagement,
} from '../../../services/accountantApi';
import type { WorkspaceCompany } from '../../../types/accountant';
import { ENGAGEMENT_STATUS_LABELS, ENGAGEMENT_STATUS_TONES, engagementErrorCode } from '../../../utils/engagement';
import { formatNumber } from '../../../utils/formatNumber';
import { OfficeCard, OfficeEmpty, OfficeError, OfficeSkeleton } from './OfficeUi';

/**
 * «زبائني» — كل شركة تجارية وافقت على الارتباط هي ملفٌ عند المكتب.
 * لا شيء هنا يُنشئ مستنداً للزبون: الفتح قراءةٌ وتحليل فقط.
 */
export const OfficeClientsPage: React.FC<{ onOpenClient: (client: WorkspaceCompany) => void }> = ({ onOpenClient }) => {
  const [clients, setClients] = useState<WorkspaceCompany[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<{ tenant_id: number; company_name: string; engagement_status: string } | null>(null);
  const [lookupError, setLookupError] = useState('');
  const [note, setNote] = useState('');
  const [inviteToken, setInviteToken] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    listWorkspaceCompanies({ search, pageSize: 100 })
      .then((res) => setClients(res.results))
      .catch(() => setError('تعذّر تحميل قائمة الزبائن.'))
      .finally(() => setLoading(false));
  }, [search]);

  useEffect(() => {
    const timer = window.setTimeout(load, 250);
    return () => window.clearTimeout(timer);
  }, [load]);

  const lookup = async (event: React.FormEvent) => {
    event.preventDefault();
    setLookupError('');
    setFound(null);
    try {
      const result = await lookupCompanyForEngagement(query.trim());
      setFound(result.company);
    } catch (caught) {
      setLookupError(
        engagementErrorCode(caught) === 'query_too_short'
          ? 'اكتب اسم الشركة كما هو مسجَّل (3 أحرف على الأقل).'
          : 'لا توجد شركة بهذا الاسم مفعَّلة لبوابة المحاسب.',
      );
    }
  };

  const request = async () => {
    if (!found) return;
    try {
      await requestAccountantEngagement(found.tenant_id, note);
      setMessage(`أُرسل الطلب إلى ${found.company_name}. لن تُفتح ملفاته قبل موافقة مديره.`);
      setFound(null);
      setQuery('');
      setNote('');
      load();
    } catch (caught) {
      setLookupError((caught as { data?: { detail?: string } }).data?.detail || 'تعذّر إرسال الطلب.');
    }
  };

  const accept = async () => {
    try {
      await acceptAccountantInvitation(inviteToken.trim());
      setInviteToken('');
      setMessage('قُبلت الدعوة وصار الملف متاحاً.');
      load();
    } catch (caught) {
      setLookupError((caught as { data?: { detail?: string } }).data?.detail || 'تعذّر قبول الدعوة.');
    }
  };

  const active = clients.filter((client) => client.accessible);
  const pending = clients.filter((client) => !client.accessible);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-3">
        <OfficeCard title="طلب ملف شركة جديدة" className="lg:col-span-2">
          <form onSubmit={lookup} className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <input
                value={query}
                onChange={(event) => { setQuery(event.target.value); setFound(null); setLookupError(''); }}
                placeholder="اسم الشركة كما هو مسجَّل"
                aria-label="اسم الشركة"
                className="min-w-[16rem] flex-1 rounded-xl border border-slate-300 px-4 py-3 dark:border-slate-700 dark:bg-slate-950"
              />
              <button type="submit" className="rounded-xl border border-indigo-600 px-5 py-3 font-bold text-indigo-700 dark:text-indigo-300">
                بحث
              </button>
            </div>
            {lookupError && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm font-bold text-red-700">{lookupError}</p>}
            {message && <p className="rounded-xl bg-emerald-50 p-3 text-sm font-bold text-emerald-800">{message}</p>}
            {found && (
              <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 dark:border-indigo-900 dark:bg-indigo-950">
                <p className="font-black text-indigo-900 dark:text-indigo-100">{found.company_name}</p>
                <p className="mt-1 text-sm text-indigo-800 dark:text-indigo-200">
                  {found.engagement_status
                    ? `يوجد ارتباط سابق (${ENGAGEMENT_STATUS_LABELS[found.engagement_status as keyof typeof ENGAGEMENT_STATUS_LABELS] || found.engagement_status}).`
                    : 'الوصول لا يبدأ إلا بموافقة مدير الشركة على طلبك.'}
                </p>
                <input
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="رسالة لمدير الشركة (اختيارية)"
                  aria-label="رسالة الطلب"
                  className="mt-3 w-full rounded-xl border border-indigo-300 px-4 py-2 dark:border-indigo-800 dark:bg-slate-950"
                />
                <button
                  type="button"
                  disabled={Boolean(found.engagement_status)}
                  onClick={() => void request()}
                  className="mt-3 rounded-xl bg-indigo-700 px-5 py-2.5 font-bold text-white disabled:opacity-50"
                >
                  إرسال طلب استلام الملف
                </button>
              </div>
            )}
          </form>
        </OfficeCard>

        <OfficeCard title="دعوة من شركة">
          <p className="mb-3 text-sm text-slate-500 dark:text-slate-400">إن دعتك شركة، ألصق رمز الدعوة هنا.</p>
          <input
            value={inviteToken}
            onChange={(event) => setInviteToken(event.target.value)}
            placeholder="رمز الدعوة"
            aria-label="رمز الدعوة"
            className="w-full rounded-xl border border-slate-300 px-4 py-3 dark:border-slate-700 dark:bg-slate-950"
          />
          <button
            type="button"
            disabled={!inviteToken.trim()}
            onClick={() => void accept()}
            className="mt-3 w-full rounded-xl bg-emerald-600 px-5 py-3 font-bold text-white disabled:opacity-50"
          >
            قبول الدعوة
          </button>
        </OfficeCard>
      </div>

      <OfficeCard
        title={`ملفات الزبائن (${formatNumber(clients.length)})`}
        actions={(
          <label className="relative">
            <Search className="absolute right-3 top-3 h-4 w-4 text-slate-400" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="ابحث باسم الزبون"
              aria-label="بحث في الزبائن"
              className="w-64 rounded-xl border border-slate-300 py-2 pr-9 pl-3 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </label>
        )}
      >
        {loading ? <OfficeSkeleton rows={4} /> : error ? <OfficeError message={error} onRetry={load} /> : clients.length === 0 ? (
          <OfficeEmpty title="لا زبائن بعد" hint="ابحث عن شركة أعلاه وأرسل لها طلب استلام ملفها." />
        ) : (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {active.map((client) => (
                <button
                  key={client.engagement_id}
                  type="button"
                  onClick={() => onOpenClient(client)}
                  className="rounded-2xl border border-slate-200 p-5 text-right transition hover:border-indigo-500 hover:shadow-md dark:border-slate-800"
                >
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-black text-slate-900 dark:text-white">{client.company_name}</h3>
                    <Building2 className="h-5 w-5 text-indigo-600" />
                  </div>
                  <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
                    {client.last_period
                      ? `آخر فترة: ${client.last_period.period_from} → ${client.last_period.period_to}`
                      : 'لم تُراجَع أي فترة بعد'}
                  </p>
                  <p className="mt-2 text-sm font-bold text-indigo-700 dark:text-indigo-300">افتح الملف ←</p>
                </button>
              ))}
            </div>

            {pending.length > 0 && (
              <div>
                <h3 className="mb-3 text-sm font-black text-slate-500">طلبات ودعوات لم تُفتح بعد</h3>
                <ul className="space-y-2">
                  {pending.map((client) => (
                    <li
                      key={client.engagement_id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-800/60"
                    >
                      <span className="font-bold text-slate-700 dark:text-slate-200">{client.company_name}</span>
                      <span className={`rounded-lg px-2 py-1 text-xs font-bold ${ENGAGEMENT_STATUS_TONES[client.status]}`}>
                        {ENGAGEMENT_STATUS_LABELS[client.status]}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </OfficeCard>

      <p className="flex items-center justify-center gap-2 text-xs text-slate-500">
        <UserPlus className="h-4 w-4" />
        المكتب يقرأ ويحلّل ويجهّز الإقرار — ولا يُنشئ للزبون فاتورة ولا يعدّلها.
      </p>
    </div>
  );
};

export default OfficeClientsPage;
