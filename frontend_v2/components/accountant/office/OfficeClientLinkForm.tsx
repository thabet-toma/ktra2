import React, { useCallback, useEffect, useState } from 'react';
import { Building2, Link2, Search } from 'lucide-react';

import {
  listWorkspaceCompanies,
  lookupCompanyForEngagement,
  requestAccountantEngagement,
} from '../../../services/accountantApi';
import {
  listPracticeClients,
  updatePracticeClient,
  type PracticeClientRecord,
} from '../../../services/accountantPracticeApi';
import { useToast } from '../../../contexts/ToastContext';
import { ENGAGEMENT_STATUS_LABELS, engagementErrorCode } from '../../../utils/engagement';
import type { WorkspaceCompany } from '../../../types/accountant';
import { OfficeField, OfficeInput, OfficeModal, OfficeSelect, OfficeSkeleton } from './OfficeUi';

/**
 * «اربطه بشركة على المنصة» — الطريق من زبونٍ خارجي إلى شركةٍ حقيقية بدفاترها.
 *
 * طريقان لا طريق واحد: الشركة التي ارتبط بها المكتب أصلاً تُربط فوراً باختيارها،
 * والشركة الجديدة تحتاج طلب ارتباط تُوافق عليه إدارتها — والربط يُخزَّن حينها
 * حتى قبل الموافقة، كي لا يضيع الطلب من ملف الزبون بانتظار جوابٍ قد يتأخّر.
 *
 * **الجدار لا يتغيّر**: الربط سطرٌ في سجل المكتب؛ فتح الدفاتر يبقى مشروطاً
 * بارتباطٍ نشط يفحصه الخادم في كل نداء.
 */
export const OfficeClientLinkForm: React.FC<{
  client: PracticeClientRecord;
  onClose: () => void;
  onLinked: (client: PracticeClientRecord) => void;
}> = ({ client, onClose, onLinked }) => {
  const toast = useToast();
  const [companies, setCompanies] = useState<WorkspaceCompany[]>([]);
  const [linkedIds, setLinkedIds] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [choice, setChoice] = useState('');
  const [query, setQuery] = useState(client.trade_name);
  const [found, setFound] = useState<{ tenant_id: number; company_name: string; engagement_status: string } | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([listWorkspaceCompanies({ pageSize: 200 }), listPracticeClients()])
      .then(([companiesRes, clientsRes]) => {
        setCompanies(companiesRes.results);
        setLinkedIds(new Set(
          clientsRes.results
            .filter((row) => row.engagement_id !== null && row.id !== client.id)
            .map((row) => row.engagement_id as number),
        ));
      })
      .catch(() => setError('تعذّر تحميل شركاتك على المنصة.'))
      .finally(() => setLoading(false));
  }, [client.id]);

  useEffect(load, [load]);

  const link = async (engagementId: number, successMessage: string) => {
    const response = await updatePracticeClient(client.id, { engagement_id: engagementId });
    toast(successMessage, 'success');
    onLinked(response.client);
  };

  const linkExisting = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!choice) return;
    setBusy(true);
    setError('');
    try {
      await link(Number(choice), 'رُبط الزبون بشركته على المنصة.');
    } catch (caught) {
      setError((caught as Error).message || 'تعذّر ربط الزبون بالشركة.');
    } finally {
      setBusy(false);
    }
  };

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

  const requestAndLink = async () => {
    if (!found) return;
    setBusy(true);
    setError('');
    try {
      const { engagement } = await requestAccountantEngagement(found.tenant_id, note);
      await link(engagement.id, `أُرسل الطلب إلى ${found.company_name}، ورُبط بملف الزبون. لن تُفتح دفاترها قبل موافقة مديرها.`);
    } catch (caught) {
      setError((caught as Error).message || 'تعذّر إرسال طلب الارتباط.');
    } finally {
      setBusy(false);
    }
  };

  const selectable = companies.filter((company) => !linkedIds.has(company.engagement_id));

  return (
    <OfficeModal title={`اربط ${client.trade_name} بشركة على المنصة`} onClose={onClose} wide>
      <div className="space-y-6">
        {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm font-bold text-red-700">{error}</p>}

        {loading ? <OfficeSkeleton rows={3} /> : (
          <>
            <section className="rounded-2xl border border-slate-200 p-4 dark:border-slate-800">
              <h3 className="flex items-center gap-2 font-black text-slate-900 dark:text-white">
                <Building2 className="h-4 w-4 text-indigo-600" />شركة مرتبطة بمكتبك أصلاً
              </h3>
              {selectable.length === 0 ? (
                <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                  لا شركة متاحة — كل ارتباطاتك مربوطة بزبائن آخرين، أو لا ارتباط لك بعد.
                </p>
              ) : (
                <form onSubmit={linkExisting} className="mt-3 flex flex-wrap items-end gap-3">
                  <OfficeField label="الشركة" className="min-w-[16rem] flex-1">
                    {(id) => (
                      <OfficeSelect id={id} value={choice} onChange={(event) => setChoice(event.target.value)}>
                        <option value="">— اختر —</option>
                        {selectable.map((company) => (
                          <option key={company.engagement_id} value={company.engagement_id}>
                            {company.company_name} ({ENGAGEMENT_STATUS_LABELS[company.status]})
                          </option>
                        ))}
                      </OfficeSelect>
                    )}
                  </OfficeField>
                  <button type="submit" disabled={!choice || busy} className="flex items-center gap-2 rounded-xl bg-indigo-700 px-5 py-2.5 font-bold text-white disabled:opacity-50">
                    <Link2 className="h-4 w-4" />اربط
                  </button>
                </form>
              )}
            </section>

            <section className="rounded-2xl border border-slate-200 p-4 dark:border-slate-800">
              <h3 className="flex items-center gap-2 font-black text-slate-900 dark:text-white">
                <Search className="h-4 w-4 text-indigo-600" />شركة جديدة على المنصة
              </h3>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                ابحث باسمها المسجَّل تماماً، وأرسل طلب استلام ملفها. الربط يُحفظ فوراً، والدفاتر
                تُفتح بعد موافقة مديرها.
              </p>
              <form onSubmit={lookup} className="mt-3 flex flex-wrap items-end gap-3">
                <OfficeField label="اسم الشركة" className="min-w-[16rem] flex-1">
                  {(id) => (
                    <OfficeInput
                      id={id}
                      value={query}
                      onChange={(event) => { setQuery(event.target.value); setFound(null); }}
                      placeholder="اسم الشركة كما هو مسجَّل"
                    />
                  )}
                </OfficeField>
                <button type="submit" className="rounded-xl border border-indigo-600 px-5 py-2.5 font-bold text-indigo-700 dark:text-indigo-300">
                  بحث
                </button>
              </form>

              {found && (
                <div className="mt-3 rounded-xl border border-indigo-200 bg-indigo-50 p-4 dark:border-indigo-900 dark:bg-indigo-950">
                  <p className="font-black text-indigo-900 dark:text-indigo-100">{found.company_name}</p>
                  <p className="mt-1 text-sm text-indigo-800 dark:text-indigo-200">
                    {found.engagement_status
                      ? `يوجد ارتباط سابق (${ENGAGEMENT_STATUS_LABELS[found.engagement_status as keyof typeof ENGAGEMENT_STATUS_LABELS] || found.engagement_status}) — اختره من القائمة أعلاه.`
                      : 'الوصول لا يبدأ إلا بموافقة مدير الشركة على طلبك.'}
                  </p>
                  {!found.engagement_status && (
                    <>
                      <OfficeInput
                        value={note}
                        onChange={(event) => setNote(event.target.value)}
                        placeholder="رسالة لمدير الشركة (اختيارية)"
                        aria-label="رسالة الطلب"
                        className="mt-3"
                      />
                      <button type="button" disabled={busy} onClick={() => void requestAndLink()} className="mt-3 rounded-xl bg-indigo-700 px-5 py-2.5 font-bold text-white disabled:opacity-50">
                        أرسل الطلب واربطه بالملف
                      </button>
                    </>
                  )}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </OfficeModal>
  );
};

export default OfficeClientLinkForm;
