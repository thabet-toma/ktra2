import React, { useCallback, useEffect, useState } from 'react';
import { Save, Send } from 'lucide-react';

import { useToast } from '../../contexts/ToastContext';
import { getAccountantProfile, submitAccountantProfile, updateAccountantProfile } from '../../services/accountantApi';
import type { AccountantProfile } from '../../types/accountant';
import { AccountantError, AccountantPage, AccountantSkeleton } from './AccountantUi';

const fieldClass = 'w-full rounded-xl border border-slate-300 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-950';

export const AccountantProfilePage: React.FC = () => {
  const toast = useToast();
  const [profile, setProfile] = useState<AccountantProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    getAccountantProfile()
      .then((result) => setProfile(result.profile))
      .catch((caught) => {
        const value = caught as { data?: { code?: string; detail?: string } };
        setError(value.data?.code === 'email_unverified' ? 'تحقق من بريدك الإلكتروني قبل فتح الملف المهني.' : value.data?.detail || 'تعذّر تحميل الملف.');
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const update = (field: keyof AccountantProfile, value: string) =>
    setProfile((current) => current ? { ...current, [field]: value } : current);

  const save = async () => {
    if (!profile) return;
    setSaving(true);
    try {
      const result = await updateAccountantProfile(profile);
      setProfile(result.profile);
      toast('تم حفظ الملف المهني.', 'success');
    } catch (caught) {
      toast((caught as { data?: { detail?: string } }).data?.detail || 'تعذّر حفظ الملف.', 'error');
    } finally {
      setSaving(false);
    }
  };

  const submit = async () => {
    try {
      await submitAccountantProfile();
      setProfile((current) => current ? { ...current, verification_status: 'pending_review' } : current);
      toast('أُرسل الملف للمراجعة.', 'success');
    } catch (caught) {
      toast((caught as { data?: { detail?: string } }).data?.detail || 'تعذّر إرسال الملف.', 'error');
    }
  };

  return (
    <AccountantPage title="الملف المهني" description="بيانات تمثيلك المهني وحالة تحقق المنصة.">
      {loading ? <AccountantSkeleton rows={6} /> : error ? <AccountantError message={error} onRetry={load} /> : profile ? (
        <div className="space-y-6 rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-900">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-50 p-4 dark:bg-slate-800">
            <div><p className="text-sm text-slate-500">حالة التحقق المهني</p><p className="font-black text-slate-900 dark:text-white">{profile.verification_status === 'pending_review' ? 'بانتظار مراجعة المنصة' : profile.verification_status === 'verified' ? 'موثّق' : profile.verification_status === 'barred' ? 'ممنوع' : profile.verification_status === 'rejected' ? 'مرفوض' : 'غير موثّق'}</p></div>
            {!profile.professional_type || !profile.tax_registration_number || !profile.business_address ? <span className="rounded-full bg-amber-100 px-3 py-1 text-sm font-bold text-amber-800">أكمل ملفك</span> : null}
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <label className="space-y-2"><span className="font-bold">الصفة المهنية</span><select className={fieldClass} value={profile.professional_type} onChange={(e) => update('professional_type', e.target.value)}><option value="accountant">محاسب</option><option value="licensed_auditor">مدقق حسابات مرخص</option><option value="lawyer">محامٍ</option><option value="finance_diploma">دبلوم مالية</option><option value="ex_tax_officer">موظف ضريبة سابق</option></select></label>
            <label className="space-y-2"><span className="font-bold">رقم التسجيل الضريبي</span><input className={fieldClass} value={profile.tax_registration_number} onChange={(e) => update('tax_registration_number', e.target.value)} /></label>
            <label className="space-y-2"><span className="font-bold">رقم الرخصة</span><input className={fieldClass} value={profile.license_number} onChange={(e) => update('license_number', e.target.value)} /></label>
            <label className="space-y-2"><span className="font-bold">جهة الترخيص</span><input className={fieldClass} value={profile.license_authority} onChange={(e) => update('license_authority', e.target.value)} /></label>
            <label className="space-y-2"><span className="font-bold">الهاتف</span><input className={fieldClass} value={profile.phone} onChange={(e) => update('phone', e.target.value)} /></label>
            <label className="space-y-2 sm:col-span-2"><span className="font-bold">عنوان العمل الدائم</span><textarea className={`${fieldClass} min-h-24`} value={profile.business_address} onChange={(e) => update('business_address', e.target.value)} /></label>
          </div>
          <div className="flex flex-wrap gap-3">
            <button type="button" disabled={saving} onClick={() => void save()} className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-3 font-bold text-white disabled:opacity-50"><Save className="h-5 w-5" />حفظ</button>
            <button type="button" disabled={profile.verification_status === 'pending_review'} onClick={() => void submit()} className="inline-flex items-center gap-2 rounded-xl border border-blue-600 px-5 py-3 font-bold text-blue-700 disabled:opacity-50"><Send className="h-5 w-5" />إرسال للمراجعة</button>
          </div>
        </div>
      ) : null}
    </AccountantPage>
  );
};

export default AccountantProfilePage;

