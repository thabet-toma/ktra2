import React, { useCallback, useEffect, useState } from 'react';
import { ArchiveRestore, ArrowRight, BookOpenCheck, Building2, Link2, Pencil, Trash2 } from 'lucide-react';

import { listWorkspaceCompanies } from '../../../services/accountantApi';
import {
  archivePracticeClient,
  getPracticeClient,
  getPracticeSettings,
  linkPracticeClient,
  restorePracticeClient,
  type PracticeClientRecord,
  type PracticeSettingsRecord,
} from '../../../services/accountantPracticeApi';
import { useCompany } from '../../../contexts/CompanyContext';
import { useConfirm } from '../../../contexts/ConfirmContext';
import { useToast } from '../../../contexts/ToastContext';
import type { WorkspaceCompany } from '../../../types/accountant';
import { resolveClientBookTenantId } from '../../../utils/clientBookAccess';
import { DEFAULT_CLIENT_BOOK_TEMPLATE, companyTemplateByKey } from '../../../utils/companyTemplates';
import { formatDateValue } from '../../../utils/formatDate';
import { platformHint } from '../../../utils/officeClients';
import { OfficeClientForm } from './OfficeClientForm';
import { OfficeClientLinkForm } from './OfficeClientLinkForm';
import { OfficeClientTaxPeriods } from './OfficeClientTaxPeriods';
import { DocumentsPanel, ProgramsPanel, TasksPanel } from './OfficeClientWork';
import { OfficeBadge, OfficeCard, OfficeError, OfficeSkeleton } from './OfficeUi';

type Tab = 'data' | 'tax' | 'programs' | 'documents' | 'tasks';

const TABS: { key: Tab; label: string }[] = [
  { key: 'data', label: 'بيانات' },
  { key: 'tax', label: 'الفترات الضريبية' },
  { key: 'programs', label: 'برامج المراجعة' },
  { key: 'documents', label: 'مستندات' },
  { key: 'tasks', label: 'مهام/مواعيد' },
];

const DETAILS: { key: keyof PracticeClientRecord; label: string }[] = [
  { key: 'contact_first', label: 'الاسم الأول' },
  { key: 'contact_last', label: 'الاسم الأخير' },
  { key: 'phone', label: 'الهاتف' },
  { key: 'mobile', label: 'الجوال' },
  { key: 'email', label: 'البريد الإلكتروني' },
  { key: 'sector', label: 'القطاع' },
  { key: 'tax_number', label: 'الرقم الضريبي' },
  { key: 'address', label: 'العنوان' },
];

/**
 * ملف الزبون الخارجي — سجلّ المكتب عن زبونٍ لا دفاتر له عندنا: بياناته، برامج
 * مراجعته، مستنداته، ومواعيده. **ليس دفتر حسابات**: لا قيد ولا رصيد ولا فاتورة
 * هنا — لكنّ منه بابين إلى دفترٍ حقيقي، ولا ثالث لهما:
 *
 * - **الربط بشركةٍ قائمة على المنصة بإذنها** (`AccountantEngagement`) — الزبون
 *   يملك دفاتره وأنت تقرؤها.
 * - **فتح دفترٍ مُدار باسمه** (ISSUE #65) — مكتبك يملكه ويشغّله، وتدخل إليه
 *   لتُدخل فواتيره بنفسك. يمرّ بنقطة `managed-books` وحدها (الحصّة و`managed_by`).
 *
 * والاثنان مستقلان: النوع مشتقٌّ منهما معاً (`client_type`) لا حقل حالة ثالث.
 */
export const OfficeExternalClientPage: React.FC<{
  clientId: number;
  onBack: () => void;
  onOpenPlatformFile: (client: { tenant_id: number; company_name: string }) => void;
}> = ({ clientId, onBack, onOpenPlatformFile }) => {
  const toast = useToast();
  const confirm = useConfirm();
  // ISSUE #65: قناة الدفاتر المُدارة — نفس النقطة التي تغذّي «دفاتر عملائي».
  const { managedBooks, officeTenantId, openManagedBook, createManagedBook } = useCompany();
  // القالب ثابت: هذا البابُ يفتح **دفتر عميل**. كان يفتح على `general`
  // (نظامٌ تجاريٌّ كامل) وهو نقيض الغرض، ويفرض الخادم القاعدة نفسها.
  const bookTemplate = DEFAULT_CLIENT_BOOK_TEMPLATE;
  const [openingBook, setOpeningBook] = useState(false);
  const [tab, setTab] = useState<Tab>('data');
  const [client, setClient] = useState<PracticeClientRecord | null>(null);
  const [settings, setSettings] = useState<PracticeSettingsRecord | null>(null);
  // حالة الشركة المربوطة الحقيقية — الربط وحده لا يعني أن الدفاتر تُفتح: الارتباط
  // قد يكون معلّقاً، أو نشطاً على شركة لم تفعّل وحدة البوابة.
  const [companies, setCompanies] = useState<WorkspaceCompany[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);
  const [linking, setLinking] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([
      getPracticeClient(clientId),
      getPracticeSettings(),
      listWorkspaceCompanies({ pageSize: 200 }).catch(() => ({ results: [] as WorkspaceCompany[] })),
    ])
      .then(([clientRes, settingsRes, companiesRes]) => {
        setClient(clientRes.client);
        setSettings(settingsRes.settings);
        setCompanies(companiesRes.results);
      })
      .catch((caught) => setError((caught as Error).message || 'تعذّر فتح ملف الزبون.'))
      .finally(() => setLoading(false));
  }, [clientId]);

  useEffect(load, [load]);

  const archive = async () => {
    if (!client) return;
    const ok = await confirm({
      title: 'أرشفة الزبون',
      message: `سيُنقل «${client.trade_name}» إلى المؤرشفين. برامجه ومستنداته تبقى كما هي، ويمكن استرجاعه في أي وقت.`,
      confirmText: 'أرشف',
    });
    if (!ok) return;
    try {
      await archivePracticeClient(client.id);
      toast('أُرشف الزبون. تجده في «المؤرشفون» بقائمة الزبائن.', 'success');
      load();
    } catch (caught) {
      toast((caught as Error).message || 'تعذّر أرشفة الزبون.', 'error');
    }
  };

  const restore = async () => {
    if (!client) return;
    try {
      const response = await restorePracticeClient(client.id);
      setClient(response.client);
      toast('عاد الزبون إلى القائمة النشطة.', 'success');
    } catch (caught) {
      toast((caught as Error).message || 'تعذّر استرجاع الزبون.', 'error');
    }
  };

  if (loading) return <OfficeSkeleton rows={6} />;
  if (error) return <OfficeError message={error} onRetry={load} />;
  if (!client) return null;

  const archived = client.status === 'archived';
  const linkedCompany = client.engagement_id === null
    ? undefined
    : companies.find((company) => company.engagement_id === client.engagement_id);
  const bookTenantId = resolveClientBookTenantId({
    managedTenantId: client.managed_tenant_id,
    linkedTenantId: client.tenant_id,
    linkedAccessible: linkedCompany?.accessible ?? false,
  });
  const visibleTabs = TABS.filter((item) => item.key !== 'tax' || bookTenantId !== null);
  const managedBook = client.managed_tenant_id === null
    ? undefined
    : managedBooks.find((book) => book.TenantID === client.managed_tenant_id);

  /**
   * ISSUE #65 — «افتح دفتراً لهذا الزبون»: خطوتان لا واحدة. الدفتر يُنشأ من نقطة
   * المكتب (فتُفحص الحصّة ويُضبط `managed_by`)، ثم يُربط بملف الزبون فيصير نوعه
   * «مُدار» — والنوع مشتقٌّ لا مخزَّن، فالربط وحده يكفي.
   */
  const openBookForClient = async () => {
    setOpeningBook(true);
    try {
      const book = await createManagedBook(client.trade_name, bookTemplate);
      try {
        const linked = await linkPracticeClient(client.id, { managed_tenant_id: book.TenantID });
        setClient(linked.client);
        toast(`فُتح دفتر «${book.CompanyName}» وربط بهذا الزبون.`, 'success');
      } catch (linkError) {
        // الدفتر أُنشئ فعلاً — قول ذلك صراحةً كي لا يعيد المستخدم المحاولة
        // فيستهلك حصّةً ثانية على دفترٍ مكرّر.
        toast(
          `فُتح دفتر «${book.CompanyName}» لكن تعذّر ربطه بملف الزبون: `
          + `${(linkError as Error).message || 'خطأ غير معروف'}. تجده في «دفاتر عملائي».`,
          'error',
        );
      }
    } catch (caught) {
      toast((caught as Error).message || 'تعذّر فتح الدفتر.', 'error');
    } finally {
      setOpeningBook(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <button type="button" onClick={onBack} className="rounded-xl border border-slate-300 p-2 dark:border-slate-700" aria-label="عودة للزبائن">
            <ArrowRight className="h-5 w-5" />
          </button>
          <div>
            <h1 className="flex flex-wrap items-center gap-2 text-2xl font-black text-slate-900 dark:text-white">
              {client.trade_name}
              {archived && <OfficeBadge tone="bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200">مؤرشف</OfficeBadge>}
              {client.legacy && <OfficeBadge tone="bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200">لم يُنقل بعد</OfficeBadge>}
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              ملف مكتب — سجلّ الزبون وبرامجه ومواعيده · فُتح في {formatDateValue(client.created_at)}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => setEditing(true)} className="flex items-center gap-2 rounded-xl border border-slate-300 px-4 py-2 font-bold dark:border-slate-700">
            <Pencil className="h-4 w-4" />تعديل البيانات
          </button>
          {archived ? (
            <button type="button" onClick={() => void restore()} className="flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 font-bold text-white">
              <ArchiveRestore className="h-4 w-4" />استرجاع
            </button>
          ) : (
            <button type="button" onClick={() => void archive()} className="flex items-center gap-2 rounded-xl border border-red-300 px-4 py-2 font-bold text-red-700">
              <Trash2 className="h-4 w-4" />أرشفة
            </button>
          )}
        </div>
      </div>

      {archived && (
        <p className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-bold text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">
          هذا الملف مؤرشف — يُقرأ ويُسترجع، ولا يظهر في الأجندة. اضغط «استرجاع» لإعادته للعمل.
        </p>
      )}

      {client.legacy && (
        <p className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-bold text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">
          هذا زبونٌ قديمٌ من سجلّ المكتب لم يُنقل بعد إلى الطرف الحديث — يُقرأ فقط،
          والتعديل والأرشفة سيُرفضان حتى يُرحَّل. لا فقد للبيانات — راجع مكتب الدعم.
        </p>
      )}

      <nav className="flex flex-wrap gap-2" aria-label="أقسام ملف الزبون">
        {visibleTabs.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            aria-current={tab === item.key}
            className={`rounded-xl px-4 py-2 font-bold transition ${
              tab === item.key
                ? 'bg-indigo-700 text-white'
                : 'border border-slate-300 text-slate-700 hover:border-indigo-400 dark:border-slate-700 dark:text-slate-200'
            }`}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {tab === 'data' && (
        <div className="space-y-5">
          <OfficeCard title="بيانات الزبون">
            <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {DETAILS.map((field) => (
                <div key={String(field.key)}>
                  <dt className="text-xs font-bold text-slate-500 dark:text-slate-400">{field.label}</dt>
                  <dd className="mt-1 font-bold text-slate-900 dark:text-white">
                    {String(client[field.key] || '') || '—'}
                  </dd>
                </div>
              ))}
            </dl>
            {client.notes && (
              <div className="mt-5 rounded-xl bg-slate-50 p-4 dark:bg-slate-800/60">
                <p className="text-xs font-bold text-slate-500 dark:text-slate-400">ملاحظات</p>
                <p className="mt-1 whitespace-pre-line text-sm text-slate-700 dark:text-slate-200">{client.notes}</p>
              </div>
            )}
          </OfficeCard>

          <OfficeCard title="دفتر هذا الزبون عندك">
            {client.managed_tenant_id !== null ? (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="flex items-center gap-2 font-bold text-slate-700 dark:text-slate-200">
                  <BookOpenCheck className="h-4 w-4 text-emerald-600" />
                  دفترٌ مفتوحٌ لهذا الزبون تمسك حساباته فيه
                  {managedBook ? ` — «${managedBook.CompanyName}»` : ''}.
                </p>
                <button
                  type="button"
                  onClick={() => openManagedBook(client.managed_tenant_id as number)}
                  className="rounded-xl bg-indigo-700 px-5 py-2.5 font-bold text-white"
                >
                  ادخل إلى دفتر الزبون ←
                </button>
              </div>
            ) : officeTenantId === null ? (
              <p className="text-sm text-slate-600 dark:text-slate-300">
                فتحُ دفترٍ لزبون يحتاج شركةً بقالب «مكتب محاسبة» تديرها — أنشئها أوّلاً ثم عُد.
              </p>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-slate-600 dark:text-slate-300">
                  افتح لهذا الزبون دفتراً مستقلاً باسمه تُدخل فيه فواتيره ومشترياته وتمسك
                  حساباته — دفترٌ لا يظهر في مبدّل شركاتك، وتعود منه إلى مكتبك بزرّ واحد.
                </p>
                <div className="flex flex-wrap items-end gap-3">
                  <div>
                    <span className="text-xs font-bold text-slate-500 dark:text-slate-400">قالب الدفتر</span>
                    <p
                      data-testid="external-client-book-template"
                      className="mt-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 font-bold text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                    >
                      {companyTemplateByKey(bookTemplate)?.name}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={openingBook}
                    onClick={() => void openBookForClient()}
                    className="flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 font-bold text-white disabled:opacity-60"
                  >
                    <BookOpenCheck className="h-4 w-4" />
                    {openingBook ? 'جارٍ فتح الدفتر…' : 'افتح دفتراً لهذا الزبون'}
                  </button>
                </div>
              </div>
            )}
          </OfficeCard>

          <OfficeCard title="الشركة على المنصة">
            {client.engagement_id && client.tenant_id ? (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="flex items-center gap-2 font-bold text-slate-700 dark:text-slate-200">
                  <Building2 className="h-4 w-4 text-indigo-600" />
                  {linkedCompany
                    ? `مربوط بـ«${linkedCompany.company_name}» — ${platformHint(linkedCompany)}`
                    : 'هذا الزبون مربوط بشركة على المنصة — دفاترها تُقرأ من ملف الشركة.'}
                </p>
                {/* الزرّ لا يُعرض إلا حين تكون الدفاتر مفتوحة فعلاً: زرٌّ يقود إلى
                    شاشة خطأ أسوأ من غيابه، والسبب مكتوب أعلاه بدلاً منه. */}
                {(!linkedCompany || linkedCompany.accessible) && (
                  <button
                    type="button"
                    onClick={() => onOpenPlatformFile({ tenant_id: client.tenant_id as number, company_name: client.trade_name })}
                    className="rounded-xl bg-indigo-700 px-5 py-2.5 font-bold text-white"
                  >
                    افتح دفاتر الشركة ←
                  </button>
                )}
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-slate-600 dark:text-slate-300">
                  زبون خارجي — سجلّه عندك بلا دفاتر على المنصة. اربطه بشركة ليصير ملفه كاملاً:
                  قوائم دخل وميزانية وإقرار ضريبة من قيوده هو.
                </p>
                <button type="button" onClick={() => setLinking(true)} className="flex items-center gap-2 rounded-xl bg-indigo-700 px-5 py-2.5 font-bold text-white">
                  <Link2 className="h-4 w-4" />اربطه بشركة على المنصة
                </button>
              </div>
            )}
          </OfficeCard>
        </div>
      )}

      {tab === 'tax' && bookTenantId !== null && (
        <OfficeClientTaxPeriods tenantId={bookTenantId} companyName={client.trade_name} />
      )}

      {tab === 'programs' && settings && (
        <ProgramsPanel
          clientId={client.id}
          serviceTypes={settings.service_types}
          defaultDueDays={settings.default_program_due_days}
        />
      )}

      {tab === 'documents' && <DocumentsPanel clientId={client.id} />}

      {tab === 'tasks' && <TasksPanel clientId={client.id} />}

      {editing && (
        <OfficeClientForm
          client={client}
          onClose={() => setEditing(false)}
          onSaved={(saved) => { setClient(saved); setEditing(false); }}
        />
      )}

      {linking && (
        <OfficeClientLinkForm
          client={client}
          onClose={() => setLinking(false)}
          onLinked={(linked) => { setClient(linked); setLinking(false); }}
        />
      )}
    </div>
  );
};

export default OfficeExternalClientPage;
