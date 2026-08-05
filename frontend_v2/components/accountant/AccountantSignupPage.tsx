import React, { useEffect, useState } from 'react';
import { CheckCircle2, Eye, EyeOff, ShieldCheck } from 'lucide-react';

import {
  resendAccountantVerification,
  signupAccountant,
  verifyAccountantEmail,
  type AccountantSignupInput,
} from '../../services/accountantApi';

const EMPTY: AccountantSignupInput = {
  fullName: '',
  email: '',
  password: '',
  professional_type: 'accountant',
  tax_registration_number: '',
  business_address: '',
  license_number: '',
  license_authority: '',
  phone: '',
};

const ERROR_LABELS: Record<string, string> = {
  weak_password: 'اختر كلمة مرور من 10 محارف على الأقل وغير شائعة.',
  invalid_email: 'أدخل بريداً إلكترونياً صالحاً.',
  missing_tax_registration: 'رقم التسجيل الضريبي مطلوب.',
  missing_business_address: 'عنوان العمل الدائم مطلوب.',
  throttled: 'تجاوزت عدد المحاولات المسموح. حاول لاحقاً.',
};

const fieldClass = 'w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100';

export const AccountantSignupPage: React.FC = () => {
  const [form, setForm] = useState(EMPTY);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  // المنصة قد لا تشترط تحقق البريد (قرار المالك) — الخادم هو من يقول ذلك.
  const [needsVerification, setNeedsVerification] = useState(true);
  const [error, setError] = useState('');
  const token = new URLSearchParams(window.location.search).get('token');
  const [verifyState, setVerifyState] = useState<'idle' | 'loading' | 'verified' | 'error'>('idle');

  useEffect(() => {
    if (!token) return;
    setVerifyState('loading');
    verifyAccountantEmail(token)
      .then(() => setVerifyState('verified'))
      .catch(() => setVerifyState('error'));
  }, [token]);

  const update = (key: keyof AccountantSignupInput, value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const result = await signupAccountant(form);
      setNeedsVerification(result.email_verification_required !== false);
      setSuccess(true);
    } catch (caught) {
      const value = caught as { data?: { code?: string; detail?: string }; message?: string };
      setError(ERROR_LABELS[value.data?.code || ''] || value.data?.detail || value.message || 'تعذّر إنشاء الحساب.');
    } finally {
      setLoading(false);
    }
  };

  if (token) {
    return (
      <main dir="rtl" className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12">
        <div className="w-full max-w-lg rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-xl">
          <ShieldCheck className="mx-auto h-14 w-14 text-blue-600" />
          <h1 className="mt-4 text-2xl font-black">التحقق من البريد</h1>
          {verifyState === 'loading' && <p className="mt-4 text-slate-600">جاري التحقق...</p>}
          {verifyState === 'verified' && <p className="mt-4 font-bold text-emerald-700">تم التحقق بنجاح. يمكنك تسجيل الدخول الآن.</p>}
          {verifyState === 'error' && <p role="alert" className="mt-4 font-bold text-red-700">الرابط غير صالح أو منتهي أو استُعمل سابقاً.</p>}
          <a href="/" className="mt-6 inline-flex rounded-xl bg-blue-600 px-6 py-3 font-bold text-white hover:bg-blue-700">العودة لتسجيل الدخول</a>
        </div>
      </main>
    );
  }

  if (success) {
    return (
      <main dir="rtl" className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12">
        <div className="w-full max-w-lg rounded-3xl border border-emerald-200 bg-white p-8 text-center shadow-xl">
          <CheckCircle2 className="mx-auto h-14 w-14 text-emerald-600" />
          {needsVerification ? (
            <>
              <h1 className="mt-4 text-2xl font-black">تحقق من بريدك</h1>
              <p className="mt-3 leading-7 text-slate-600">إن كان الطلب صالحاً أرسلنا رسالة تحقق. حفاظاً على الخصوصية تظهر الرسالة نفسها للحساب الموجود.</p>
              <button type="button" onClick={() => void resendAccountantVerification(form.email)} className="mt-6 rounded-xl border border-blue-600 px-5 py-3 font-bold text-blue-700 hover:bg-blue-50">إعادة إرسال الرسالة</button>
            </>
          ) : (
            <>
              <h1 className="mt-4 text-2xl font-black">تم إنشاء حسابك</h1>
              <p className="mt-3 leading-7 text-slate-600">سجّل الدخول ببريدك وكلمة مرورك، ثم أرسل طلب ارتباط للشركة التي تراجع حساباتها.</p>
              <a href="/" className="mt-6 inline-flex rounded-xl bg-blue-600 px-6 py-3 font-bold text-white hover:bg-blue-700">تسجيل الدخول</a>
            </>
          )}
        </div>
      </main>
    );
  }

  return (
    <main dir="rtl" className="min-h-screen bg-gradient-to-b from-blue-50 to-slate-50 px-4 py-10">
      <form onSubmit={submit} className="mx-auto w-full max-w-3xl rounded-3xl border border-slate-200 bg-white p-6 shadow-xl sm:p-10">
        <div className="mb-8 text-center">
          <ShieldCheck className="mx-auto h-12 w-12 text-blue-600" />
          <h1 className="mt-3 text-3xl font-black text-slate-900">إنشاء حساب محاسب قانوني</h1>
          <p className="mt-2 text-slate-600">أنشئ هويتك المهنية أولاً؛ لا يُمنح أي وصول لشركة قبل موافقتها.</p>
        </div>
        {error && <div role="alert" className="mb-5 rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">{error}</div>}
        <div className="grid gap-5 sm:grid-cols-2">
          <label className="space-y-2"><span className="font-bold">الاسم الكامل</span><input required value={form.fullName} onChange={(e) => update('fullName', e.target.value)} className={fieldClass} /></label>
          <label className="space-y-2"><span className="font-bold">البريد الإلكتروني</span><input required type="email" value={form.email} onChange={(e) => update('email', e.target.value)} className={fieldClass} /></label>
          <label className="space-y-2"><span className="font-bold">الصفة المهنية</span><select value={form.professional_type} onChange={(e) => update('professional_type', e.target.value)} className={fieldClass}><option value="accountant">محاسب</option><option value="licensed_auditor">مدقق حسابات مرخص</option><option value="lawyer">محامٍ</option><option value="finance_diploma">دبلوم مالية</option><option value="ex_tax_officer">موظف ضريبة سابق</option></select></label>
          <label className="space-y-2"><span className="font-bold">رقم التسجيل الضريبي</span><input required value={form.tax_registration_number} onChange={(e) => update('tax_registration_number', e.target.value)} className={fieldClass} /></label>
          <label className="space-y-2 sm:col-span-2"><span className="font-bold">عنوان العمل الدائم</span><textarea required value={form.business_address} onChange={(e) => update('business_address', e.target.value)} className={`${fieldClass} min-h-24`} /></label>
          <label className="space-y-2"><span className="font-bold">رقم الرخصة (اختياري)</span><input value={form.license_number} onChange={(e) => update('license_number', e.target.value)} className={fieldClass} /></label>
          <label className="space-y-2"><span className="font-bold">جهة الترخيص (اختياري)</span><input value={form.license_authority} onChange={(e) => update('license_authority', e.target.value)} className={fieldClass} /></label>
          <label className="space-y-2"><span className="font-bold">الهاتف (اختياري)</span><input value={form.phone} onChange={(e) => update('phone', e.target.value)} className={fieldClass} /></label>
          <label className="space-y-2"><span className="font-bold">كلمة المرور</span><div className="relative"><input required minLength={10} type={showPassword ? 'text' : 'password'} value={form.password} onChange={(e) => update('password', e.target.value)} className={`${fieldClass} pl-12`} /><button type="button" onClick={() => setShowPassword((v) => !v)} className="absolute left-3 top-3 text-slate-500" aria-label="إظهار كلمة المرور">{showPassword ? <EyeOff /> : <Eye />}</button></div></label>
        </div>
        <button disabled={loading} className="mt-8 w-full rounded-xl bg-blue-600 px-6 py-4 text-lg font-black text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50">{loading ? 'جاري إنشاء الحساب...' : 'إنشاء الحساب المهني'}</button>
      </form>
    </main>
  );
};

export default AccountantSignupPage;

