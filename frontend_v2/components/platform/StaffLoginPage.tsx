import React, { useState } from "react";
import { Loader2, Lock, ShieldCheck, User2 } from "lucide-react";

import { loginUser } from "../../services/authService";
import { getPlatformStaffCapabilities } from "../../services/platformHiringApi";

/**
 * بابُ دخولِ موظّفي المنصّة — مسارٌ خصوصيٌّ `/staff` (211-C).
 *
 * **لماذا بابٌ ثانٍ وليس تعديلَ الأوّل:** الهبوطُ بعد الدخول يُحسَب في
 * `App.tsx` (`roleDefault`) الذي لا يعرف موظّفَ المنصّة، فيرسله إلى شاشةِ مهامّ
 * **شركةِ الزبون**. وذاك الملفُّ محجوزٌ لمهمّةٍ أخرى، فبدلاً من انتظاره: صفحةٌ
 * قائمةٌ بذاتها **خارجَ شجرة المزوّدات** (كصفحةِ قبول الدعوة تماماً) تُثبت الهويّة
 * ثم تنتقل انتقالاً كاملاً إلى `/platform/employee-space` — فتُعاد تهيئةُ
 * `AuthProvider` من التخزين المحلّي ويهبط الموظّفُ على مساحته مباشرةً.
 *
 * **وليست بوّابةَ صلاحيّة.** الحراسةُ خادميّةٌ كما كانت (`IsPlatformOperationsStaff`
 * وتضييقُ `get_queryset`)؛ هذه الصفحةُ توجيهٌ لا إذن. ولذلك من يدخل منها وليس
 * موظّفَ منصّةٍ **لا يُعاقَب ولا يُخبَر بشيء**: يُرسَل إلى بيته الطبيعيّ `/` —
 * رسالةُ «هذا الباب ليس لك» تُخبر الغريبَ أنّ هنا باباً.
 *
 * ولا يُذكَر هذا المسارُ في صفحة الهبوط ولا في `PublicNavbar` بقرار المالك.
 */
export const StaffLoginPage: React.FC = () => {
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const describe = (message: string): string => {
    if (message === "ACCOUNT_NOT_APPROVED") return "حسابك غير مُفعَّل بعد. راجع مدير العمليات.";
    if (message === "EMAIL_NOT_VERIFIED") return "لم يُفعَّل بريدك بعد.";
    if (message === "INVALID_CREDENTIALS") return "اسم المستخدم أو كلمة المرور غير صحيحة.";
    return message || "تعذّر تسجيل الدخول. حاول مرّةً أخرى.";
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setError("");
    setBusy(true);
    try {
      await loginUser(identifier.trim(), password);
      // **الوجهةُ تُقرَّر بعد أن يحسم الخادمُ من هو**، لا بتخمينٍ من الواجهة.
      // وفشلُ هذا النداء لا يحبس الموظّفَ خارجاً: الجلسةُ صارت قائمةً، فالسقوطُ
      // إلى البيت الطبيعيّ أسلمُ من شاشةِ خطأٍ تُخفي دخولاً ناجحاً.
      let destination = "/";
      try {
        const capabilities = await getPlatformStaffCapabilities();
        if (capabilities.is_platform_employee || capabilities.is_platform_recruiter) {
          destination = "/platform/employee-space";
        }
      } catch {
        destination = "/";
      }
      window.location.assign(destination);
    } catch (cause) {
      setError(describe(cause instanceof Error ? cause.message : ""));
      setBusy(false);
    }
  };

  const field =
    "h-11 w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20";

  return (
    <div
      dir="rtl"
      className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4 py-10"
    >
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-7 shadow-xl">
        <div className="flex flex-col items-center gap-2 pb-6 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-sky-500/10 text-sky-600 dark:text-sky-400">
            <ShieldCheck className="h-6 w-6" />
          </span>
          <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">دخول فريق كترا</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            بابُ موظّفي عمليات المنصّة. لدخول حساب شركتك استعمل الصفحة الرئيسية.
          </p>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <label
              htmlFor="staff-identifier"
              className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300"
            >
              <User2 className="h-4 w-4" />
              اسم المستخدم أو البريد
            </label>
            {/* `type="text"`: اسمُ المستخدم هو ما تُنشئه دعوةُ التوظيف، و`type="email"`
                يجعل المتصفّحَ يرفض إرسالَه قبل أن يبلغ الخادمَ (211-B). */}
            <input
              id="staff-identifier"
              type="text"
              autoComplete="username"
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              className={field}
              required
            />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="staff-password"
              className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300"
            >
              <Lock className="h-4 w-4" />
              كلمة المرور
            </label>
            <input
              id="staff-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className={field}
              required
            />
          </div>

          {error && (
            <p role="alert" className="rounded-lg bg-rose-50 dark:bg-rose-950/40 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-sky-600 text-sm font-bold text-white transition hover:bg-sky-700 disabled:opacity-60"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {busy ? "جارٍ الدخول..." : "دخول"}
          </button>
        </form>
      </div>
    </div>
  );
};

export default StaffLoginPage;
