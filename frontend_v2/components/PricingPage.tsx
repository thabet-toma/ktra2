import React from 'react';
import { Link } from 'react-router-dom';
import { Check, Sparkles } from 'lucide-react';

import { PublicNavbar } from './layout/PublicNavbar';
import { usePublicPricing } from '../hooks/usePublicPricing.ts';
import { formatNumber } from '../utils/formatNumber.ts';
import {
  buildLimitComparisonRows,
  buildModuleComparisonRows,
  formatPlanLimitValue,
} from '../utils/planPricingDisplay.ts';
import type { PublicPlan } from '../services/pricingApi.ts';

// لا مفتاح «الأكثر طلباً» في حمولة الخادم بعد — «المتقدمة» أشمل من «الأساسية»
// وأخفّ سعراً من «المتخصصة»، فهي التوازن الذي تُبرزه صفحاتُ التسعير عادةً.
// حسمها المالك رقماً لا حرفاً حين تُضاف الحقولُ لاحقاً يُلغي هذا الثابت وحده.
const HIGHLIGHTED_PLAN_KEY = 'Pro';

// أهمُّ أربعة حدودٍ تُعرَض في البطاقة المختصرة — الباقي في جدول المقارنة
// الكامل تحتها؛ لا اختيارٌ عشوائيٌّ بل ما يهمّ صاحب قرار الشراء أوّلاً.
const FEATURED_LIMIT_KEYS = ['sales.invoices', 'hr.employees', 'company.members', 'inventory.products'];

const PlanCard: React.FC<{ plan: PublicPlan; highlighted: boolean }> = ({ plan, highlighted }) => {
  const featuredLimits = plan.limits.filter((limit) => FEATURED_LIMIT_KEYS.includes(limit.key));
  return (
    <div
      className={`relative flex flex-col rounded-3xl border p-7 shadow-sm transition ${
        highlighted
          ? 'border-blue-600 bg-white shadow-xl shadow-blue-600/10 dark:border-blue-400 dark:bg-slate-900'
          : 'border-slate-200 bg-white dark:border-white/10 dark:bg-slate-900/60'
      }`}
    >
      {highlighted && (
        <span className="absolute -top-3 right-7 inline-flex items-center gap-1 rounded-full bg-blue-600 px-3 py-1 text-xs font-extrabold text-white shadow">
          <Sparkles className="h-3.5 w-3.5" />
          الأكثر طلباً
        </span>
      )}

      <h3 className="text-lg font-extrabold text-slate-900 dark:text-white">{plan.label}</h3>

      <div className="mt-4 flex items-end gap-1.5">
        <span className="text-4xl font-black text-slate-950 dark:text-white">{formatNumber(plan.price)}</span>
        <span className="pb-1 text-lg font-bold text-slate-500 dark:text-slate-400">{plan.currency_symbol}</span>
        <span className="pb-1.5 text-sm font-semibold text-slate-400 dark:text-slate-500">/ شهرياً</span>
      </div>

      <ul className="mt-6 flex-1 space-y-2.5">
        {featuredLimits.map((limit) => (
          <li key={limit.key} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <Check className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" strokeWidth={3} />
            <span>
              {limit.label}: <strong className="font-extrabold">{formatPlanLimitValue(limit.value)}</strong>
              {limit.value !== 0 && limit.value !== null ? ` ${limit.unit} ${limit.period_label}` : ''}
            </span>
          </li>
        ))}
        {/* «٠ وحدة مرخّصة» بعلامةِ صحٍّ خضراءَ تُقرأ ميزةً لا نفياً — والأساسيّةُ
            بلا وحداتٍ فعلاً. فالسطرُ يغيب حين لا وحدةَ، وجدولُ المقارنة تحته
            يقول «—» صراحةً في مكانه الصحيح. */}
        {plan.modules.length > 0 && (
          <li className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <Check className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" strokeWidth={3} />
            <span>{formatNumber(plan.modules.length, { maxDecimals: 0 })} وحدة إضافية مرخّصة لهذه الخطّة</span>
          </li>
        )}
      </ul>

      {/* لا مسار `/signup` حقيقيّ في السجلّ — `publicAuthRoutes.ts` يضمن بقاءه
          فارغاً بحارسٍ ثابت (الباب مُغلَق بقرارٍ سابق)، والتسجيلُ حالةٌ داخل
          `App.tsx` المحجوز لا رابطٌ. الوجهةُ إذاً الهبوطُ حيث زرُّ التسجيل الحقيقيّ. */}
      <Link
        to="/"
        className={`mt-7 inline-flex min-h-12 items-center justify-center rounded-xl px-5 text-sm font-extrabold transition ${
          highlighted
            ? 'bg-blue-600 text-white hover:bg-blue-700'
            : 'border border-slate-300 text-slate-800 hover:border-blue-300 hover:text-blue-700 dark:border-white/10 dark:text-slate-100 dark:hover:border-blue-400/40'
        }`}
      >
        ابدأ بهذه الخطّة
      </Link>
    </div>
  );
};

export const PricingPage: React.FC = () => {
  const { data, loading, error } = usePublicPricing();

  return (
    <div dir="rtl" className="min-h-screen bg-[#f7f9fc] font-sans text-slate-950 dark:bg-slate-950 dark:text-white">
      <PublicNavbar />

      <main className="mx-auto max-w-7xl px-5 pb-20 pt-28 sm:px-8 lg:px-10 lg:pt-36">
        <div className="mx-auto max-w-2xl text-center">
          <h1 className="text-3xl font-black tracking-tight text-slate-950 sm:text-4xl dark:text-white">خطط الأسعار</h1>
          <p className="mt-3 text-base leading-7 text-slate-600 dark:text-slate-300">
            اختر الخطّة التي تناسب حجم عملك — الأسعار والحدود هنا هي نفسها المطبَّقة فعلياً على حسابك.
          </p>
        </div>

        {loading && (
          <p className="mt-16 text-center text-sm font-semibold text-slate-500 dark:text-slate-400">جاري تحميل الخطط...</p>
        )}

        {!loading && error && (
          <p role="alert" className="mt-16 text-center text-sm font-semibold text-red-700 dark:text-red-300">{error}</p>
        )}

        {!loading && !error && data && (
          <>
            <div className="mt-12 grid gap-6 md:grid-cols-3">
              {data.plans.map((plan) => (
                <PlanCard key={plan.key} plan={plan} highlighted={plan.key === HIGHLIGHTED_PLAN_KEY} />
              ))}
            </div>

            <div className="mt-8 flex flex-col items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-6 text-center sm:flex-row sm:text-right dark:border-white/10 dark:bg-slate-900/60">
              <div>
                <p className="text-sm font-extrabold text-blue-600 dark:text-blue-400">إضافة على أيّ خطّة</p>
                <h2 className="mt-1 text-xl font-black text-slate-950 dark:text-white">{data.data_entry_addon.label}</h2>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                  {formatNumber(data.data_entry_addon.included_operations)} عمليّة مضمَّنة
                  {data.data_entry_addon.extra_operation_price !== null && (
                    <> — {formatNumber(data.data_entry_addon.extra_operation_price)} {data.plans[0]?.currency_symbol ?? '₪'} لكل عمليّة إضافية</>
                  )}
                </p>
              </div>
              <div className="flex items-end gap-1.5">
                <span className="text-3xl font-black text-slate-950 dark:text-white">{formatNumber(data.data_entry_addon.price)}</span>
                <span className="pb-1 text-base font-bold text-slate-500 dark:text-slate-400">{data.plans[0]?.currency_symbol ?? '₪'}</span>
                <span className="pb-1.5 text-sm font-semibold text-slate-400 dark:text-slate-500">/ شهرياً</span>
              </div>
            </div>

            <div className="mt-14">
              <h2 className="text-xl font-extrabold text-slate-950 dark:text-white">مقارنة كاملة بين الخطط</h2>
              <div className="mt-5 overflow-x-auto rounded-2xl border border-slate-200 dark:border-white/10">
                <table className="w-full min-w-[640px] border-collapse text-right text-sm">
                  <thead className="bg-slate-50 dark:bg-white/5">
                    <tr>
                      <th className="p-4 font-extrabold text-slate-700 dark:text-slate-200">المزايا</th>
                      {data.plans.map((plan) => (
                        <th key={plan.key} className="p-4 text-center font-extrabold text-slate-700 dark:text-slate-200">{plan.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {buildLimitComparisonRows(data.plans).map((row) => (
                      <tr key={row.key} className="border-t border-slate-100 dark:border-white/5">
                        <td className="p-4 font-semibold text-slate-700 dark:text-slate-300">{row.label} ({row.periodLabel})</td>
                        {data.plans.map((plan) => (
                          <td key={plan.key} className="p-4 text-center text-slate-600 dark:text-slate-400">
                            {formatPlanLimitValue(row.valuesByPlan[plan.key])}
                          </td>
                        ))}
                      </tr>
                    ))}
                    {buildModuleComparisonRows(data.plans).map((row) => (
                      <tr key={row.key} className="border-t border-slate-100 dark:border-white/5">
                        <td className="p-4 font-semibold text-slate-700 dark:text-slate-300">{row.label}</td>
                        {data.plans.map((plan) => (
                          <td key={plan.key} className="p-4 text-center">
                            {row.enabledByPlan[plan.key] ? (
                              <Check className="mx-auto h-4 w-4 text-emerald-600 dark:text-emerald-400" strokeWidth={3} />
                            ) : (
                              <span className="text-slate-300 dark:text-slate-600">—</span>
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
};

export default PricingPage;
