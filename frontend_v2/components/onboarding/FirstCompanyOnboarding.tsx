import React, { useState } from "react";
import { ArrowLeft, Building2, Calculator, Disc, CheckCircle2, Loader2, LogOut, ShieldCheck } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { useCompany } from "../../contexts/CompanyContext";
import { clientLogger } from "../../services/logger";
import { LogoIcon } from "../icons/LogoIcon";
import { SELF_SERVE_COMPANY_TEMPLATES, DEFAULT_COMPANY_TEMPLATE, type CompanyTemplateKey } from "../../utils/companyTemplates";

const TEMPLATE_ICONS: Record<string, React.FC<{ className?: string }>> = {
  Building2,
  Calculator,
  Disc,
};

export const FirstCompanyOnboarding: React.FC = () => {
  const { logout } = useAuth();
  const { createCompany } = useCompany();
  const [companyName, setCompanyName] = useState("");
  const [template, setTemplate] = useState<CompanyTemplateKey>(DEFAULT_COMPANY_TEMPLATE);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const name = companyName.trim();
    if (!name) {
      setError("أدخل اسم الشركة للمتابعة.");
      return;
    }

    const startedAt = performance.now();
    setSubmitting(true);
    setError(null);
    clientLogger.info("onboarding.company_create_started");
    try {
      await createCompany(name, template);
      clientLogger.info("onboarding.company_create_succeeded", {
        durationMs: Math.round(performance.now() - startedAt),
      });
      window.location.replace("/dashboard");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "تعذّر إنشاء الشركة. حاول مرة أخرى.");
      clientLogger.error("onboarding.company_create_failed", {
        durationMs: Math.round(performance.now() - startedAt),
      });
      setSubmitting(false);
    }
  };

  return (
    <main dir="rtl" className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-slate-100 px-4 py-8 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950 sm:py-14">
      <div className="mx-auto max-w-5xl">
        <header className="mb-10 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-white p-2 shadow-md dark:bg-gray-800"><LogoIcon className="h-9 w-9 text-blue-600" /></div>
            <span className="font-bold text-gray-900 dark:text-white">K.T.R.A</span>
          </div>
          <button type="button" onClick={() => void logout()} className="flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-gray-600 transition hover:bg-white hover:text-red-600 dark:text-gray-300 dark:hover:bg-gray-800"><LogOut className="h-4 w-4" />تسجيل الخروج</button>
        </header>

        <div className="grid items-center gap-10 lg:grid-cols-2">
          <section>
            <p className="font-semibold text-blue-600 dark:text-blue-400">مرحباً بك في K.T.R.A</p>
            <h1 className="mt-3 text-4xl font-bold leading-tight text-gray-950 dark:text-white">لنُنشئ شركتك الأولى</h1>
            <p className="mt-4 text-lg leading-8 text-gray-600 dark:text-gray-300">سنجهز تلقائياً الإعدادات الأساسية والفرع والمستودع ودليل الحسابات، لتبدأ العمل مباشرة.</p>
            <ul className="mt-8 space-y-4">
              {["١. حسابك جاهز ومفعّل", "٢. أدخل اسم شركتك في النموذج", "٣. سنجهّز مساحة العمل ونفتح لوحة التحكم"].map((item) => (
                <li key={item} className="flex items-center gap-3 text-gray-700 dark:text-gray-200"><CheckCircle2 className="h-5 w-5 text-emerald-600" />{item}</li>
              ))}
            </ul>
          </section>

          <section className="rounded-3xl border border-gray-200 bg-white p-6 shadow-2xl shadow-blue-950/10 dark:border-gray-700 dark:bg-gray-800 sm:p-8">
            <div className="mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600 text-white"><Building2 className="h-7 w-7" /></div>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">بيانات الشركة</h2>
            <p className="mt-2 text-sm leading-6 text-gray-600 dark:text-gray-400">أدخل الاسم الذي تريد ظهوره في الفواتير ولوحة التحكم. يمكنك تعديله لاحقاً.</p>

            <form onSubmit={handleSubmit} className="mt-7 space-y-5">
              {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300">{error}</div>}
              <label className="block">
                <span className="mb-2 block text-sm font-semibold text-gray-700 dark:text-gray-200">اسم الشركة</span>
                <input name="companyName" autoComplete="organization" autoFocus value={companyName} onChange={(event) => setCompanyName(event.target.value)} disabled={submitting} required className="w-full rounded-xl border border-gray-300 bg-gray-50 px-4 py-4 text-gray-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 disabled:opacity-60 dark:border-gray-600 dark:bg-gray-900 dark:text-white" placeholder="مثال: شركة الأفق للتجارة" />
              </label>
              <div>
                <span className="mb-2 block text-sm font-semibold text-gray-700 dark:text-gray-200">نوع الشركة</span>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {SELF_SERVE_COMPANY_TEMPLATES.map((option) => {
                    const Icon = TEMPLATE_ICONS[option.icon] ?? Building2;
                    const isSelected = template === option.key;
                    return (
                      <button
                        key={option.key}
                        type="button"
                        onClick={() => setTemplate(option.key)}
                        disabled={submitting}
                        aria-pressed={isSelected}
                        className={`flex flex-col items-start gap-2 rounded-xl border p-4 text-right transition disabled:cursor-not-allowed disabled:opacity-60 ${
                          isSelected
                            ? "border-blue-500 bg-blue-50 ring-2 ring-blue-500/20 dark:bg-blue-950/30"
                            : "border-gray-300 bg-gray-50 hover:border-blue-300 dark:border-gray-600 dark:bg-gray-900"
                        }`}
                      >
                        <Icon className={`h-6 w-6 ${isSelected ? "text-blue-600" : "text-gray-500 dark:text-gray-400"}`} />
                        <span className="font-bold text-gray-900 dark:text-white">{option.name}</span>
                        <span className="text-xs leading-5 text-gray-600 dark:text-gray-400">{option.description}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
              <button type="submit" disabled={submitting} className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-4 font-bold text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
                {submitting ? <><Loader2 className="h-5 w-5 animate-spin" />جاري تجهيز شركتك...</> : <>إنشاء الشركة والمتابعة<ArrowLeft className="h-5 w-5" /></>}
              </button>
              <p className="flex items-center justify-center gap-2 text-xs text-gray-500 dark:text-gray-400"><ShieldCheck className="h-4 w-4" />لن نرسل اسم الشركة ضمن سجلات المتصفح.</p>
            </form>
          </section>
        </div>
      </div>
    </main>
  );
};
