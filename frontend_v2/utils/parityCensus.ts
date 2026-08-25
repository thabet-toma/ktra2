/**
 * منطق حارس التكافؤ — نقيّ بلا DOM ولا Playwright.
 *
 * الحارس (`e2e/feature-parity-census.spec.ts`) يمرّ على كل شاشة فيحصي أزرارها
 * وحقولها وتبويباتها ورؤوس جداولها، ثم يقارن الحصيلة بخط أساس مسجَّل:
 * **النقصان فشل، والزيادة تحذير**. جمعُ الحصيلة يلزمه متصفّح، أما **الحكم**
 * فحسابٌ صرف — فأُخرج إلى هنا ليُختبر في أجزاء الثانية بدل ثلاث عشرة دقيقة.
 *
 * لماذا يهمّ: الحارس هو ما يجعل إعادة تسمية آلاف المواضع عمليةً لا مقامرة، ومن
 * لا يستطيع أن يُثبت أن حارسه **يحمرّ** حين يسقط زرّ، لا يملك حارساً بل طمأنينة.
 * الاختبار المرافق يُثبت الحمرة والخضرة معاً بلا تشغيل الحزمة كلها.
 */

export type CensusCategory = {
  count: number;
  values: string[];
};

export const CENSUS_CATEGORIES = [
  "buttons",
  "fields",
  "tabs",
  "tableHeaders",
  "toolbarItems",
] as const;

export type CensusCategoryName = (typeof CENSUS_CATEGORIES)[number];

export type ViewCensus = { path: string } & Record<CensusCategoryName, CensusCategory>;

export type ParityBaseline = {
  schemaVersion: 1;
  viewport: { width: 1440; height: 900 };
  views: Record<string, ViewCensus>;
  skipped: Record<string, string>;
};

/** يوحّد المسافات ويُسقط الأطراف — نصّ DOM لا يُقارَن خاماً. */
export const normalise = (value: string | null | undefined): string =>
  (value ?? "").replace(/\s+/g, " ").trim();

/** فئة مفروزة بترتيب عربي مستقرّ — لتخرج نفس النتيجة من تشغيلين متتاليين. */
export const toCategory = (values: string[]): CensusCategory => {
  const sorted = values.map(normalise).sort((a, b) => a.localeCompare(b, "ar"));
  return { count: sorted.length, values: sorted };
};

/**
 * ما في `baseline` ولا يقابله مثيلٌ في `current` — **بحساب التكرار**: عمودان
 * بنفس العنوان يلزمهما عمودان، فسقوط أحدهما نقصان.
 */
export function missingValues(baseline: string[], current: string[]): string[] {
  const available = new Map<string, number>();
  for (const value of current) available.set(value, (available.get(value) ?? 0) + 1);

  const missing: string[] = [];
  for (const value of baseline) {
    const count = available.get(value) ?? 0;
    if (count > 0) available.set(value, count - 1);
    else missing.push(value);
  }
  return missing;
}

export type ComparisonResult = {
  /** النقصان — كلٌّ منها يُفشل الحارس. */
  failures: string[];
  /** الزيادة — تُطبع تحذيراً ولا تُفشل: الميزة الجديدة ليست عطلاً. */
  additions: string[];
};

/** يقارن حصيلةً جديدة بخط الأساس ويفصل النقصان عن الزيادة. */
export function compareBaselines(
  baseline: ParityBaseline,
  current: ParityBaseline,
): ComparisonResult {
  const failures: string[] = [];
  const additions: string[] = [];

  for (const [view, expectedView] of Object.entries(baseline.views)) {
    const actualView = current.views[view];
    if (!actualView) {
      failures.push(`${view}: entire view census is missing`);
      continue;
    }

    for (const category of CENSUS_CATEGORIES) {
      const missing = missingValues(expectedView[category].values, actualView[category].values);
      if (missing.length > 0) {
        failures.push(
          `${view}.${category}: missing ${missing.map((value) => JSON.stringify(value)).join(", ")}`,
        );
      }

      const added = missingValues(actualView[category].values, expectedView[category].values);
      if (added.length > 0) {
        additions.push(
          `${view}.${category}: new ${added.map((value) => JSON.stringify(value)).join(", ")}`,
        );
      }
    }
  }

  for (const view of Object.keys(current.views)) {
    if (!baseline.views[view]) additions.push(`${view}: new view census`);
  }

  return { failures, additions };
}

/** ترتيبٌ ثابت للمفاتيح — بدونه يختلف الملفّ المكتوب بين تشغيلين بلا سبب. */
export function sortedBaseline(baseline: ParityBaseline): ParityBaseline {
  return {
    ...baseline,
    views: Object.fromEntries(Object.entries(baseline.views).sort(([a], [b]) => a.localeCompare(b))),
    skipped: Object.fromEntries(
      Object.entries(baseline.skipped).sort(([a], [b]) => a.localeCompare(b)),
    ),
  };
}
