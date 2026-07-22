import React, { useState } from "react";
import { ArrowLeft, BarChart3, Boxes, Building2, Eye, EyeOff, Lock, Mail, ShieldCheck, User } from "lucide-react";
import { signupUser } from "../services/authService";
import { clientLogger } from "../services/logger";
import { LogoIcon } from "./icons/LogoIcon";
import { PublicNavbar } from "./layout/PublicNavbar";

interface SignupPageProps {
  onNavigateToLogin: () => void;
}

const BENEFITS = [
  { icon: Boxes, title: "مخزون ومبيعات مترابطة", description: "تابع الأصناف والفواتير والحركات من مساحة عمل واحدة." },
  { icon: BarChart3, title: "أرقام واضحة لحظياً", description: "لوحات وتقارير تساعدك على اتخاذ القرار بثقة." },
  { icon: ShieldCheck, title: "بيانات كل شركة معزولة", description: "ابدأ بشركتك الأولى وأضف فرقك وفروعك لاحقاً." },
];

export const SignupPage: React.FC<SignupPageProps> = ({ onNavigateToLogin }) => {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);

    const normalizedName = fullName.trim();
    const normalizedEmail = email.trim();
    if (!normalizedName) {
      setError("أدخل اسمك الكامل.");
      return;
    }
    if (password.length < 6) {
      setError("يجب أن تكون كلمة المرور 6 أحرف على الأقل.");
      return;
    }

    const startedAt = performance.now();
    setIsLoading(true);
    clientLogger.info("onboarding.signup_started");
    try {
      await signupUser({ fullName: normalizedName, email: normalizedEmail, password });
      setSuccess(true);
      clientLogger.info("onboarding.signup_succeeded", {
        durationMs: Math.round(performance.now() - startedAt),
      });
      window.setTimeout(onNavigateToLogin, 1500);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "تعذّر إنشاء الحساب. حاول مرة أخرى.";
      setError(message);
      clientLogger.error("onboarding.signup_failed", {
        durationMs: Math.round(performance.now() - startedAt),
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div dir="rtl" className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50 dark:from-gray-950 dark:via-gray-900 dark:to-slate-900">
      <PublicNavbar />
      <main className="mx-auto grid min-h-screen max-w-6xl items-center gap-10 px-4 pb-12 pt-28 lg:grid-cols-2 lg:px-8">
        <section className="order-2 lg:order-1">
          <div className="mb-8 flex items-center gap-4">
            <div className="rounded-2xl bg-white p-3 shadow-lg ring-1 ring-gray-100 dark:bg-gray-800 dark:ring-gray-700">
              <LogoIcon className="h-11 w-11 text-blue-600" />
            </div>
            <div>
              <p className="text-sm font-semibold text-blue-600 dark:text-blue-400">ابدأ خلال دقائق</p>
              <h1 className="text-3xl font-bold text-gray-900 dark:text-white sm:text-4xl">مساحة عملك التجارية تبدأ هنا</h1>
            </div>
          </div>
          <p className="max-w-xl text-lg leading-8 text-gray-600 dark:text-gray-300">
            أنشئ حسابك أولاً، ثم سنرشدك لإنشاء شركتك وإعداد بيئة العمل المناسبة لك.
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-3 lg:grid-cols-1">
            {BENEFITS.map(({ icon: Icon, title, description }) => (
              <div key={title} className="flex gap-4 rounded-2xl border border-gray-200 bg-white/80 p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800/70">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600 dark:bg-blue-950/60 dark:text-blue-300">
                  <Icon className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="font-bold text-gray-900 dark:text-white">{title}</h2>
                  <p className="mt-1 text-sm leading-6 text-gray-600 dark:text-gray-400">{description}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="order-1 rounded-3xl border border-gray-200 bg-white p-6 shadow-2xl shadow-blue-950/10 dark:border-gray-700 dark:bg-gray-800 sm:p-8 lg:order-2">
          <div className="mb-7">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-600 text-white">
              <Building2 className="h-6 w-6" />
            </div>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">إنشاء حساب جديد</h2>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">ثلاثة حقول فقط، وستنشئ شركتك في الخطوة التالية.</p>
          </div>

          {success ? (
            <div role="status" className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">
              <p className="font-bold">تم إنشاء حسابك بنجاح.</p>
              <p className="mt-1 text-sm">سيتم نقلك الآن إلى تسجيل الدخول.</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              {error && (
                <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">
                  {error}
                </div>
              )}

              <label className="block">
                <span className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-200"><User className="h-4 w-4" />الاسم الكامل</span>
                <input name="fullName" autoComplete="name" value={fullName} onChange={(event) => setFullName(event.target.value)} required className="w-full rounded-xl border border-gray-300 bg-gray-50 px-4 py-3.5 text-gray-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-gray-900 dark:text-white" placeholder="مثال: محمد أحمد" />
              </label>

              <label className="block">
                <span className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-200"><Mail className="h-4 w-4" />البريد الإلكتروني</span>
                <input name="email" type="email" inputMode="email" autoComplete="email" dir="ltr" value={email} onChange={(event) => setEmail(event.target.value)} required className="w-full rounded-xl border border-gray-300 bg-gray-50 px-4 py-3.5 text-left text-gray-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-gray-900 dark:text-white" placeholder="name@example.com" />
              </label>

              <label className="block">
                <span className="mb-2 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-200"><Lock className="h-4 w-4" />كلمة المرور</span>
                <span className="relative block">
                  <input name="password" type={showPassword ? "text" : "password"} autoComplete="new-password" minLength={6} value={password} onChange={(event) => setPassword(event.target.value)} required className="w-full rounded-xl border border-gray-300 bg-gray-50 px-4 py-3.5 pl-12 text-gray-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 dark:border-gray-600 dark:bg-gray-900 dark:text-white" placeholder="6 أحرف على الأقل" />
                  <button type="button" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "إخفاء كلمة المرور" : "إظهار كلمة المرور"} className="absolute left-2 top-1/2 -translate-y-1/2 rounded-lg p-2 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700">
                    {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                  </button>
                </span>
              </label>

              <button type="submit" disabled={isLoading} className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-4 font-bold text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
                {isLoading ? "جاري إنشاء الحساب..." : "إنشاء الحساب"}
                {!isLoading && <ArrowLeft className="h-5 w-5" />}
              </button>
            </form>
          )}

          <p className="mt-6 text-center text-sm text-gray-600 dark:text-gray-400">
            لديك حساب بالفعل؟{" "}
            <button type="button" onClick={onNavigateToLogin} className="font-bold text-blue-600 hover:text-blue-700 dark:text-blue-400">تسجيل الدخول</button>
          </p>
        </section>
      </main>
    </div>
  );
};
