import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ArchiveRestore, Building2, FolderOpen, Search, UserPlus } from 'lucide-react';

import {
  acceptAccountantInvitation,
  listWorkspaceCompanies,
  lookupCompanyForEngagement,
  requestAccountantEngagement,
} from '../../../services/accountantApi';
import {
  listPracticeClients,
  restorePracticeClient,
  type PracticeClientRecord,
} from '../../../services/accountantPracticeApi';
import { useToast } from '../../../contexts/ToastContext';
import type { WorkspaceCompany } from '../../../types/accountant';
import { ENGAGEMENT_STATUS_LABELS, ENGAGEMENT_STATUS_TONES, engagementErrorCode } from '../../../utils/engagement';
import { formatNumber } from '../../../utils/formatNumber';
import {
  filterOfficeClients,
  mergeOfficeClients,
  OFFICE_CLIENT_BADGES,
  OFFICE_CLIENT_BADGE_TONES,
  type OfficeClientRow,
} from '../../../utils/officeClients';
import { OfficeClientForm } from './OfficeClientForm';
import { OfficeBadge, OfficeCard, OfficeEmpty, OfficeError, OfficeInput, OfficeSkeleton } from './OfficeUi';

/**
 * «زبائني» — قائمة المكتب الواحدة: كل زبون، سواء كانت دفاتره على المنصة أم لا.
 *
 * الدمج على الواجهة وحدها (`utils/officeClients`): الشركات تأتي من الارتباطات
 * وزبائن المكتب من سجلّ الممارسة، والجدار بينهما في الخادم لم يُمسّ. من هنا
 * يُضاف الزبون الخارجي يدوياً — وهو ما يجعل المكتب يخدم **كل** زبائنه لا
 * المسجَّلين عندنا فقط.
 */
/**
 * طلب استلام ملف شركة مسجَّلة — المسار القائم منذ البداية، ويبقى مستقلاً عن
 * إضافة الزبون الخارجي: محاسبٌ يريد شركةً بعينها لا يُجبَر على إنشاء ملف مكتب
 * أولاً.
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
  onOpenPracticeClient: (clientId: number) => void;
}> = ({ onOpenClient, onOpenPracticeClient }) => {
  const toast = useToast();
  const [companies, setCompanies] = useState<WorkspaceCompany[]>([]);
  const [practiceClients, setPracticeClients] = useState<PracticeClientRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [inviteToken, setInviteToken] = useState('');
  const [adding, setAdding] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([listWorkspaceCompanies({ pageSize: 200 }), listPracticeClients()])
      .then(([companiesRes, clientsRes]) => {
        setCompanies(companiesRes.results);
        setPracticeClients(clientsRes.results);
      })
      .catch(() => setError('تعذّر تحميل قائمة الزبائن.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const rows = useMemo(
    () => filterOfficeClients(mergeOfficeClients(companies, practiceClients), search),
    [companies, practiceClients, search],
  );

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

  const restore = async (row: OfficeClientRow) => {
    if (!row.practiceId) return;
    try {
      await restorePracticeClient(row.practiceId);
      toast('عاد الزبون إلى القائمة النشطة.', 'success');
      load();
    } catch (caught) {
      toast((caught as Error).message || 'تعذّر استرجاع الزبون.', 'error');
    }
  };

  const open = (row: OfficeClientRow) => {
    // ترتيب الأبواب: دفاتر الشركة أولاً حين تكون مفتوحة — هي الأغنى؛ وإلا فملف
    // المكتب. الارتباط المعلَّق لا يفتح شيئاً، ويقول لماذا.
    if (row.accessible && row.tenantId !== null) {
      onOpenClient({ tenant_id: row.tenantId, company_name: row.name });
      return;
    }
    if (row.practiceId) {
      onOpenPracticeClient(row.practiceId);
      return;
    }
    toast('هذا الارتباط لم تُوافق عليه الشركة بعد — لا يُفتح ملفها قبل موافقة مديرها.', 'info');
  };

  const groups: { key: OfficeClientRow['group']; title: string; hint?: string }[] = [
    { key: 'open', title: 'زبائن المكتب' },
    { key: 'pending', title: 'ملفات لم تُفتح بعد', hint: 'السبب مكتوب على كل بطاقة.' },
    { key: 'archived', title: 'المؤرشفون', hint: 'محفوظون كما هم — الاسترجاع بضغطة.' },
  ];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-3">
        <OfficeCard title="أضف زبوناً إلى مكتبك">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            زبونك زبونك سواء كانت دفاتره عندنا أم لا. أضفه هنا بملفٍ يحمل بياناته وبرامج
            مراجعته ومستنداته ومواعيده — ثم اربطه بشركة على المنصة متى أردت دفاتره كاملة.
          </p>
          <button type="button" onClick={() => setAdding(true)} className="mt-4 flex items-center gap-2 rounded-xl bg-indigo-700 px-5 py-3 font-bold text-white">
            <UserPlus className="h-5 w-5" />إضافة زبون
          </button>
        </OfficeCard>

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
        title={`زبائني (${formatNumber(rows.length)})`}
        actions={(
          <label className="relative">
            <Search className="absolute right-3 top-3 h-4 w-4 text-slate-400" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="ابحث بالاسم أو القطاع أو الرقم الضريبي"
              aria-label="بحث في الزبائن"
              className="w-72 rounded-xl border border-slate-300 py-2 pr-9 pl-3 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </label>
        )}
      >
        {loading ? <OfficeSkeleton rows={4} /> : error ? <OfficeError message={error} onRetry={load} /> : rows.length === 0 ? (
          <OfficeEmpty
            title={search ? 'لا زبون يطابق بحثك' : 'لا زبائن بعد'}
            hint={search ? 'جرّب اسماً آخر أو امسح البحث.' : 'ابدأ بـ«إضافة زبون» أعلاه — لا يلزمه حسابٌ على المنصة.'}
          />
        ) : (
          <div className="space-y-6">
            {groups.map((group) => {
              const groupRows = rows.filter((row) => row.group === group.key);
              if (groupRows.length === 0) return null;
              return (
                <section key={group.key}>
                  <h3 className="mb-3 text-sm font-black text-slate-500 dark:text-slate-400">
                    {group.title} ({formatNumber(groupRows.length)})
                    {group.hint && <span className="mr-2 font-normal">— {group.hint}</span>}
                  </h3>
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {groupRows.map((row) => (
                      <article key={row.key} className="flex flex-col rounded-2xl border border-slate-200 p-5 dark:border-slate-800">
                        <div className="flex items-start justify-between gap-2">
                          <h4 className="font-black text-slate-900 dark:text-white">{row.name}</h4>
                          <OfficeBadge tone={OFFICE_CLIENT_BADGE_TONES[row.kind]}>
                            {OFFICE_CLIENT_BADGES[row.kind]}
                          </OfficeBadge>
                        </div>
                        <p className="mt-2 flex-1 text-sm text-slate-500 dark:text-slate-400">{row.hint}</p>
                        {row.engagementStatus && !row.accessible && (
                          <p className="mt-2">
                            <OfficeBadge tone={ENGAGEMENT_STATUS_TONES[row.engagementStatus]}>
                              {ENGAGEMENT_STATUS_LABELS[row.engagementStatus]}
                            </OfficeBadge>
                          </p>
                        )}
                        <div className="mt-4 flex flex-wrap gap-2">
                          {row.group === 'archived' ? (
                            <button type="button" onClick={() => void restore(row)} className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white">
                              <ArchiveRestore className="h-3.5 w-3.5" />استرجاع
                            </button>
                          ) : (
                            <button type="button" onClick={() => open(row)} className="flex items-center gap-1.5 rounded-lg bg-indigo-700 px-3 py-1.5 text-xs font-bold text-white">
                              {row.accessible && row.tenantId !== null
                                ? <><Building2 className="h-3.5 w-3.5" />افتح دفاتر الشركة</>
                                : <><FolderOpen className="h-3.5 w-3.5" />افتح ملف المكتب</>}
                            </button>
                          )}
                          {/* الزبون المربوط له بابان: دفاتر الشركة، وملفه في المكتب. */}
                          {row.accessible && row.practiceId !== null && row.group !== 'archived' && (
                            <button type="button" onClick={() => onOpenPracticeClient(row.practiceId as number)} className="flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-bold dark:border-slate-700">
                              <FolderOpen className="h-3.5 w-3.5" />ملف المكتب
                            </button>
                          )}
                          {row.group === 'archived' && row.practiceId !== null && (
                            <button type="button" onClick={() => onOpenPracticeClient(row.practiceId as number)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-bold dark:border-slate-700">
                              اطّلع على الملف
                            </button>
                          )}
                        </div>
                      </article>
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </OfficeCard>

      <p className="text-center text-xs text-slate-500">
        دفاتر الشركات تُقرأ ولا تُكتب من هنا — أما ملفات المكتب (البرامج والمستندات والمواعيد)
        فهي بيانات مكتبك أنت.
      </p>

      {adding && (
        <OfficeClientForm
          onClose={() => setAdding(false)}
          onSaved={(client) => { setAdding(false); load(); onOpenPracticeClient(client.id); }}
        />
      )}
    </div>
  );
};

export default OfficeClientsPage;
