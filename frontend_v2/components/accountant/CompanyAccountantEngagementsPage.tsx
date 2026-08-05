import React, { useCallback, useEffect, useState } from 'react';
import { ShieldCheck, UserPlus } from 'lucide-react';

import { useCompany } from '../../contexts/CompanyContext';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useToast } from '../../contexts/ToastContext';
import {
  companyEngagementAction,
  getCompanyAccountantScopeCatalog,
  inviteCompanyAccountant,
  listCompanyAccountantEngagements,
  updateCompanyAccountantScope,
} from '../../services/accountantApi';
import type { AccountantEngagement, AccountantPermissionEntry } from '../../types/accountant';
import { engagementErrorCode } from '../../utils/engagement';
import { AccountantError, AccountantPage, AccountantSkeleton } from './AccountantUi';
import { EngagementPermissionTable } from './EngagementPermissionTable';
import { EngagementStatusBadge } from './EngagementStatusBadge';

/**
 * التبويب **الوحيد** للشركة التجارية في هذه الوحدة، ويجيب ثلاثة أسئلة لا رابع لها:
 * مَن المحاسب القانوني الماسك ملفنا · ماذا طلب منّا · ما الصلاحيات التي منحناه.
 *
 * الشركة التجارية لا تصير مكتب محاسبة: لا شاشات مراجعة ولا فترات ضريبية هنا —
 * تلك واجهات المكتب في قشرته المستقلة. ما نمنحه هنا **صلاحية وصول فقط**.
 */
export const CompanyAccountantEngagementsPage: React.FC = () => {
  const { currentCompany } = useCompany();
  const tenantId = currentCompany?.TenantID;
  const toast = useToast();
  const confirm = useConfirm();
  const [items, setItems] = useState<AccountantEngagement[]>([]);
  const [catalog, setCatalog] = useState<AccountantPermissionEntry[]>([]);
  // الافتراضي المهني يأتي من الخادم: الموافقة وحدها تكفي ليعمل المحاسب.
  const [defaults, setDefaults] = useState<string[]>([]);
  const [profiles, setProfiles] = useState<Record<string, string[]>>({});
  const [selected, setSelected] = useState<AccountantEngagement | null>(null);
  const [scope, setScope] = useState<string[]>([]);
  const [email, setEmail] = useState('');
  const [note, setNote] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expired, setExpired] = useState(false);
  const [reauthPassword, setReauthPassword] = useState('');
  const [showInvite, setShowInvite] = useState(false);

  const load = useCallback(() => {
    if (!tenantId) return;
    setLoading(true);
    setError('');
    Promise.all([
      listCompanyAccountantEngagements(tenantId),
      getCompanyAccountantScopeCatalog(tenantId),
    ])
      .then(([engagements, permissions]) => {
        setItems(engagements.results);
        setCatalog(permissions.permissions);
        setDefaults(permissions.defaults || []);
        setProfiles(permissions.profiles || {});
      })
      .catch((caught) => setError((caught as { data?: { detail?: string } }).data?.detail || 'تعذّر تحميل بيانات المحاسب القانوني.'))
      .finally(() => setLoading(false));
  }, [tenantId]);

  useEffect(load, [load]);

  const labelFor = (key: string) => catalog.find((entry) => entry.key === key)?.label || key;

  const approve = async () => {
    if (!tenantId || !selected) return;
    try {
      await companyEngagementAction(tenantId, selected.id, 'approve', { scope });
      toast('وافقت على المحاسب بالنطاق المحدد.', 'success');
      setSelected(null);
      load();
    } catch (caught) {
      if (engagementErrorCode(caught) === 'invitation_expired') setExpired(true);
      else toast((caught as { data?: { detail?: string } }).data?.detail || 'تعذّرت الموافقة.', 'error');
    }
  };

  const saveScope = async () => {
    if (!tenantId || !selected) return;
    try {
      await updateCompanyAccountantScope(tenantId, selected.id, scope, reauthPassword);
      toast('حُدّثت صلاحيات المحاسب.', 'success');
      setSelected(null);
      setReauthPassword('');
      load();
    } catch (caught) {
      const code = engagementErrorCode(caught);
      toast(
        code === 'reauth_required'
          ? 'أعد إدخال كلمة مرورك لتأكيد تغيير الصلاحيات.'
          : (caught as { data?: { detail?: string } }).data?.detail || 'تعذّر تعديل الصلاحيات.',
        'error',
      );
    }
  };

  const invite = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!tenantId) return;
    try {
      await inviteCompanyAccountant(tenantId, { email, note, scope });
      setEmail('');
      setNote('');
      setShowInvite(false);
      toast('أُرسلت الدعوة للمحاسب.', 'success');
      load();
    } catch (caught) {
      toast((caught as { data?: { detail?: string } }).data?.detail || 'تعذّر إرسال الدعوة.', 'error');
    }
  };

  const act = async (item: AccountantEngagement, action: 'decline' | 'suspend' | 'resume' | 'revoke') => {
    if (!tenantId) return;
    const messages: Record<string, string> = {
      decline: 'سيُرفض طلب هذا المحاسب.',
      suspend: 'سيتوقف وصول المحاسب فوراً، ويمكنك استئنافه لاحقاً بنفس الصلاحيات.',
      revoke: 'سيسقط وصول المحاسب نهائياً، والعودة تحتاج طلباً وموافقة جديدين.',
    };
    if (action !== 'resume') {
      const ok = await confirm({
        title: 'تأكيد الإجراء',
        message: messages[action],
        confirmText: 'تأكيد',
        danger: true,
      });
      if (!ok) return;
    }
    try {
      await companyEngagementAction(tenantId, item.id, action, { reason: 'قرار مدير الشركة' });
      toast('تم تحديث حالة المحاسب.', 'success');
      load();
    } catch (caught) {
      toast((caught as { data?: { detail?: string } }).data?.detail || 'تعذّر تنفيذ الإجراء.', 'error');
    }
  };

  if (!tenantId) return <AccountantError message="اختر شركة أولاً." onRetry={() => {}} />;

  const holders = items.filter((item) => item.status === 'active' || item.status === 'suspended');
  const requests = items.filter((item) => item.status === 'pending');
  const history = items.filter((item) => !holders.includes(item) && !requests.includes(item));

  return (
    <AccountantPage
      title="واجهة المحاسب القانوني"
      description="مَن يمسك ملفنا، وماذا طلب منّا، وما الصلاحيات التي منحناه. الوصول صلاحية تُمنح وتُسحب — لا أكثر."
      actions={(
        <button
          type="button"
          onClick={() => { setShowInvite((value) => !value); setScope([]); }}
          className="flex items-center gap-2 rounded-xl border border-blue-600 px-4 py-2 font-bold text-blue-700"
        >
          <UserPlus className="h-4 w-4" />دعوة محاسب
        </button>
      )}
    >
      {expired && <div role="alert" className="rounded-2xl border border-red-300 bg-red-50 p-5 font-bold text-red-800">انتهت صلاحية الدعوة. أرسل دعوة جديدة.</div>}

      {showInvite && (
        <form onSubmit={invite} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
          <h2 className="font-black">دعوة محاسب قانوني بالبريد</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="بريد المحاسب المهني" aria-label="بريد المحاسب" className="rounded-xl border border-slate-300 px-4 py-3 dark:border-slate-700 dark:bg-slate-950" />
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="ملاحظة" aria-label="ملاحظة الدعوة" className="rounded-xl border border-slate-300 px-4 py-3 dark:border-slate-700 dark:bg-slate-950" />
          </div>
          <EngagementPermissionTable permissions={catalog} selected={scope} onChange={setScope} />
          <button className="rounded-xl bg-blue-600 px-5 py-3 font-bold text-white">إرسال الدعوة بهذا النطاق</button>
        </form>
      )}

      {loading ? <AccountantSkeleton rows={5} /> : error ? <AccountantError message={error} onRetry={load} /> : (
        <div className="space-y-6">
          <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
            <h2 className="mb-4 flex items-center gap-2 font-black"><ShieldCheck className="h-5 w-5 text-emerald-600" />المحاسب الماسك ملفنا</h2>
            {holders.length === 0 ? (
              <p className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-slate-500">لا محاسب قانوني يمسك ملف الشركة حالياً.</p>
            ) : holders.map((item) => (
              <article key={item.id} className="rounded-2xl border border-slate-200 p-5 dark:border-slate-700">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-lg font-black text-slate-900 dark:text-white">{item.accountant_name}</p>
                    <p className="text-sm text-slate-500">{item.accountant_email}</p>
                  </div>
                  <EngagementStatusBadge status={item.status} />
                </div>
                <div className="mt-4">
                  <p className="mb-2 text-sm font-bold text-slate-600 dark:text-slate-300">الصلاحيات الممنوحة له ({item.scope.length}):</p>
                  {item.scope.length === 0 ? (
                    <p className="text-sm text-slate-500">قراءة الملفات المالية الأساسية فقط (افتراضي الدور) بلا أي صلاحية إضافية.</p>
                  ) : (
                    <ul className="flex flex-wrap gap-2">
                      {item.scope.map((key) => (
                        <li key={key} className="rounded-lg bg-slate-100 px-3 py-1 text-xs font-bold text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                          {labelFor(key)}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="mt-5 flex flex-wrap gap-2">
                  {item.status === 'active' && (
                    <>
                      <button type="button" onClick={() => { setSelected(item); setScope(item.scope); setReauthPassword(''); }} className="rounded-lg border border-blue-300 px-4 py-2 font-bold text-blue-700">تعديل الصلاحيات</button>
                      <button type="button" onClick={() => void act(item, 'suspend')} className="rounded-lg border border-orange-300 px-4 py-2 font-bold text-orange-700">تعليق الوصول</button>
                    </>
                  )}
                  {item.status === 'suspended' && (
                    <button type="button" onClick={() => void act(item, 'resume')} className="rounded-lg bg-blue-600 px-4 py-2 font-bold text-white">استئناف الوصول</button>
                  )}
                  <button type="button" onClick={() => void act(item, 'revoke')} className="rounded-lg border border-red-300 px-4 py-2 font-bold text-red-700">إنهاء نهائي</button>
                </div>
              </article>
            ))}
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
            <h2 className="mb-4 font-black">طلبات واردة ({requests.length})</h2>
            {requests.length === 0 ? (
              <p className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-slate-500">لا طلبات تنتظر قرارك.</p>
            ) : (
              <ul className="space-y-3">
                {requests.map((item) => (
                  <li key={item.id} className="rounded-2xl border border-amber-200 bg-amber-50 p-5 dark:border-amber-900 dark:bg-amber-950">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="font-black text-slate-900 dark:text-white">{item.accountant_name}</p>
                        <p className="text-sm text-slate-600 dark:text-slate-300">{item.accountant_email}</p>
                        <p className="mt-2 text-sm text-slate-700 dark:text-slate-200">
                          {item.initiated_by === 'accountant' ? 'طلب استلام ملف الشركة' : 'دعوة أرسلناها له'}
                          {item.note ? ` — «${item.note}»` : ''}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <button type="button" onClick={() => { setSelected(item); setScope(item.scope.length ? item.scope : defaults); }} className="rounded-lg bg-emerald-600 px-4 py-2 font-bold text-white">مراجعة الصلاحيات والموافقة</button>
                        <button type="button" onClick={() => void act(item, 'decline')} className="rounded-lg border border-red-300 px-4 py-2 font-bold text-red-700">رفض</button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {history.length > 0 && (
            <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
              <h2 className="mb-3 font-black">سجل سابق</h2>
              <ul className="space-y-2">
                {history.map((item) => (
                  <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 px-4 py-3 dark:bg-slate-800">
                    <span className="font-bold">{item.accountant_name}</span>
                    <EngagementStatusBadge status={item.status} />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}

      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4">
          <div role="dialog" aria-modal="true" className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl dark:bg-slate-900">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-black">صلاحيات {selected.accountant_name}</h2>
                <p className="text-sm text-slate-500">أشّر ما تسمح له برؤيته أو فعله. غير المؤشَّر ممنوع خادمياً.</p>
              </div>
              <button type="button" onClick={() => setSelected(null)} className="rounded-lg px-3 py-2 text-slate-500">إغلاق</button>
            </div>
            <div className="mb-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 dark:border-emerald-900 dark:bg-emerald-950">
              <p className="text-sm font-bold text-emerald-900 dark:text-emerald-100">
                المؤشَّر أدناه هو <span className="underline">عمل المحاسب الدارج</span>: قراءة الفواتير والقيود
                والتقارير — يكفيه ليُخرج لك الميزانية وورقة الضريبة. لا مخزون ولا إعدادات ولا إدارة أعضاء بحال.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" onClick={() => setScope(defaults)} className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-bold text-white">الافتراضي (مراجعة)</button>
                {profiles.review_and_prepare && (
                  <button type="button" onClick={() => setScope(profiles.review_and_prepare)} className="rounded-lg border border-emerald-600 px-3 py-1.5 text-xs font-bold text-emerald-800 dark:text-emerald-200">مراجعة وتجهيز مسودات</button>
                )}
                {profiles.full_accounting && (
                  <button type="button" onClick={() => setScope(profiles.full_accounting)} className="rounded-lg border border-emerald-600 px-3 py-1.5 text-xs font-bold text-emerald-800 dark:text-emerald-200">محاسبة كاملة (يرحّل القيود)</button>
                )}
                <button type="button" onClick={() => setScope([])} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-bold text-slate-600 dark:border-slate-700">تفريغ الكل</button>
              </div>
            </div>
            <EngagementPermissionTable permissions={catalog} selected={scope} onChange={setScope} />
            {selected.status === 'pending' ? (
              <button type="button" onClick={() => void approve()} className="mt-5 w-full rounded-xl bg-emerald-600 px-5 py-3 font-black text-white">موافقة ومنح الوصول</button>
            ) : (
              <div className="mt-5 space-y-3">
                <label className="block text-sm font-bold" htmlFor="scope-reauth">أكّد هويتك بكلمة المرور</label>
                <input id="scope-reauth" type="password" autoComplete="current-password" value={reauthPassword} onChange={(e) => setReauthPassword(e.target.value)} className="w-full rounded-xl border border-slate-300 px-4 py-3 dark:border-slate-700 dark:bg-slate-950" />
                <button type="button" onClick={() => void saveScope()} className="w-full rounded-xl bg-blue-600 px-5 py-3 font-black text-white">حفظ الصلاحيات</button>
              </div>
            )}
          </div>
        </div>
      )}
    </AccountantPage>
  );
};

export default CompanyAccountantEngagementsPage;
