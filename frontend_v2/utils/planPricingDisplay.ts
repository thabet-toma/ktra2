/**
 * 211-N/O: دوالٌ خالصةٌ لعرض حدود الخطط — لا منطق حسابيّ داخل `useMemo` لا يراه
 * شيء. الحدّ الثلاثيّ المعاني (`core/plans.py`): عددٌ = الحدّ · `null` = بلا
 * حدّ · `0` = غير متاح. خلط `null` بالصفر يقلب «بلا سقف» إلى «ممنوع».
 */
import { formatNumber } from './formatNumber.ts';
import type { PublicPlan } from '../services/pricingApi.ts';

export function formatPlanLimitValue(value: number | null): string {
  if (value === null) return 'بلا حدّ';
  if (value === 0) return 'غير متاح';
  return formatNumber(value, { maxDecimals: 0, group: true });
}

export interface LimitComparisonRow {
  key: string;
  label: string;
  unit: string;
  periodLabel: string;
  valuesByPlan: Record<string, number | null>;
}

export interface ModuleComparisonRow {
  key: string;
  label: string;
  enabledByPlan: Record<string, boolean>;
}

/**
 * صفٌّ لكلّ حدّ: كلّ الخطط تحمل مفاتيحَ الحدود نفسَها بالترتيب نفسِه
 * (`public_plan_rows` تبنيها من `LIMITS` الواحدة لكلّ خطّة) — فمرجعُ الأعمدة
 * أوّل خطّةٍ وحدها، لا اتّحادٌ يُحسب.
 */
export function buildLimitComparisonRows(plans: PublicPlan[]): LimitComparisonRow[] {
  const base = plans[0]?.limits ?? [];
  return base.map((limit) => ({
    key: limit.key,
    label: limit.label,
    unit: limit.unit,
    periodLabel: limit.period_label,
    valuesByPlan: Object.fromEntries(
      plans.map((plan) => [plan.key, plan.limits.find((l) => l.key === limit.key)?.value ?? null]),
    ),
  }));
}

/**
 * صفٌّ لكلّ وحدة: كلّ خطّةٍ تحمل مفاتيحها المرخَّصة **وحدها** (`modules` في
 * الحمولة لا تذكر ما هو مقفلٌ)، فصفوفُ الجدول اتّحادُ المفاتيح عبر الخطط الثلاث
 * — لا مرجعَ واحداً.
 */
export function buildModuleComparisonRows(plans: PublicPlan[]): ModuleComparisonRow[] {
  const labelByKey = new Map<string, string>();
  const order: string[] = [];
  for (const plan of plans) {
    for (const module of plan.modules) {
      if (!labelByKey.has(module.key)) {
        labelByKey.set(module.key, module.label);
        order.push(module.key);
      }
    }
  }
  return order.map((key) => ({
    key,
    label: labelByKey.get(key) as string,
    enabledByPlan: Object.fromEntries(
      plans.map((plan) => [plan.key, plan.modules.some((m) => m.key === key)]),
    ),
  }));
}

/**
 * حالةُ شريط الاستهلاك لحدٍّ واحد. `percent` مقصوصةٌ في [0,100] لرسم الشريط،
 * و`rawPercent` تحمل الفائضَ كما هو.
 */
export interface PlanUsageBar {
  /** `true` حين لا شريطَ يُرسم أصلاً: بلا حدّ، أو غير متاح. */
  unbounded: boolean;
  unavailable: boolean;
  percent: number;
  rawPercent: number;
  /** `warning` من 80%، و`over` عند بلوغ الحدّ أو تجاوزه. */
  tone: 'ok' | 'warning' | 'over';
  remaining: number | null;
}

/**
 * شريطُ استهلاكٍ واحد — دالّةٌ خالصةٌ لأنّ `npm test` هنا لا يُصيّر مكوّناً:
 * منطقٌ داخل `useMemo` في البطاقة لا يفحصه شيء، والأرقامُ المعروضة هنا هي التي
 * يقرؤها المستخدمُ قبل أن يُمنَع من الإنشاء.
 *
 * ثلاثةُ قراراتٍ مقصودة:
 * - **`null` بلا حدّ و`0` غير متاح** — نفسُ الثلاثيّة في `core/plans.py`؛ قسمةٌ
 *   على أيٍّ منهما تُنتج `Infinity` أو `NaN` فيُرسم شريطٌ بلا معنى.
 * - **الفائقُ يُقصّ في الشريط لا في الرقم.** بلوغُ 320 من 200 (حدٌّ خُفّض بعد
 *   الاستهلاك) يبقى «320 من 200» في النصّ وشريطاً ممتلئاً — لا 100% تُقرأ
 *   «على الحدّ تماماً».
 * - **`remaining` لا تنزل تحت الصفر** — «بقي لك -120» ليس رقماً يُقرأ.
 */
export function buildPlanUsageBar(usage: number, limit: number | null): PlanUsageBar {
  if (limit === null) {
    return { unbounded: true, unavailable: false, percent: 0, rawPercent: 0, tone: 'ok', remaining: null };
  }
  if (limit === 0) {
    return { unbounded: false, unavailable: true, percent: 0, rawPercent: 0, tone: 'over', remaining: 0 };
  }
  const rawPercent = (usage / limit) * 100;
  const percent = Math.max(0, Math.min(100, rawPercent));
  const tone: PlanUsageBar['tone'] = rawPercent >= 100 ? 'over' : rawPercent >= 80 ? 'warning' : 'ok';
  return {
    unbounded: false,
    unavailable: false,
    percent,
    rawPercent,
    tone,
    remaining: Math.max(0, limit - usage),
  };
}
