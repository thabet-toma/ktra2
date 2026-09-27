/**
 * SA-5/SA-6 — حسابات لوحة المنصة الخالصة (بلا React ولا شبكة) كي يختبرها `npm test`:
 * الإيراد الشهري المتوقَّع، وفلترة جدول الشركات وترتيبه.
 */

/** «تنتهي قريباً» = باقٍ هذا العدد من الأيام أو أقل (أو انتهت). */
export const TRIAL_WARNING_DAYS = 7;
export const IDLE_DAYS = 30;

export interface ConsoleCompanyRow {
  id: number;
  name: string;
  plan: string;
  status: string;
  subscription_days_left: number | null;
  last_activity_at: string | null;
  near_limit: unknown[];
  created_at: string;
}

export interface ConsoleUsage {
  documents_total: number;
  documents_month: number;
  movements_total: number;
  movements_month: number;
}

export interface PlanPrice {
  plan_key: string;
  effective_price: string | number;
}

/**
 * الإيراد الشهري **المتوقَّع**: كل شركة فعّالة × السعر الفعّال لخطتها. التجريبية
 * والموقوفة صفر، وخطةٌ بلا سعر (التجريبية) صفر — تقديرٌ من الأسعار لا تحصيلٌ فعلي.
 */
export function expectedMrr(rows: Pick<ConsoleCompanyRow, "plan" | "status">[], pricing: PlanPrice[]): number {
  const price = new Map(pricing.map((row) => [row.plan_key, Number(row.effective_price) || 0]));
  return rows.reduce((sum, row) => (row.status === "Active" ? sum + (price.get(row.plan) ?? 0) : sum), 0);
}

export type CompanyFlag = "" | "idle" | "near" | "ending";
export type CompanySort = "created" | "name" | "documents" | "movements" | "activity";

export interface CompanyFilter {
  q: string;
  status: string;
  plan: string;
  flag: CompanyFlag;
  sort: CompanySort;
}

export const EMPTY_COMPANY_FILTER: CompanyFilter = { q: "", status: "", plan: "", flag: "", sort: "created" };

export function isIdle(row: Pick<ConsoleCompanyRow, "last_activity_at">, now: number): boolean {
  if (!row.last_activity_at) return true;
  return now - Date.parse(row.last_activity_at) > IDLE_DAYS * 86_400_000;
}

/** الموقوفة لا تُعدّ «تنتهي قريباً» — قرارها اتُّخذ. */
export function isEnding(row: Pick<ConsoleCompanyRow, "subscription_days_left" | "status">): boolean {
  return row.subscription_days_left !== null && row.subscription_days_left <= TRIAL_WARNING_DAYS
    && row.status !== "Suspended";
}

const time = (value: string | null) => (value ? Date.parse(value) || 0 : 0);

export function filterCompanies<T extends ConsoleCompanyRow>(
  rows: T[],
  usage: Map<number, ConsoleUsage>,
  filter: CompanyFilter,
  now: number = Date.now(),
): T[] {
  const needle = filter.q.trim().toLowerCase();
  const result = rows.filter((row) => {
    if (needle && !row.name.toLowerCase().includes(needle) && String(row.id) !== needle) return false;
    if (filter.status && row.status !== filter.status) return false;
    if (filter.plan && row.plan !== filter.plan) return false;
    if (filter.flag === "idle" && !isIdle(row, now)) return false;
    if (filter.flag === "near" && row.near_limit.length === 0) return false;
    if (filter.flag === "ending" && !isEnding(row)) return false;
    return true;
  });
  const metric = (row: T, key: "documents_total" | "movements_total") => usage.get(row.id)?.[key] ?? 0;
  const sorters: Record<CompanySort, (a: T, b: T) => number> = {
    created: (a, b) => time(b.created_at) - time(a.created_at),
    name: (a, b) => a.name.localeCompare(b.name, "ar"),
    documents: (a, b) => metric(b, "documents_total") - metric(a, "documents_total"),
    movements: (a, b) => metric(b, "movements_total") - metric(a, "movements_total"),
    activity: (a, b) => time(b.last_activity_at) - time(a.last_activity_at),
  };
  return [...result].sort(sorters[filter.sort] ?? sorters.created);
}

const FLAGS: CompanyFlag[] = ["idle", "near", "ending"];
const SORTS: CompanySort[] = ["name", "documents", "movements", "activity"];

/** يقرأ الفلتر من `?status=&plan=&filter=&sort=&q=` — روابط بطاقات «نظرة عامة». */
export function filterFromSearch(search: string): CompanyFilter {
  const params = new URLSearchParams(search);
  const flag = params.get("filter") ?? "";
  const sort = params.get("sort") ?? "";
  return {
    q: params.get("q") ?? "",
    status: params.get("status") ?? "",
    plan: params.get("plan") ?? "",
    flag: FLAGS.includes(flag as CompanyFlag) ? (flag as CompanyFlag) : "",
    sort: SORTS.includes(sort as CompanySort) ? (sort as CompanySort) : "created",
  };
}
