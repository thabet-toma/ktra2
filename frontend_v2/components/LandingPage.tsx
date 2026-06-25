import React from 'react';
import { LogoIcon } from './icons/LogoIcon';
import { PublicNavbar } from './layout/PublicNavbar';
import {
  Ship, FileText, Warehouse, Calculator, Users, BarChart3,
  Globe, Shield, ArrowLeft, CheckCircle2, Building2, Boxes, Store, UserCog,
} from 'lucide-react';

interface LandingPageProps {
  onLogin: () => void;
  /** نوع التسجيل: 'trader' تاجر/شركة، 'employee' موظف/فريق كترا. */
  onSignup: (type: 'trader' | 'employee') => void;
  onGoToStore: () => void;
}

// ميزات المنصة — مصدر واحد للبيانات (DRY) تُرسم في شبكة البطاقات.
const FEATURES: { icon: React.ElementType; title: string; desc: string }[] = [
  { icon: Ship, title: 'الاستيراد والتخليص الجمركي', desc: 'إدارة صفقات الاستيراد من العرض حتى الوصول: الشحنات، التخليص، احتساب التكلفة النهائية (Landed Cost) والمصاريف الجمركية.' },
  { icon: FileText, title: 'الفواتير والمبيعات', desc: 'فواتير بيع وشراء وعروض أسعار وإشعارات دائن/مدين، مع ترحيل محاسبي تلقائي وأسعار مقترحة لكل عميل.' },
  { icon: Warehouse, title: 'المخزون والأصناف', desc: 'أرصدة لحظية، حركات مخزون، تحويل بين المستودعات، جرد، وتنبيهات نفاد الكمية والحد الأدنى.' },
  { icon: Calculator, title: 'المحاسبة والقيود', desc: 'دليل حسابات كامل، قيود يومية، كشوف حسابات، قائمة الدخل وتكلفة البضاعة المباعة بدقة.' },
  { icon: Users, title: 'الموردون والعملاء', desc: 'بطاقات وكشوف حساب للأطراف، أعمار الديون، سندات قبض وصرف، وربط مباشر بالفواتير.' },
  { icon: BarChart3, title: 'التقارير ولوحات المتابعة', desc: 'تقارير أرباح الفواتير، أرصدة الأطراف، حركة المخزون — قابلة للتصدير والطباعة PDF.' },
];

const HIGHLIGHTS = [
  'يعمل دون اتصال (PWA) مع مزامنة تلقائية عند عودة الشبكة',
  'دعم كامل للغة العربية واتجاه RTL',
  'تعدّد الشركات والفروع مع عزل بيانات آمن',
];

export const LandingPage: React.FC<LandingPageProps> = ({ onLogin, onSignup }) => {
  const scrollToPaths = () => {
    document.getElementById('signup-paths')?.scrollIntoView({ behavior: 'smooth' });
  };
  return (
    <div dir="rtl" className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-[var(--color-primary)] dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 font-sans relative overflow-hidden">
      <PublicNavbar />

      {/* خلفية زخرفية */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-blue-200 dark:bg-blue-900/20 rounded-full blur-3xl opacity-50"></div>
        <div className="absolute bottom-20 -left-40 w-96 h-96 bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/20 rounded-full blur-3xl opacity-50"></div>
      </div>

      <div className="relative z-10 max-w-6xl mx-auto px-4 pt-28 pb-16">

        {/* ── Hero ── */}
        <section className="flex flex-col items-center text-center animate-fade-in">
          <div className="relative group mb-8">
            <div className="absolute inset-0 bg-gradient-to-r from-blue-400 to-[var(--color-primary)] rounded-full blur-lg opacity-30 animate-pulse group-hover:opacity-50 transition-opacity"></div>
            <div className="relative p-4 bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-100 dark:border-gray-700">
              <LogoIcon className="h-14 w-14 text-blue-600 dark:text-blue-400" />
            </div>
          </div>

          <h1 className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-blue-600 via-[var(--color-primary)] to-blue-600 bg-clip-text text-transparent leading-tight max-w-3xl">
            منصة K.T.R.A لإدارة الاستيراد والتجارة
          </h1>
          <p className="mt-5 text-lg md:text-xl text-gray-600 dark:text-gray-300 max-w-2xl">
            نظام متكامل يجمع الاستيراد والتخليص الجمركي، الفواتير، المخزون والمحاسبة في مكان واحد —
            مصمَّم لشركات التجارة العالمية.
          </p>

          {/* شارات الثقة */}
          <div className="flex flex-wrap justify-center gap-3 mt-7">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-full text-sm">
              <Globe className="w-4 h-4" />
              <span>K.T.R.A العالمية</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/30 text-[var(--color-primary)] rounded-full text-sm">
              <Shield className="w-4 h-4" />
              <span>أكثر من 20 سنة خبرة</span>
            </div>
          </div>

          {/* أزرار الإجراء */}
          <div className="flex flex-col sm:flex-row items-center gap-4 mt-10 w-full sm:w-auto">
            <button
              onClick={onLogin}
              className="w-full sm:w-auto group bg-gradient-to-r from-blue-600 to-[var(--color-primary)] text-white font-bold py-4 px-8 rounded-xl text-lg hover:from-blue-700 hover:to-[var(--color-primary)] hover:shadow-xl hover:shadow-blue-500/25 transition-all duration-300 flex items-center justify-center gap-2"
            >
              <span>تسجيل الدخول</span>
              <ArrowLeft className="w-5 h-5 group-hover:-translate-x-1 transition-transform" />
            </button>
            <button
              onClick={scrollToPaths}
              className="w-full sm:w-auto bg-white dark:bg-gray-700 border-2 border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-200 font-bold py-4 px-8 rounded-xl text-lg hover:bg-gray-50 dark:hover:bg-gray-600 hover:border-gray-300 hover:shadow-lg transition-all duration-300"
            >
              إنشاء حساب جديد
            </button>
          </div>
        </section>

        {/* ── مساران للتسجيل: التجار/الشركات و الموظفون/فريق كترا ── */}
        <section id="signup-paths" className="mt-24 scroll-mt-28">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-gray-800 dark:text-gray-100">اختر نوع حسابك</h2>
            <p className="mt-3 text-gray-600 dark:text-gray-400">واجهتان مختلفتان حسب دورك في المنصة.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl mx-auto">
            {/* التجار وأصحاب الشركات */}
            <div className="group p-8 bg-white/90 dark:bg-gray-800/80 backdrop-blur-sm rounded-2xl shadow-lg border border-gray-100/70 dark:border-gray-700/60 hover:shadow-xl hover:-translate-y-1 transition-all duration-300 flex flex-col">
              <div className="w-14 h-14 rounded-xl bg-gradient-to-tr from-blue-600 to-[var(--color-primary)] flex items-center justify-center mb-5 shadow-md">
                <Store className="w-7 h-7 text-white" />
              </div>
              <h3 className="text-xl font-bold text-gray-800 dark:text-gray-100 mb-2">للتجار وأصحاب الشركات</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed mb-6 flex-1">
                سجّل شركتك أو متجرك وأدر الاستيراد والتخليص، الفواتير، المخزون والمحاسبة في منصة واحدة.
              </p>
              <button
                onClick={() => onSignup('trader')}
                className="w-full group/btn bg-gradient-to-r from-blue-600 to-[var(--color-primary)] text-white font-bold py-3.5 px-6 rounded-xl hover:shadow-xl transition-all duration-300 flex items-center justify-center gap-2"
              >
                <span>للتجار والشركات من هنا</span>
                <ArrowLeft className="w-5 h-5 group-hover/btn:-translate-x-1 transition-transform" />
              </button>
            </div>

            {/* الموظفون ومنظمو فريق كترا */}
            <div className="group p-8 bg-white/90 dark:bg-gray-800/80 backdrop-blur-sm rounded-2xl shadow-lg border border-gray-100/70 dark:border-gray-700/60 hover:shadow-xl hover:-translate-y-1 transition-all duration-300 flex flex-col">
              <div className="w-14 h-14 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-500 flex items-center justify-center mb-5 shadow-md">
                <UserCog className="w-7 h-7 text-white" />
              </div>
              <h3 className="text-xl font-bold text-gray-800 dark:text-gray-100 mb-2">للموظفين ومنظّمي فريق كترا</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed mb-6 flex-1">
                انضم إلى فريق كترا — قدّم سيرتك الذاتية وبياناتك المهنية وابدأ رحلتك المهنية معنا.
              </p>
              <button
                onClick={() => onSignup('employee')}
                className="w-full group/btn bg-gradient-to-r from-emerald-600 to-teal-500 text-white font-bold py-3.5 px-6 rounded-xl hover:shadow-xl transition-all duration-300 flex items-center justify-center gap-2"
              >
                <span>للموظفين والمنظّمين من هنا</span>
                <ArrowLeft className="w-5 h-5 group-hover/btn:-translate-x-1 transition-transform" />
              </button>
            </div>
          </div>
        </section>

        {/* ── الميزات ── */}
        <section className="mt-24">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-gray-800 dark:text-gray-100">كل ما تحتاجه شركتك في منصة واحدة</h2>
            <p className="mt-3 text-gray-600 dark:text-gray-400">من أول عرض سعر للمورِّد حتى القيد المحاسبي النهائي.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="group p-6 bg-white/90 dark:bg-gray-800/80 backdrop-blur-sm rounded-2xl shadow-lg border border-gray-100/70 dark:border-gray-700/60 hover:shadow-xl hover:-translate-y-1 transition-all duration-300"
              >
                <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-blue-600 to-[var(--color-primary)] flex items-center justify-center mb-4 shadow-md group-hover:scale-105 transition-transform">
                  <f.icon className="w-6 h-6 text-white" />
                </div>
                <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100 mb-2">{f.title}</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── مزايا تقنية ── */}
        <section className="mt-20 relative">
          <div className="relative p-8 md:p-10 bg-white/90 dark:bg-gray-800/80 backdrop-blur-sm rounded-3xl shadow-xl border border-gray-100/70 dark:border-gray-700/60">
            <div className="flex items-center gap-3 mb-6">
              <Boxes className="w-7 h-7 text-blue-600 dark:text-blue-400" />
              <h2 className="text-2xl font-bold text-gray-800 dark:text-gray-100">مبنية لتعمل في بيئتك</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              {HIGHLIGHTS.map((h) => (
                <div key={h} className="flex items-start gap-3 text-gray-700 dark:text-gray-300">
                  <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400 shrink-0 mt-0.5" />
                  <span className="text-sm leading-relaxed">{h}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── دعوة ختامية ── */}
        <section className="mt-20 text-center">
          <div className="relative inline-block w-full">
            <div className="absolute -inset-1 bg-gradient-to-r from-blue-600 to-[var(--color-primary)] rounded-3xl blur opacity-25"></div>
            <div className="relative p-10 bg-gradient-to-r from-blue-600 to-[var(--color-primary)] rounded-3xl text-white">
              <h2 className="text-2xl md:text-3xl font-bold mb-3">جاهز للبدء؟</h2>
              <p className="text-blue-100 mb-7 max-w-xl mx-auto">سجّل الدخول للوصول إلى نظامك المتكامل، أو أنشئ حساباً جديداً للانضمام.</p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                <button onClick={onLogin} className="w-full sm:w-auto bg-white text-blue-700 font-bold py-3.5 px-8 rounded-xl hover:bg-blue-50 transition-all duration-300">
                  تسجيل الدخول
                </button>
                <button onClick={scrollToPaths} className="w-full sm:w-auto bg-blue-500/30 border border-white/40 text-white font-bold py-3.5 px-8 rounded-xl hover:bg-blue-500/50 transition-all duration-300">
                  إنشاء حساب جديد
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>

      {/* ── التذييل ── */}
      <footer className="relative z-10 border-t border-gray-200/60 dark:border-gray-700/60 py-8 mt-8">
        <div className="max-w-6xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-center gap-3 text-gray-600 dark:text-gray-400 text-sm">
          <Building2 className="w-5 h-5" />
          <span>© {new Date().getFullYear()} شركة K.T.R.A للتجارة العالمية</span>
          <div className="hidden sm:block w-1 h-1 bg-gray-400 rounded-full"></div>
          <span>جميع الحقوق محفوظة | نظام إدارة متكامل</span>
        </div>
      </footer>
    </div>
  );
};
