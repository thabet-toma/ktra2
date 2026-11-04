/**
 * ISSUE #271 — دوالُّ خالصة لموديول مكتب المحاسبة.
 *
 * **لا تسميةَ في هذا الملف.** كلُّ نصٍّ يعرضه الموديول يأتي من الخادم:
 * `status_label` و`language_label` و`label` (نوع التذكير) وتسميةُ قيمة الإعداد
 * (`value_label`) واختياراتُه (`choices`، ومنها أيام الأسبوع). نسخةٌ هنا تعني
 * مصطلحين لشيءٍ واحد يفترقان عند أول تعديل في السجلّ. والاستثناءُ الوحيدُ
 * المعلَن: «مالك» تسميةُ `manager` في قسم أدوار المكتب وحده (`OFFICE_OWNER_ROLE_LABEL`)
 * — صرّح بها القرارُ المحسوم في #272، ومصدرُ باقي أسماء الأدوار يبقى الخادم.
 *
 * الباقي هنا **منطقٌ حقيقيّ**: ما يُعرض لزبونٍ إسرائيليّ، واشتقاقُ «مخصَّص»،
 * وقراءةُ معرّف الزبون من العنوان وبناءُ رابطه، وما يخفيه حجمُ المكتب «شخص واحد»،
 * وقناعُ المبلغ المخفيّ. صرفةٌ بلا React كي تُختبر بـ`node --test` في بوّابة
 * `npm test`.
 */
import { monthKeyLabel, monthKeyOf, shiftMonthKey } from './monthKey.ts';
import { userRoleLabel } from './userRoleLabel.ts';

/** مسار شاشة الزبائن — مصدرٌ واحدٌ للرابط وقراءته. */
export const OFFICE_CLIENTS_PATH = '/accounting-office/clients';

/** مسار شاشة إعدادات المكتب — بجانب مسار الزبائن، مصدرٌ واحدٌ لجدول المسارات. */
export const OFFICE_SETTINGS_PATH = '/accounting-office/settings';

/** مسار شاشة التقويم (#274) — بجانبهما، ومصدرٌ واحدٌ للموجّه والقائمة. */
export const OFFICE_CALENDAR_PATH = '/accounting-office/calendar';

/** اسم معامل العنوان الذي يحمل معرّف الزبون المفتوح. */
export const CLIENT_QUERY_PARAM = 'client';

/** مفتاح حجم المكتب في سجلّ الإعدادات — يُقرأ كما يرسله الخادم. */
export const OFFICE_SIZE_KEY = 'office_size';
/** «شخص واحد»: لا أدوار، ولا إسناد، ولا عمودَ موظفٍ في الشاشات. */
export const OFFICE_SIZE_SOLO = 'solo';
/** «كبير»: الوحيد الذي يعرض دور القارئ في قسم أدوار المكتب. */
export const OFFICE_SIZE_LARGE = 'large';

/**
 * دورُ مالك المكتب — هو الدور القائم `manager` نفسه لا دوراً ثانياً.
 *
 * وتسميتُه في قسم أدوار المكتب **«مالك»** لأن «مدير» هناك تعني `office_manager`.
 * وهي التسميةُ المحلّيةُ الوحيدة في هذا الملفّ: `ROLE_LABELS` في الخادم تسمّي
 * `manager` «مدير» لكلّ الشاشات، وتغييرُها من أجله يبدّل اسمَ المالك في كل مكان.
 */
export const OFFICE_OWNER_ROLE = 'manager';
export const OFFICE_OWNER_ROLE_LABEL = 'مالك';

/** أدوارُ قسم «الموظفون والأدوار» — أربعة، والقارئ في المكتب الكبير وحده. */
export const OFFICE_ROLE_KEYS: readonly string[] = [
  'manager', 'office_manager', 'accountant', 'viewer',
];

/** بديلُ المبلغ المخفيّ: الخادم يرسل `null` والشاشة تعرض هذا — لا صفراً. */
export const AMOUNT_MASK = '—';

export interface SettingChoice {
  value: string;
  label: string;
}

export interface SettingRow {
  key: string;
  label: string;
  /** تسميةُ الإعداد من منظور الزبون حين تختلف (أيام عطلة المكتب ← يوم راحة الزبون). */
  client_label?: string;
  kind: string;
  levels: readonly string[];
  group?: string;
  note?: string;
  choices: readonly SettingChoice[];
  has_default: boolean;
  default: unknown;
  value: unknown;
  /** نصُّ القيمة كما يُعرض — يبنيه الخادم من السجلّ. */
  value_label?: string;
  source?: string | null;
  is_customized?: boolean;
  office_value?: unknown;
  has_office_value?: boolean;
  differs_from_default?: boolean;
  can_reset?: boolean;
  client_customization_count?: number;
}

/**
 * إعدادات البطاقة التي تُعرض لهذا الزبون.
 *
 * `filing_method` معناه في إسرائيل (19/23): عرضُه لزبونٍ فلسطينيّ يُغرِق الشاشة
 * بإعدادٍ لا أثر له في نظامه. والباقي يظهر دائماً — وقيمتُه الموروثة صحيحة،
 * فلا معنى لإخفاء إعدادٍ لأن المكتب لم يخصّصه.
 */
export function visibleClientSettings(
  settings: readonly SettingRow[],
  taxSystem: string | null | undefined,
): SettingRow[] {
  return settings.filter(
    (setting) => setting.key !== 'filing_method' || taxSystem === 'IL',
  );
}

/** عددُ الإعدادات المخصَّصة لهذا الزبون — يُعرض في رأس الملف. */
export function customizedSettingCount(settings: readonly SettingRow[]): number {
  return settings.filter((setting) => setting.is_customized === true).length;
}

/** أسماءُ مفاتيح أول تشغيل الناقصة — بالعربية، من السجلّ لا من قائمةٍ محليّة. */
export function missingFirstRunLabels(
  missingKeys: readonly string[],
  settings: readonly SettingRow[],
): string[] {
  return missingKeys.map((key) => {
    const match = settings.find((setting) => setting.key === key);
    return match ? match.label : key;
  });
}

/**
 * معرّفُ الزبون المفتوح من نصّ العنوان — `null` حين لا معرّف أو كان فاسداً.
 *
 * الفسادُ (سالب، صفر، نصّ) لا يُرمى به: الشاشةُ تعود إلى القائمة بدل أن تنكسر
 * على رابطٍ قديمٍ أو معدَّلٍ يدوياً.
 */
export function clientIdFromSearch(search: string): number | null {
  const params = new URLSearchParams(search.startsWith('?') ? search : `?${search}`);
  const raw = params.get(CLIENT_QUERY_PARAM);
  if (raw === null) return null;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

/** رابطُ شاشة الزبائن، بملفّ زبونٍ مفتوحٍ أو بلا. */
export function clientFilePath(clientId?: number | null): string {
  if (clientId === null || clientId === undefined) return OFFICE_CLIENTS_PATH;
  return `${OFFICE_CLIENTS_PATH}?${CLIENT_QUERY_PARAM}=${clientId}`;
}

/** أصناف Tailwind لشارة الحالة — عرضٌ لا نصّ: النصُّ يصل من `status_label`. */
export function clientStatusBadgeClass(status: string): string {
  if (status === 'active') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300';
  }
  if (status === 'ended') {
    return 'border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400';
  }
  return 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300';
}

/** حجمُ المكتب من سطر إعداده — `null` ما دام غير مختار. */
export function officeSizeOf(settings: readonly SettingRow[]): string | null {
  const setting = settings.find((row) => row.key === OFFICE_SIZE_KEY);
  const value = setting?.value;
  return typeof value === 'string' && value !== '' ? value : null;
}

/**
 * هل يُعرض الإسناد في هذه الشاشة؟ «شخص واحد» يخفي عمود المسؤول وزرّ «حوّل»
 * وقسم الأدوار. والحكمُ في الخادم يبقى للصلاحيات وحدها — هذا عرضٌ لا إنفاذ،
 * وحجمٌ غير معروف لا يُخفي شيئاً.
 */
export function showsOfficeAssignment(officeSize: string | null | undefined): boolean {
  return officeSize !== OFFICE_SIZE_SOLO;
}

/** المبلغ كما يُعرض: المخفيُّ «—» — ولا صفرَ مكانه ولا فراغاً يُقرأ خطأً. */
export function formatOfficeAmount(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return AMOUNT_MASK;
  return String(value);
}

/** تسميةُ الدور في قسم أدوار المكتب — و«مالك» لصاحب المكتب وحده. */
export function officeRoleLabel(role: string, serverLabel: string): string {
  return role === OFFICE_OWNER_ROLE ? OFFICE_OWNER_ROLE_LABEL : serverLabel;
}

// ── الخدمات والباقات (#273) ─────────────────────────────────────────────
//
// **ولا تسميةَ دوريةٍ هنا**: أسماءُ الدوريات وحالاتِ الخدمة تصل من الخادم
// (`frequency_label` · `status_label` · `frequency_choices`)، والثواني في هذا
// الملفّ منطقٌ لا نصوص: أولُ الشهر، وما يتاح لمنتقي الإضافة، وملخّصُ الباقة.

/** سطرُ كتالوج خدمة — كما يعيده الخادم. */
export interface OfficeServiceRow {
  id: number;
  code: string;
  name: string;
  is_active: boolean;
  is_builtin: boolean;
  position: number;
}

/** باقةٌ جاهزة — `suggested_price` نصٌّ عشريّ أو `null` بلا رؤية مبالغ. */
export interface ServicePackageRow {
  id: number;
  name: string;
  suggested_price: string | null;
  services: OfficeServiceRow[];
  created_at: string;
  updated_at: string;
}

/** صفُّ دوريةٍ مؤرَّخ — تاريخٌ لكل تغيير، ولا يُعدَّل ما قبله. */
export interface ClientServiceFrequencyRow {
  id: number;
  frequency: string;
  frequency_label: string;
  effective_from: string;
  suggested: string | null;
  created_by_name: string;
  created_at: string;
}

/** خدمةُ زبون: تواريخُها وحالتُها ودوريتُها اليوم وتاريخُ دورياتها. */
export interface ClientServiceRow {
  id: number;
  service: OfficeServiceRow;
  starts_on: string;
  ends_on: string | null;
  responsible_from: string;
  is_active: boolean;
  status: string;
  status_label: string;
  frequency: string | null;
  frequency_label: string;
  frequency_from: string | null;
  frequencies: ClientServiceFrequencyRow[];
}

export interface ClientServicesPayload {
  client: number;
  today: string;
  services: ClientServiceRow[];
  frequency_choices: SettingChoice[];
}

/** اقتراحُ الدورية وسببُه — السببُ نصٌّ بلا أرقام مبالغ. */
export interface ServiceSuggestion {
  service: string;
  service_id: number;
  service_name: string;
  on: string;
  frequency: string | null;
  frequency_label: string;
  reason: string;
  frequency_choices: SettingChoice[];
}

export interface ApplyPackageResult {
  added: {
    service_id: number;
    service_name: string;
    client_service_id: number;
    frequency: string;
  }[];
  skipped: { service_id: number; service_name: string; reason: string }[];
}

/**
 * أولُ يومٍ في شهر تاريخٍ ما — افتراضُ «من أيّ فترةٍ المكتب مسؤول».
 *
 * التاريخُ نصٌّ ISO من الخادم أو من `input[type=date]`، فلا كائنَ `Date` ولا
 * انزياحَ منطقةٍ زمنيّة: `2026-04-30T23:00-05:00` يبقى نيسان. وسطرٌ فارغ أو
 * غير مؤرَّخ يعيد `''` — لا تاريخَ مخترعاً يُحفظ بلا أن يراه الموظف.
 */
export function firstOfMonth(day: string): string {
  const match = /^(\d{4})-(\d{2})/.exec(day ?? '');
  return match ? `${match[1]}-${match[2]}-01` : '';
}

/**
 * أولُ يومٍ في الشهر **التالي** — افتراضُ «سارية من» عند تغيير الدورية.
 *
 * اليومُ يرفضه الخادم لخدمةٍ أُضيفت اليوم (تاريخُ سريانٍ مسجَّل)، والشهرُ القادم
 * أولُ تاريخٍ صالحٍ دائماً. والسطرُ غيرُ المؤرَّخ يعيد `''` كـ`firstOfMonth`.
 */
export function firstOfNextMonth(day: string): string {
  const first = firstOfMonth(day);
  if (!first) return '';
  const [year, month] = first.split('-').map(Number);
  if (month === 12) return `${year + 1}-01-01`;
  return `${year}-${String(month + 1).padStart(2, '0')}-01`;
}

/**
 * ما يُعرض في منتقي «أضف خدمة»: خدماتُ الكتالوج **المفعّلة** التي ليست **نشطةً**
 * عند الزبون. والمعطَّلةُ لا تُضاف، والموقوفةُ تُعرض لإعادة الإضافة بعد إيقافها.
 */
export function availableServicesForClient(
  catalog: readonly OfficeServiceRow[],
  services: readonly { service: { id: number }; is_active: boolean }[],
): OfficeServiceRow[] {
  const activeIds = new Set(
    services.filter((row) => row.is_active).map((row) => row.service.id),
  );
  return catalog.filter((row) => row.is_active && !activeIds.has(row.id));
}

/** تسميةُ قيمة دورية من **اختيارات الخادم** — لا جدولَ تسمياتٍ محليّاً. */
export function frequencyLabelFrom(
  choices: readonly SettingChoice[],
  value: string | null | undefined,
): string {
  if (!value) return '';
  return choices.find((choice) => choice.value === value)?.label ?? value;
}

/** أصناف Tailwind لشارة حالة خدمة الزبون — العرضُ وحده، والنصُّ من `status_label`. */
export function clientServiceStatusClass(status: string): string {
  if (status === 'active') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300';
  }
  if (status === 'stopped') {
    return 'border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400';
  }
  return 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300';
}

/**
 * الدوريةُ في مسوّدة «أضف خدمة» بعد وصول مقترحٍ جديد: ما اختاره الموظفُ بيده
 * (`frequencyTouched`) لا يُكتب فوقه، وإلا أخذ المقترحَ (أو فراغاً إن لم يوجد).
 */
export function frequencyAfterSuggestion(
  draft: { frequency: string; frequencyTouched: boolean },
  suggested: string | null | undefined,
): string {
  return draft.frequencyTouched ? draft.frequency : (suggested ?? '');
}

/**
 * ملخّصُ «طبّق باقة» كما يُعرض في التنبيه — بأسماء الخادم لا بمعرّفات.
 * وتُخطّي الخدمةِ سببٌ يرسله الخادم، فيُعرض نصُّه كما وصل بجانب الاسم
 * «<الاسم> (<السبب>)» ولا يُعاد بناؤه هنا.
 */
export function applyPackageSummary(result: ApplyPackageResult): string {
  const added = result.added.map((row) => row.service_name).join('، ');
  const skipped = result.skipped
    .map((row) => (row.reason ? `${row.service_name} (${row.reason})` : row.service_name))
    .join('، ');
  if (!result.added.length && !result.skipped.length) {
    return 'لم تُضف شيئاً — لا خدمةَ مفعّلةً في هذه الباقة';
  }
  const parts: string[] = [];
  if (result.added.length) parts.push(`أُضيفت ${result.added.length}: ${added}`);
  if (result.skipped.length) parts.push(`تُخطّي ${result.skipped.length}: ${skipped}`);
  return parts.join(' · ');
}

/**
 * خياراتُ إسناد الدور في قسم «الموظفون والأدوار».
 *
 * **المفاتيحُ الأربعة قرارُ المكتب في هذا الملفّ** (`OFFICE_ROLE_KEYS`:
 * `manager` · `office_manager` · `accountant` · `viewer`)، و**التسمياتُ من
 * الخادم** (`roles` من `/api/permissions/roles/`) — لا نُصدر أسماءً محليّة.
 * و`viewer` في المكتب **الكبير** وحده. و«شخص واحد» لا قسمَ أدوارٍ فيه أصلاً
 * فتُرجَع قائمةٌ فارغة. والدورُ الحاليّ خارج الأربعة يُضاف أوّلاً كي لا يكذب
 * المنتقي على صاحبه.
 */
export function officeAssignableRoles(
  roles: readonly { key: string; label: string }[],
  officeSize: string | null | undefined,
  currentRole?: string | null,
): { key: string; label: string }[] {
  if (!showsOfficeAssignment(officeSize)) return [];
  const byKey = new Map(roles.map((role) => [role.key, role]));
  const options = OFFICE_ROLE_KEYS
    .filter((key) => key !== 'viewer' || officeSize === OFFICE_SIZE_LARGE)
    .filter((key) => byKey.has(key))
    .map((key) => ({ key, label: officeRoleLabel(key, byKey.get(key)!.label) }));
  if (currentRole && !options.some((option) => option.key === currentRole)) {
    const current = byKey.get(currentRole);
    options.unshift({
      key: currentRole,
      label: officeRoleLabel(currentRole, current ? current.label : userRoleLabel(currentRole)),
    });
  }
  return options;
}

// ── التقويم (#274) ──────────────────────────────────────────────────────
//
// **ولا تسميةَ قانونية هنا**: اسمُ السطر والتنبيهات وتسميةُ الفترة تأتي من
// الخادم (`name` · `warnings` · `period_label`) — الشاشة ترسمها كما وصلت.
// والباقي **حسابُ تقويمٍ** لا قانون: شبكةُ الشهر، ومدى الأسبوع، وتجميعُ العناصر
// على أيامها. والتواريخُ نصوصٌ ISO بلا كائن `Date` منطقةً زمنية (`firstOfMonth`
// نفسه): `2026-04-30T23:00-05:00` يبقى نيسان.

const MS_PER_DAY = 86_400_000;
const DAYS_PER_WEEK = 7;

/** صفُّ تقويم كما يعيده الخادم — بلا أيّ مبلغ. */
export interface CalendarDeadlineRow {
  client: { id: number; name: string };
  service: { code: string; name: string };
  rule: { code: string; name: string; needs_review: boolean };
  period_start: string;
  period_end: string;
  period_label: string;
  legal_date: string;
  official_date: string;
  actual_deadline: string;
  internal_deadline: string;
  estimated: boolean;
  postponed: boolean;
  warnings: string[];
  expected: boolean;
}

export interface CalendarPayload {
  from: string;
  to: string;
  today: string;
  rows: CalendarDeadlineRow[];
}

/** خليّةُ يومٍ في شبكة الشهر — الأيامُ من الشهرين المجاورين تُعرض باهتةً لا تُحذف. */
export interface CalendarDay {
  date: string;
  inMonth: boolean;
}

/** سطرُ لائحة المواعيد — لفلتر «النوع» ولعرض اللائحة. */
export interface DeadlineRuleRow {
  code: string;
  name: string;
  service_code: string;
  is_generated: boolean;
  needs_review: boolean;
  year: number;
  version: number;
  source_url: string;
}

const pad2 = (value: number) => String(value).padStart(2, '0');

const isoFromMs = (ms: number): string => {
  const day = new Date(ms);
  return `${day.getUTCFullYear()}-${pad2(day.getUTCMonth() + 1)}-${pad2(day.getUTCDate())}`;
};

const msFromIso = (iso: string): number | null => {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  if (!match) return null;
  const [, year, month, day] = match;
  return Date.UTC(Number(year), Number(month) - 1, Number(day));
};

/**
 * شبكةُ الشهر: أسابيعٌ تبدأ **بالأحد**، كلٌّ سبعةُ أيام، والأطرافُ من الشهرين
 * المجاورين بعلامة `inMonth: false`.
 *
 * `monthKey` نصٌّ `YYYY-MM` (كما في `utils/monthKey.ts`)؛ ومفتاحٌ فاسدٌ يعيد `[]`
 * — الشاشة تعرض «لا شيء» ولا تنكسر على رابطٍ معدَّل.
 */
export function monthGrid(monthKey: string): CalendarDay[][] {
  const match = /^(\d{4})-(\d{2})$/.exec(monthKey ?? '');
  if (!match) return [];
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (month < 1 || month > 12) return [];

  const firstMs = Date.UTC(year, month - 1, 1);
  // 0 = الأحد في `getUTCDay()` — أولُ أسبوعٍ الشاشة.
  const lead = new Date(firstMs).getUTCDay();
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const gridStartMs = firstMs - lead * MS_PER_DAY;
  const cells = Math.ceil((lead + daysInMonth) / DAYS_PER_WEEK) * DAYS_PER_WEEK;

  const days: CalendarDay[] = [];
  for (let index = 0; index < cells; index += 1) {
    days.push({
      date: isoFromMs(gridStartMs + index * MS_PER_DAY),
      inMonth: index >= lead && index < lead + daysInMonth,
    });
  }
  const weeks: CalendarDay[][] = [];
  for (let index = 0; index < days.length; index += DAYS_PER_WEEK) {
    weeks.push(days.slice(index, index + DAYS_PER_WEEK));
  }
  return weeks;
}

/** مدى الأسبوع (أحدٌ ← سبت) الذي يقع فيه تاريخٌ — للعرض الأسبوعيّ والطلب. */
export function weekRange(day: string): { start: string; end: string } {
  const ms = msFromIso(day);
  if (ms === null) return { start: '', end: '' };
  const startMs = ms - new Date(ms).getUTCDay() * MS_PER_DAY;
  return {
    start: isoFromMs(startMs),
    end: isoFromMs(startMs + (DAYS_PER_WEEK - 1) * MS_PER_DAY),
  };
}

/** أيامُ الأسبوع السبعة (ISO) التي يقع فيها تاريخ — من الأحد إلى السبت. */
export function weekDays(anchor: string): string[] {
  const { start } = weekRange(anchor);
  const startMs = msFromIso(start);
  if (startMs === null) return [];
  return Array.from(
    { length: DAYS_PER_WEEK },
    (_, index) => isoFromMs(startMs + index * MS_PER_DAY),
  );
}

/** اليومُ نفسه من الأسبوع بعد `delta` أسبوعاً — نافذةُ العرض الأسبوعيّ. */
export function shiftWeek(anchor: string, delta: number): string {
  const ms = msFromIso(anchor);
  if (ms === null) return '';
  return isoFromMs(ms + delta * DAYS_PER_WEEK * MS_PER_DAY);
}

/** مفتاحُ شهرٍ صالح `YYYY-MM` — والحسابُ في `utils/monthKey.ts` وحده. */
const isMonthKey = (value: string): boolean => /^\d{4}-(0[1-9]|1[0-2])$/.test(value ?? '');

/** الشهرُ التالي لمفتاح `YYYY-MM` — ومفتاحٌ فاسدٌ يعيد `''` لا `NaN-NaN`. */
export function nextMonthKey(monthKey: string): string {
  return isMonthKey(monthKey) ? shiftMonthKey(monthKey, 1) : '';
}

/** الشهرُ السابق لمفتاح `YYYY-MM`. */
export function previousMonthKey(monthKey: string): string {
  return isMonthKey(monthKey) ? shiftMonthKey(monthKey, -1) : '';
}

/**
 * أسطرُ اللائحة **بلا تكرارٍ بالكود**: فلترُ «النوع» يعرض نوعاً واحداً لكل كود،
 * وأحدثُ سنةٍ تغلب (لائحةُ 2027 أحدثُ من 2026)، والترتيبُ أبجديّ باسم السطر.
 *
 * ولا يُحذف سطرٌ من الخادم: التصفيةُ للعرض، ونفسُ الكود بسنةٍ أخرى يعمل في
 * تقويمها لأن الخادم يقرأ نسخةَ سنة الفترة.
 */
export function uniqueDeadlineRules(
  rows: readonly DeadlineRuleRow[],
): DeadlineRuleRow[] {
  const byCode = new Map<string, DeadlineRuleRow>();
  rows.forEach((rule) => {
    const current = byCode.get(rule.code);
    if (!current || rule.year > current.year) byCode.set(rule.code, rule);
  });
  return [...byCode.values()].sort((left, right) => left.name.localeCompare(right.name, 'ar'));
}

/** العناصرُ مجموعةً بمفتاح يومها — الشهرُ يُرسم بقراءة قاموسٍ لا بمسحٍ لكل يوم. */
export function groupDeadlinesByDay(
  rows: readonly CalendarDeadlineRow[],
): Record<string, CalendarDeadlineRow[]> {
  const byDay: Record<string, CalendarDeadlineRow[]> = {};
  rows.forEach((row) => {
    const key = String(row.actual_deadline).slice(0, 10);
    (byDay[key] ??= []).push(row);
  });
  return byDay;
}

/** اسمُ الشهر وحده من `utils/monthKey.ts` — لا جدولَ شهورٍ ثانٍ هنا. */
function monthNameOf(iso: string): string {
  const key = monthKeyOf(iso);
  const label = monthKeyLabel(key);
  const year = key.slice(0, 4);
  return label.endsWith(` ${year}`) ? label.slice(0, -(year.length + 1)) : label;
}

/**
 * تسميةُ الفترة — **احتياطٌ حين لا يرسل الخادم `period_label`** وحدها.
 *
 * الشكلُ نفسُه الذي يبنيه الخادم: «كانون الثاني 2026»، و«كانون الثاني–آذار 2026»،
 * و«2026» للسنة الكاملة، ومدىً يعبر السنة يُذكر فيه الطرفان.
 */
export function periodLabel(start: string, end: string): string {
  const startKey = monthKeyOf(start);
  const endKey = monthKeyOf(end);
  if (!startKey || !endKey) return '';
  if (startKey === endKey) return monthKeyLabel(startKey);
  const startYear = startKey.slice(0, 4);
  const endYear = endKey.slice(0, 4);
  if (startYear === endYear) {
    if (startKey.slice(5) === '01' && endKey.slice(5) === '12') return startYear;
    return `${monthNameOf(start)}–${monthNameOf(end)} ${startYear}`;
  }
  return `${monthNameOf(start)} ${startYear}–${monthNameOf(end)} ${endYear}`;
}

/** «متوقَّع» على كل سطرٍ محسوبٍ لم يُحفظ — و#275 تجعل المحفوظ كاملَ اللون. */
export function isExpectedDeadline(row: CalendarDeadlineRow): boolean {
  return row.expected !== false;
}
