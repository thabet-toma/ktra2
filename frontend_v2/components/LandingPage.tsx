import React from "react";
import {
  ArrowLeft,
  ArrowUpLeft,
  BarChart3,
  Boxes,
  Building2,
  Calculator,
  Check,
  ChevronLeft,
  CircleDollarSign,
  FileCheck2,
  FileText,
  Globe2,
  LayoutDashboard,
  PackageCheck,
  ReceiptText,
  ShieldCheck,
  Ship,
  Sparkles,
  TrendingUp,
  Users,
  Warehouse,
} from "lucide-react";
import { PublicNavbar } from "./layout/PublicNavbar";

interface LandingPageProps {
  onLogin: () => void;
  onSignup: () => void;
  onGoToStore: () => void;
}

const FEATURES: { icon: React.ElementType; title: string; desc: string; accent: string }[] = [
  {
    icon: Ship,
    title: "الاستيراد والتكاليف",
    desc: "تابع الشحنات والمصاريف والتخليص حتى احتساب التكلفة الفعلية لكل منتج.",
    accent: "bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-300",
  },
  {
    icon: ReceiptText,
    title: "المبيعات والفواتير",
    desc: "أنشئ عروض الأسعار والفواتير وحوّل كل عملية إلى أثر مالي واضح تلقائياً.",
    accent: "bg-violet-50 text-violet-600 dark:bg-violet-500/10 dark:text-violet-300",
  },
  {
    icon: Warehouse,
    title: "المخزون والمستودعات",
    desc: "اعرف الرصيد المتاح وحركة المنتجات ونقاط إعادة الطلب لحظة بلحظة.",
    accent: "bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-300",
  },
  {
    icon: Calculator,
    title: "محاسبة مترابطة",
    desc: "قيود يومية ودليل حسابات وتقارير مالية تنمو مع عمليات شركتك.",
    accent: "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-300",
  },
  {
    icon: Users,
    title: "العملاء والموردون",
    desc: "كشوف حساب وأرصدة وأعمار ديون في ملف موحّد لكل شريك تجاري.",
    accent: "bg-cyan-50 text-cyan-600 dark:bg-cyan-500/10 dark:text-cyan-300",
  },
  {
    icon: BarChart3,
    title: "قرار مبني على البيانات",
    desc: "لوحات متابعة تعرض ما يستحق انتباهك وتحوّل الأرقام إلى قرارات.",
    accent: "bg-rose-50 text-rose-600 dark:bg-rose-500/10 dark:text-rose-300",
  },
];

const TRUST_POINTS = ["واجهة عربية كاملة", "تعدّد الشركات والفروع", "عزل آمن لبيانات كل شركة"];

export const LandingPage: React.FC<LandingPageProps> = ({ onLogin, onSignup, onGoToStore }) => (
  <div dir="rtl" className="min-h-screen overflow-hidden bg-[#f7f9fc] font-sans text-slate-950 selection:bg-blue-200 dark:bg-slate-950 dark:text-white dark:selection:bg-blue-800">
    <PublicNavbar />

    <main>
      <section className="relative isolate border-b border-slate-200/70 pb-14 pt-28 dark:border-white/10 lg:pb-20 lg:pt-36">
        <div className="pointer-events-none absolute inset-0 -z-20 bg-[radial-gradient(circle_at_77%_22%,rgba(37,99,235,0.13),transparent_31%),radial-gradient(circle_at_14%_30%,rgba(14,165,233,0.11),transparent_27%)] dark:bg-[radial-gradient(circle_at_77%_22%,rgba(37,99,235,0.22),transparent_32%),radial-gradient(circle_at_12%_35%,rgba(14,165,233,0.12),transparent_28%)]" />
        <div className="pointer-events-none absolute inset-0 -z-10 bg-[linear-gradient(to_right,rgba(148,163,184,0.08)_1px,transparent_1px),linear-gradient(to_bottom,rgba(148,163,184,0.08)_1px,transparent_1px)] bg-[size:44px_44px] [mask-image:linear-gradient(to_bottom,black,transparent_88%)]" />

        <div className="mx-auto grid max-w-7xl items-center gap-14 px-5 sm:px-8 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16 lg:px-10">
          <div className="relative z-10 max-w-2xl lg:order-2">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-blue-200/80 bg-white/80 px-3.5 py-2 text-sm font-bold text-blue-700 shadow-sm shadow-blue-100/70 backdrop-blur dark:border-blue-400/20 dark:bg-blue-400/10 dark:text-blue-200 dark:shadow-none">
              <Sparkles className="h-4 w-4" />
              نظام تشغيل متكامل لشركتك التجارية
            </div>
            <h1 className="text-4xl font-black leading-[1.22] tracking-tight text-slate-950 sm:text-5xl lg:text-[3.75rem] dark:text-white">
              كل عملياتك التجارية،
              <span className="mt-1 block bg-gradient-to-l from-blue-700 via-blue-600 to-cyan-500 bg-clip-text text-transparent dark:from-blue-400 dark:via-cyan-300 dark:to-emerald-300">
                في منصة واحدة واضحة.
              </span>
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-8 text-slate-600 sm:text-xl sm:leading-9 dark:text-slate-300">
              اربط الاستيراد والمبيعات والمخزون والمحاسبة في دورة عمل واحدة، واخرج من تشتّت الملفات إلى رؤية دقيقة تساعدك على النمو.
            </p>

            <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
              <button
                type="button"
                onClick={onSignup}
                aria-label="إنشاء حساب جديد"
                className="group inline-flex min-h-14 items-center justify-center gap-3 rounded-2xl bg-blue-600 px-7 text-base font-extrabold text-white shadow-xl shadow-blue-600/25 transition duration-300 hover:-translate-y-0.5 hover:bg-blue-700 hover:shadow-blue-600/35 focus:outline-none focus:ring-4 focus:ring-blue-200 dark:focus:ring-blue-900"
              >
                ابدأ بإعداد شركتك
                <ArrowLeft className="h-5 w-5 transition-transform group-hover:-translate-x-1" />
              </button>
              <button
                type="button"
                onClick={onLogin}
                className="inline-flex min-h-14 items-center justify-center gap-2 rounded-2xl px-6 font-bold text-slate-700 transition hover:bg-white hover:text-blue-700 hover:shadow-sm focus:outline-none focus:ring-4 focus:ring-slate-200 dark:text-slate-200 dark:hover:bg-white/5 dark:hover:text-blue-300 dark:focus:ring-slate-800"
              >
                لديك حساب؟ تسجيل الدخول
                <ChevronLeft className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-8 flex flex-wrap gap-x-5 gap-y-3 border-t border-slate-200/80 pt-6 dark:border-white/10">
              {TRUST_POINTS.map((point) => (
                <span key={point} className="inline-flex items-center gap-2 text-sm font-semibold text-slate-600 dark:text-slate-300">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300">
                    <Check className="h-3.5 w-3.5" strokeWidth={3} />
                  </span>
                  {point}
                </span>
              ))}
            </div>
          </div>

          <div className="relative mx-auto w-full max-w-2xl lg:order-1">
            <div className="absolute -inset-5 -z-10 rounded-[2.5rem] bg-gradient-to-bl from-blue-500/15 via-cyan-400/10 to-transparent blur-2xl" />
            <div className="overflow-hidden rounded-[1.6rem] border border-white/80 bg-white/90 p-2 shadow-[0_30px_80px_-30px_rgba(15,23,42,0.35)] ring-1 ring-slate-200/70 backdrop-blur-xl dark:border-white/10 dark:bg-slate-900/90 dark:ring-white/10">
              <div className="overflow-hidden rounded-[1.2rem] border border-slate-200 bg-slate-50 dark:border-white/10 dark:bg-slate-950">
                <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 dark:border-white/10 dark:bg-slate-900">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white">
                      <LayoutDashboard className="h-4 w-4" />
                    </div>
                    <div>
                      <p className="text-[11px] font-extrabold text-slate-800 dark:text-white">لوحة الأعمال</p>
                      <p className="text-[9px] text-slate-400">نظرة عامة • اليوم</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-rose-400" />
                    <span className="h-2 w-2 rounded-full bg-amber-400" />
                    <span className="h-2 w-2 rounded-full bg-emerald-400" />
                  </div>
                </div>

                <div className="grid grid-cols-[3.8rem_1fr] sm:grid-cols-[8rem_1fr]">
                  <aside className="border-l border-slate-200 bg-white p-2 sm:p-3 dark:border-white/10 dark:bg-slate-900">
                    <div className="space-y-1.5">
                      {[LayoutDashboard, FileText, Boxes, Users, BarChart3].map((Icon, index) => (
                        <div
                          key={index}
                          className={`flex items-center gap-2 rounded-lg p-2 text-[9px] font-semibold ${index === 0 ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300" : "text-slate-400"}`}
                        >
                          <Icon className="h-3.5 w-3.5 shrink-0" />
                          <span className="hidden sm:inline">{["الرئيسية", "الفواتير", "المخزون", "الشركاء", "التقارير"][index]}</span>
                        </div>
                      ))}
                    </div>
                  </aside>

                  <div className="min-w-0 p-3 sm:p-5">
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3">
                      {[
                        { label: "صافي المبيعات", value: "₪ 128,450", change: "+12.4%", icon: CircleDollarSign, tone: "text-blue-600 bg-blue-50 dark:bg-blue-500/10 dark:text-blue-300" },
                        { label: "قيمة المخزون", value: "₪ 84,920", change: "+4.8%", icon: PackageCheck, tone: "text-violet-600 bg-violet-50 dark:bg-violet-500/10 dark:text-violet-300" },
                        { label: "فواتير مستحقة", value: "₪ 16,780", change: "8 فواتير", icon: FileCheck2, tone: "text-amber-600 bg-amber-50 dark:bg-amber-500/10 dark:text-amber-300" },
                      ].map(({ label, value, change, icon: Icon, tone }, index) => (
                        <div key={label} className={`rounded-xl border border-slate-200 bg-white p-2.5 sm:p-3 dark:border-white/10 dark:bg-slate-900 ${index === 2 ? "col-span-2 sm:col-span-1" : ""}`}>
                          <div className="flex items-center justify-between gap-2">
                            <span className={`rounded-lg p-1.5 ${tone}`}><Icon className="h-3.5 w-3.5" /></span>
                            <span className="text-[8px] font-bold text-emerald-600 dark:text-emerald-400">{change}</span>
                          </div>
                          <p className="mt-2 text-[8px] text-slate-400 sm:text-[9px]">{label}</p>
                          <p className="mt-0.5 text-[11px] font-black text-slate-800 sm:text-sm dark:text-white">{value}</p>
                        </div>
                      ))}
                    </div>

                    <div className="mt-3 grid gap-3 sm:grid-cols-[1.45fr_0.75fr]">
                      <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-white/10 dark:bg-slate-900">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-[10px] font-extrabold text-slate-700 dark:text-slate-200">أداء المبيعات</p>
                            <p className="mt-0.5 text-[8px] text-slate-400">آخر 6 أشهر</p>
                          </div>
                          <TrendingUp className="h-4 w-4 text-emerald-500" />
                        </div>
                        <div className="mt-4 flex h-24 items-end gap-2 border-b border-slate-100 px-1 dark:border-white/5 sm:h-28 sm:gap-3">
                          {[42, 57, 48, 72, 64, 88, 78, 96].map((height, index) => (
                            <div key={index} className="group relative flex h-full flex-1 items-end">
                              <div className={`w-full rounded-t-sm ${index === 7 ? "bg-blue-600" : "bg-blue-200 dark:bg-blue-500/25"}`}>
                                <span className={`block w-full rounded-t-sm ${height >= 80 ? "h-20 sm:h-24" : height >= 65 ? "h-16 sm:h-20" : height >= 50 ? "h-12 sm:h-16" : "h-10 sm:h-12"}`} />
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="rounded-xl bg-slate-900 p-3 text-white dark:bg-blue-600/15 dark:ring-1 dark:ring-blue-400/20">
                        <p className="text-[9px] font-bold text-slate-300 dark:text-blue-200">صحة الأعمال</p>
                        <div className="mx-auto mt-4 flex h-20 w-20 items-center justify-center rounded-full border-[9px] border-emerald-400 border-l-slate-700 text-center dark:border-l-blue-950">
                          <div><strong className="block text-lg">92%</strong><span className="text-[7px] text-slate-400">ممتاز</span></div>
                        </div>
                        <div className="mt-4 flex items-center gap-2 rounded-lg bg-white/5 p-2 text-[8px] text-slate-300">
                          <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                          الحسابات متوازنة
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="absolute -bottom-5 -right-2 hidden items-center gap-3 rounded-2xl border border-white bg-white p-3.5 shadow-xl shadow-slate-900/10 sm:flex dark:border-white/10 dark:bg-slate-800">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-100 text-emerald-600 dark:bg-emerald-400/10 dark:text-emerald-300">
                <Check className="h-5 w-5" strokeWidth={3} />
              </div>
              <div><p className="text-xs font-extrabold text-slate-800 dark:text-white">تم ترحيل الفاتورة</p><p className="mt-0.5 text-[10px] text-slate-400">القيد المحاسبي أُنشئ تلقائياً</p></div>
            </div>
          </div>
        </div>

        <div className="mx-auto mt-16 max-w-7xl px-5 sm:px-8 lg:px-10">
          <div className="grid overflow-hidden rounded-2xl border border-slate-200/80 bg-white/70 shadow-sm backdrop-blur sm:grid-cols-2 lg:grid-cols-4 dark:border-white/10 dark:bg-white/5">
            {[
              { icon: Building2, title: "شركة واحدة أو أكثر", text: "مساحات عمل مستقلة" },
              { icon: Globe2, title: "عربي من الأساس", text: "تجربة RTL متكاملة" },
              { icon: ShieldCheck, title: "صلاحيات دقيقة", text: "وصول يناسب كل دور" },
              { icon: PackageCheck, title: "معلومات لحظية", text: "من المصدر إلى التقرير" },
            ].map(({ icon: Icon, title, text }) => (
              <div key={title} className="flex items-center gap-3 border-b border-slate-200/80 p-4 last:border-0 sm:[&:nth-child(odd)]:border-l lg:border-b-0 lg:border-l lg:last:border-l-0 dark:border-white/10">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-blue-600 dark:bg-white/5 dark:text-blue-300"><Icon className="h-5 w-5" /></span>
                <div><p className="text-sm font-extrabold text-slate-800 dark:text-white">{title}</p><p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{text}</p></div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-white py-20 dark:bg-slate-950 lg:py-28">
        <div className="mx-auto max-w-7xl px-5 sm:px-8 lg:px-10">
          <div className="grid items-end gap-5 md:grid-cols-[1fr_0.75fr]">
            <div>
              <span className="text-sm font-extrabold text-blue-600 dark:text-blue-400">منظومة واحدة، بلا فجوات</span>
              <h2 className="mt-3 max-w-2xl text-3xl font-black leading-tight tracking-tight text-slate-950 sm:text-4xl dark:text-white">ما يحدث في التشغيل ينعكس فوراً في أرقامك.</h2>
            </div>
            <p className="max-w-xl text-base leading-7 text-slate-600 dark:text-slate-400">لا إدخال متكرر ولا ملفات منفصلة. صُممت الوحدات لتعمل معاً حتى تعرف أين تقف شركتك في أي لحظة.</p>
          </div>

          <div className="mt-12 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, desc, accent }) => (
              <article key={title} className="group rounded-3xl border border-slate-200 bg-white p-6 transition duration-300 hover:-translate-y-1 hover:border-blue-200 hover:shadow-xl hover:shadow-slate-900/5 dark:border-white/10 dark:bg-slate-900/50 dark:hover:border-blue-400/30">
                <div className={`flex h-12 w-12 items-center justify-center rounded-2xl transition-transform duration-300 group-hover:scale-105 ${accent}`}><Icon className="h-6 w-6" /></div>
                <h3 className="mt-5 text-lg font-extrabold text-slate-900 dark:text-white">{title}</h3>
                <p className="mt-2 text-sm leading-7 text-slate-600 dark:text-slate-400">{desc}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="relative overflow-hidden border-y border-slate-200 bg-slate-950 py-20 text-white dark:border-white/10 lg:py-24">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_80%_0%,rgba(37,99,235,0.35),transparent_34%),radial-gradient(circle_at_10%_100%,rgba(14,165,233,0.18),transparent_30%)]" />
        <div className="relative mx-auto grid max-w-7xl items-center gap-12 px-5 sm:px-8 lg:grid-cols-2 lg:px-10">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-bold text-blue-200"><Boxes className="h-4 w-4" />تدفق عمل مترابط</span>
            <h2 className="mt-5 text-3xl font-black leading-tight sm:text-4xl">من أول طلب شراء إلى صافي الربح.</h2>
            <p className="mt-4 max-w-xl text-base leading-8 text-slate-300">اجعل كل خطوة تكمل التي قبلها. تقل الأخطاء، تختصر وقت الفريق، وتصبح الصورة المالية جاهزة دون انتظار نهاية الشهر.</p>
            <button type="button" onClick={onGoToStore} className="group mt-7 inline-flex items-center gap-2 text-sm font-extrabold text-cyan-300 transition hover:text-white focus:outline-none focus:ring-2 focus:ring-cyan-400/60">
              استكشف واجهة المتجر
              <ArrowUpLeft className="h-4 w-4 transition-transform group-hover:-translate-x-0.5 group-hover:-translate-y-0.5" />
            </button>
          </div>

          <div className="relative grid gap-3 sm:grid-cols-2">
            {[
              { step: "01", icon: FileText, title: "عملية موثّقة", text: "فاتورة أو شحنة أو حركة مخزون" },
              { step: "02", icon: Boxes, title: "تحديث تلقائي", text: "الأرصدة والتكلفة تتحدث فوراً" },
              { step: "03", icon: Calculator, title: "أثر محاسبي", text: "قيود دقيقة مرتبطة بالمصدر" },
              { step: "04", icon: TrendingUp, title: "قرار أوضح", text: "تقارير حديثة وجاهزة للتحليل" },
            ].map(({ step, icon: Icon, title, text }) => (
              <div key={step} className="relative rounded-2xl border border-white/10 bg-white/[0.06] p-5 backdrop-blur transition hover:bg-white/[0.09]">
                <span className="absolute left-4 top-4 text-xs font-black text-white/20">{step}</span>
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/15 text-blue-300"><Icon className="h-5 w-5" /></div>
                <h3 className="mt-4 font-extrabold">{title}</h3>
                <p className="mt-1.5 text-sm text-slate-400">{text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-white py-16 dark:bg-slate-950">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-8 px-5 sm:px-8 md:flex-row lg:px-10">
          <div>
            <p className="text-sm font-extrabold text-blue-600 dark:text-blue-400">K.T.R.A تنمو معك</p>
            <h2 className="mt-2 text-2xl font-black text-slate-950 sm:text-3xl dark:text-white">ابدأ بهيكل واضح من اليوم الأول.</h2>
            <p className="mt-3 text-slate-600 dark:text-slate-400">أنشئ حسابك ثم جهّز مساحة شركتك بخطوات قصيرة ومباشرة.</p>
          </div>
          <div className="flex items-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-emerald-800 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-200">
            <ShieldCheck className="h-6 w-6 shrink-0" />
            <div><p className="text-sm font-extrabold">بيانات شركتك تبقى لشركتك</p><p className="mt-0.5 text-xs opacity-75">عزل وصلاحيات على مستوى مساحة العمل</p></div>
          </div>
        </div>
      </section>
    </main>

    <footer className="border-t border-slate-200 bg-slate-50 py-8 dark:border-white/10 dark:bg-slate-950">
      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-3 px-5 text-sm text-slate-500 sm:px-8 md:flex-row lg:px-10 dark:text-slate-400">
        <p>© {new Date().getFullYear()} K.T.R.A. جميع الحقوق محفوظة.</p>
        <p>منصة عربية لإدارة الشركات التجارية.</p>
      </div>
    </footer>
  </div>
);
