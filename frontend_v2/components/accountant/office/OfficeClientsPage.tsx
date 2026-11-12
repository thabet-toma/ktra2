import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Building2, FolderOpen, Search } from 'lucide-react';

import {
  acceptAccountantInvitation,
  listWorkspaceCompanies,
  lookupCompanyForEngagement,
  requestAccountantEngagement,
} from '../../../services/accountantApi';
import { useToast } from '../../../contexts/ToastContext';
import type { WorkspaceCompany } from '../../../types/accountant';
import { ENGAGEMENT_STATUS_LABELS, ENGAGEMENT_STATUS_TONES, engagementErrorCode } from '../../../utils/engagement';
import { formatNumber } from '../../../utils/formatNumber';
import { platformHint, visibleWorkspaceCompanies } from '../../../utils/officeClients';
import { OfficeBadge, OfficeCard, OfficeEmpty, OfficeError, OfficeInput, OfficeSkeleton } from './OfficeUi';

/**
 * «شركاتي المرتبطة» — شركاتُ المنصّة التي ربطها المحاسب بشركائه (بوابة المحاسب).
 *
 * مصدرٌ واحد لا مصدران: `listWorkspaceCompanies` ما عاد يُدمَج بسجلّ ممارسةٍ
 * محلي، فالقائمة تعرض ما يعرفه الخادم وحده. ومن هنا يفتح المحاسب ملفّ الزبون
 * المالي (`OfficeClientFilePage`) — قراءةً وتحليلاً لا كتابة.
 */
/**
 * طلب استلام ملف شركة مسجَّلة — البابُ الذي يصير به للمحاسب ارتباطٌ جديد حين
 * لا تدعوه شركةٌ بعد.
 */
const RequestCompanyCard: React.FC<{ onRequested: () => void }> = ({ onRequested }) => {
  const toast = useToast();
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<{ tenant_id: number; company_name: string; engagement_status: string } | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');

  const lookup = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setFound(null);
    try {
      const result = await lookupCompanyForEngagement(query.trim());
      setFound(result.company);
    } catch (caught) {
      setError(
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
      toast(`أُرسل الطلب إلى ${found.company_name}. لن تُفتح ملفاته قبل موافقة مديره.`, 'success');
      setFound(null);
      setQuery('');
      setNote('');
      onRequested();
    } catch (caught) {
      setError((caught as Error).message || 'تعذّر إرسال الطلب.');
    }
  };

  return (
    <OfficeCard title="طلب ملف شركة على المنصة">
      <form onSubmit={lookup} className="space-y-3">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          للشركات المسجَّلة عندنا — ابحث باسمها المسجَّل تماماً.
        </p>
        <div className="flex flex-wrap gap-2">
          <OfficeInput
            value={query}
            onChange={(event) => { setQuery(event.target.value); setFound(null); setError(''); }}
            placeholder="اسم الشركة كما هو مسجَّل"
            aria-label="اسم الشركة"
            className="min-w-[12rem] flex-1"
          />
          <button type="submit" className="rounded-xl border border-indigo-600 px-5 py-2.5 font-bold text-indigo-700 dark:text-indigo-300">
            بحث
          </button>
        </div>
        {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm font-bold text-red-700">{error}</p>}
        {found && (
          <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 dark:border-indigo-900 dark:bg-indigo-950">
            <p className="font-black text-indigo-900 dark:text-indigo-100">{found.company_name}</p>
            <p className="mt-1 text-sm text-indigo-800 dark:text-indigo-200">
              {found.engagement_status
                ? `يوجد ارتباط سابق (${ENGAGEMENT_STATUS_LABELS[found.engagement_status as keyof typeof ENGAGEMENT_STATUS_LABELS] || found.engagement_status}).`
                : 'الوصول لا يبدأ إلا بموافقة مدير الشركة على طلبك.'}
            </p>
            <OfficeInput
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="رسالة لمدير الشركة (اختيارية)"
              aria-label="رسالة الطلب"
              className="mt-3"
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
  );
};

export const OfficeClientsPage: React.FC<{
  onOpenClient: (client: { tenant_id: number; company_name: string }) => void;
}> = ({ onOpenClient }) => {
  const toast = useToast();
  const [companies, setCompanies] = useState<WorkspaceCompany[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [inviteToken, setInviteToken] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    listWorkspaceCompanies({ pageSize: 200 })
      .then((result) => setCompanies(result.results))
      .catch(() => setError('تعذّر تحميل شركاتك المرتبطة.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const rows = useMemo(() => visibleWorkspaceCompanies(companies, search), [companies, search]);

  const accept = async () => {
    try {
      await acceptAccountantInvitation(inviteToken.trim());
      setInviteToken('');
      toast('قُبلت الدعوة وصار الملف متاحاً.', 'success');
      load();
    } catch (caught) {
      toast((caught as Error).message || 'تعذّر قبول الدعوة.', 'error');
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-2">
        <RequestCompanyCard onRequested={load} />

        <OfficeCard title="دعوة من شركة">
          <p className="mb-3 text-sm text-slate-500 dark:text-slate-400">إن دعتك شركة، ألصق رمز الدعوة هنا.</p>
          <OfficeInput
            value={inviteToken}
            onChange={(event) => setInviteToken(event.target.value)}
            placeholder="رمز الدعوة"
            aria-label="رمز الدعوة"
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
        title={`شركاتي المرتبطة (${formatNumber(rows.length)})`}
        actions={(
          <label className="relative">
            <Search className="absolute right-3 top-3 h-4 w-4 text-slate-400" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="ابحث باسم الشركة"
              aria-label="بحث في الشركات"
              className="w-72 rounded-xl border border-slate-300 py-2 pr-9 pl-3 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </label>
        )}
      >
        {loading ? <OfficeSkeleton rows={4} /> : error ? <OfficeError message={error} onRetry={load} /> : rows.length === 0 ? (
          <OfficeEmpty
            title={search ? 'لا شركة تطابق بحثك' : 'لا شركات مرتبطة بعد'}
            hint={search ? 'جرّب اسماً آخر أو امسح البحث.' : 'ابدأ بطلبِ ملف شركةٍ أعلاه، أو برمز دعوةٍ من شركة.'}
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {rows.map((row) => (
              <article key={row.engagement_id} className="flex flex-col rounded-2xl border border-slate-200 p-5 dark:border-slate-800">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-black text-slate-900 dark:text-white">{row.company_name}</h3>
                  <OfficeBadge tone={row.accessible
                    ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200'
                    : ENGAGEMENT_STATUS_TONES[row.status]}>
                    {row.accessible ? 'مفتوحة' : ENGAGEMENT_STATUS_LABELS[row.status]}
                  </OfficeBadge>
                </div>
                <p className="mt-2 flex-1 text-sm text-slate-500 dark:text-slate-400">{platformHint(row)}</p>
                <div className="mt-4">
                  {row.accessible ? (
                    <button
                      type="button"
                      onClick={() => onOpenClient({ tenant_id: row.tenant_id, company_name: row.company_name })}
                      className="flex items-center gap-1.5 rounded-lg bg-indigo-700 px-3 py-1.5 text-xs font-bold text-white"
                    >
                      <Building2 className="h-3.5 w-3.5" />افتح ملف الزبون
                    </button>
                  ) : (
                    <p className="flex items-center gap-1.5 text-xs font-bold text-slate-500 dark:text-slate-400">
                      <FolderOpen className="h-3.5 w-3.5" />الملف لا يُفتح قبل الموافقة
                    </p>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </OfficeCard>

      <p className="text-center text-xs text-slate-500">
        دفاتر الشركات تُقرأ ولا تُكتب من هنا — قراءةٌ وتحليلٌ لحسابات زبائنك.
      </p>
    </div>
  );
};

export default OfficeClientsPage;
