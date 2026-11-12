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
import { monthKeyLabel, monthKeyOf, monthKeyRange, shiftMonthKey } from './monthKey.ts';
import { userRoleLabel } from './userRoleLabel.ts';

/** مسار شاشة الزبائن — مصدرٌ واحدٌ للرابط وقراءته. */
export const OFFICE_CLIENTS_PATH = '/accounting-office/clients';

/** مسار شاشة إعدادات المكتب — بجانب مسار الزبائن، مصدرٌ واحدٌ لجدول المسارات. */
export const OFFICE_SETTINGS_PATH = '/accounting-office/settings';

/** مسار شاشة التقويم (#274) — بجانبهما، ومصدرٌ واحدٌ للموجّه والقائمة. */
export const OFFICE_CALENDAR_PATH = '/accounting-office/calendar';

/** اسم معامل مجموعة الإعدادات — يُقرأ ويُبنى في مكانٍ واحد (#277). */
export const SETTINGS_GROUP_PARAM = 'group';

/** مجموعة «الضريبة ولائحة المواعيد» — وجهةُ تنبيهَي اللائحة. */
export const SETTINGS_GROUP_SCHEDULE = 'schedule';

/** مجموعة «المكتب» — فيها إعدادُ مكتب الدفاتر (طريقةِ إدخاله) وشجرتُه (#286/ب). */
export const SETTINGS_GROUP_OFFICE = 'office';

/** مجموعة «التذكيرات والنصوص» (#280/ب) — موضعُ النصوص وقائمةِ العطل. */
export const SETTINGS_GROUP_REMINDERS = 'reminders';

/** مجموعاتُ شاشة الإعدادات المعروفة — `?group=` خارجها يُتجاهَل. */
export const OFFICE_SETTING_GROUPS = ['office', 'schedule', 'alerts', 'reminders'] as const;

/** مفتاحُ وجهة التنبيه الذي يفتح شاشة اللائحة (#277) — من الخادم في `opens`. */
export const ALERT_OPENS_DEADLINE_RULES = 'deadline_rules';

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
  /** حدُّ طول النص (`kind === 'text'`) — من السجلّ لا من ثابتٍ في الواجهة. */
  max_length?: number | null;
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

/** اسم معامل تبويب ملفّ الزبون — مصدرٌ واحدٌ لبناء الرابط وقراءته (#276). */
export const CLIENT_TAB_PARAM = 'tab';

/** تبويبُ «الالتزامات والشغلات» — مكانُ فتح التنبيه من الجرس. */
export const CLIENT_OBLIGATIONS_TAB = 'obligations';

/** تبويبُ «المواعيد» (#281) — وجهةُ موعدٍ من التقويم إلى ملفّ زبونه. */
export const CLIENT_APPOINTMENTS_TAB = 'appointments';
/** تبويبُ «الدفتر» (#286/ب) — حركاتُ دفتر الزبون وإدخالُها. */
export const CLIENT_BOOK_TAB = 'book';
/** تبويبُ «الحساب» (#282/أ٢/٢) — «اللي عليه» وفواتيره ورصيده ورقمُ ملفّه. */
export const CLIENT_ACCOUNT_TAB = 'account';

/** اسم معامل الشغلة المطلوب فتحها — واحدٌ في بناء الرابط وقراءته (#276). */
export const TASK_QUERY_PARAM = 'task';

/** تبويباتُ ملفّ الزبون المعروفة — `?tab=` خارجها يُتجاهَل فلا تبيضّ الشاشة. */
export const CLIENT_TAB_KEYS = [
  'tax-card', 'obligations', 'services', 'contacts', 'documents',
  'reminder-log', 'notes',
  // #281: المواعيد — قبل «الدفتر»، فمفتاحُ #286/ب يبقى آخرَ القائمة (اختبارُه يثبته).
  'appointments',
  // #283/ب: الأتعابُ — دفعاتُ الزبون بإشعارِ قبضٍ لكلٍّ، وقبل «الدفتر» كذلك.
  'fees',
  // #282/أ٢/٢: «الحساب» — «اللي عليه» وفواتيره ورصيده ورقمُ ملفّه الضريبيّ.
  'account',
  'book',
] as const;
export type ClientTabKey = typeof CLIENT_TAB_KEYS[number];

/**
 * وجهةُ التنبيه: **ملفّ الزبون على تبويب «الالتزامات والشغلات»** (#276).
 *
 * التنبيهُ يحمل مكانَه لا محتواه: `client` هو ما يفتحه، و`task_id` هو **السطرُ
 * المقصود** فيُبرز ويُمرَّر إليه (`officeTaskAnchorId`)، والتبويبُ يُقرأ من
 * العنوان. وتنبيهٌ بلا زبون (مثل نوعَي اللائحة #277) لا وجهةَ له إلا إن قال
 * الخادمُ غير ذلك في `opens`: `deadline_rules` ⇒ شاشةُ الإعدادات على مجموعة
 * «الضريبة ولائحة المواعيد».
 */
export function alertTargetPath(
  alert: {
    client: { id: number } | null;
    task_id?: number | null;
    opens?: string | null;
  },
): string {
  if (alert.opens === ALERT_OPENS_DEADLINE_RULES) {
    return `${OFFICE_SETTINGS_PATH}?${SETTINGS_GROUP_PARAM}=${SETTINGS_GROUP_SCHEDULE}`;
  }
  if (!alert.client) return '';
  const base = `${clientFilePath(alert.client.id)}&${CLIENT_TAB_PARAM}=${CLIENT_OBLIGATIONS_TAB}`;
  return alert.task_id ? `${base}&${TASK_QUERY_PARAM}=${alert.task_id}` : base;
}

/**
 * المجموعةُ المطلوبة من عنوان شاشة الإعدادات — المعروفةُ وحدها، وإلا `null`.
 *
 * الفسادُ (رابطٌ قديمٌ أو معدَّلٌ يدوياً) لا يُرمى به: الشاشةُ تفتح على الافتراضي
 * بدل أن تنكسر.
 */
export function settingsGroupFromSearch(search: string): string | null {
  const params = new URLSearchParams(search.startsWith('?') ? search : `?${search}`);
  const raw = params.get(SETTINGS_GROUP_PARAM) ?? '';
  return (OFFICE_SETTING_GROUPS as readonly string[]).includes(raw) ? raw : null;
}

/** التبويبُ المطلوب من العنوان — المعروفُ وحده، وإلا `null` (الافتراضُ للشاشة). */
export function clientTabFromSearch(search: string): ClientTabKey | null {
  const params = new URLSearchParams(search.startsWith('?') ? search : `?${search}`);
  const raw = params.get(CLIENT_TAB_PARAM) ?? '';
  return (CLIENT_TAB_KEYS as readonly string[]).includes(raw)
    ? (raw as ClientTabKey)
    : null;
}

/** معرّفُ الشغلة المطلوب فتحها من العنوان — `null` إن غاب أو كان فاسداً. */
export function taskIdFromSearch(search: string): number | null {
  const params = new URLSearchParams(search.startsWith('?') ? search : `?${search}`);
  const raw = params.get(TASK_QUERY_PARAM);
  if (raw === null) return null;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

/** معرّفُ عنصر شغلةٍ في الصفحة — يُمرَّر إليه (`scrollIntoView`) ويُبرز. */
export function officeTaskAnchorId(taskId: number): string {
  return `office-task-${taskId}`;
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
  last_period_ours: boolean;
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
  /** «رسمي» أو «من المكتب» أو «حدث» — وتسميتُه من الخادم (#277). */
  origin: string;
  origin_label: string;
  period_start: string;
  period_end: string;
  period_label: string;
  legal_date: string;
  official_date: string;
  actual_deadline: string;
  internal_deadline: string;
  platform_official_date: string | null;
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
  /** #281: مواعيدُ المدى — تُعرض في اليوم نفسه مع التزاماته لا في شاشةٍ ثانية. */
  appointments: OfficeAppointmentRow[];
  /** #281: أنواعُ المواعيد — التقويمُ يحجز أيضاً، فلا جدولَ تسمياتٍ في الواجهة. */
  kind_choices: SettingChoice[];
}

/** خليّةُ يومٍ في شبكة الشهر — الأيامُ من الشهرين المجاورين تُعرض باهتةً لا تُحذف. */
export interface CalendarDay {
  date: string;
  inMonth: boolean;
}

/** سطرُ لائحة المواعيد — لفلتر «النوع» ولعرض اللائحة وتعديلها (#277). */
export interface DeadlineRuleRow {
  code: string;
  /** الكودُ صريحاً (= `code`) — يتكرّر لكل سنة فلا مفتاحَ به وحده. */
  rule_code: string;
  name: string;
  service_code: string;
  is_generated: boolean;
  needs_review: boolean;
  year: number;
  version: number;
  source_url: string;
  /** قيمُ المنصة — والوصفُ منها ومن `rule_kind_label`. */
  platform: {
    rule_kind: string;
    rule_kind_label: string;
    rule_day: number | null;
    rule_month: number | null;
    electronic_extension_days: number;
  };
  /** تعديلُ المكتب الساري، أو `null` إن لم يُعدَّل السطر. */
  override: DeadlineRuleOverrideRow | null;
  /** آخرُ صفوف تعديلٍ (الأحدث أوّلاً) — و«رجّع للمنصة» صفٌّ `cleared`. */
  history: DeadlineRuleOverrideRow[];
  /** المنصة غيّرت السطرَ بعد تعديل المكتب — يحسبه الخادم بمسند التنبيه نفسه. */
  awaiting_decision: boolean;
}

/** صفُّ تعديل مكتبٍ على سطر — **سجلٌّ إلحاقيّ** لا يُعدَّل ولا يُحذف. */
export interface DeadlineRuleOverrideRow {
  id: number;
  tax_system: string;
  rule_code: string;
  rule_day: number | null;
  rule_month: number | null;
  electronic_extension_days: number | null;
  cleared: boolean;
  note: string;
  based_on: Record<string, unknown>;
  created_by_name: string;
  created_at: string | null;
}

/** التزامٌ خاص بالمكتب (#277) — يُعطَّل ولا يُحذف. */
export interface OfficeCustomRuleRow {
  id: number;
  code: string;
  name: string;
  service: { id: number; code: string; name: string };
  cadence: string;
  cadence_label: string;
  rule_kind: string;
  rule_kind_label: string;
  rule_day: number | null;
  rule_month: number | null;
  is_active: boolean;
  origin_label: string;
}

export interface OfficeCustomRulesPayload {
  custom_rules: OfficeCustomRuleRow[];
  cadence_choices: SettingChoice[];
  rule_kind_choices: SettingChoice[];
  services: { id: number; code: string; name: string }[];
}

/** نوعُ حدثٍ مفعَّل — كما يرسله الخادم (`event_kinds`). */
export interface EventKindChoice {
  value: string;
  label: string;
}

/** حدثُ زبون مسجَّل («صار حدث») — والتزاماتُه كما في تبويب الالتزامات. */
export interface ClientEventRow {
  id: number;
  kind: string;
  kind_label: string;
  occurred_on: string;
  note: string;
  created_by_name: string;
  created_at: string;
  obligations: ObligationRow[];
}

export interface ClientEventsPayload {
  client: { id: number; name: string };
  event_kinds: EventKindChoice[];
  events: ClientEventRow[];
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

/** «متوقَّع» على كل سطر تقويمٍ اليوم (كلُّه محسوب)؛ وتمييزُ المحفوظ تذكرةٌ لاحقة. */
export function isExpectedDeadline(row: CalendarDeadlineRow): boolean {
  return row.expected !== false;
}

// ── «اليوم» والالتزامات والشغلات (#275) ─────────────────────────────────
//
// **ولا جدولَ تسمياتٍ هنا**: حالةُ الالتزام واتجاهُ المبلغ وشارةُ «قريب/متأخّر»
// تصل نصوصاً من الخادم (`status_label` · `direction_label` · `badges[].label`).
// ودالّةُ `serverLabel` تعيد نصَّ الخادم كما هو، و`value` الخام احتياطاً حين
// يغيب — فلا مصطلحان لشيءٍ واحد يفترقان عند أول تعديل في الخادم.
//
// الباقي حسابُ عرض: نصُّ المبلغ بالقناع، وقراءةُ الفلتر من العنوان، وتقصيرُ
// التاريخ إلى `dd/MM` — كلها نصوصُ ISO بلا كائن `Date` منطقةً زمنية.

/** مسار شاشة «اليوم» — مصدرٌ واحدٌ للموجّه والقائمة. */
export const OFFICE_TODAY_PATH = '/accounting-office/today';

/** فلترُ شاشة «اليوم»: الفارغ «الكل»، والباقي رقائقُه وعدّاداتُه. */
export type TodayFilter =
  | '' | 'mine' | 'week' | 'late' | 'late_internal' | 'missing_docs';

/** الفلاترُ الستّة المحسومة — الفارغ «الكل»، وغيرُها لا يُقرأ من العنوان. */
export const TODAY_FILTERS: readonly TodayFilter[] = [
  '', 'mine', 'week', 'late', 'late_internal', 'missing_docs',
];

/** اسم معامل العنوان الذي يحمل الفلتر — يُقرأ ويُكتب في مكانٍ واحد. */
export const TODAY_FILTER_PARAM = 'filter';

export interface ObligationBadge {
  key: string;
  label: string;
}

export interface ObligationAssignee {
  id: number;
  name: string;
}

/** الشغلةُ كما تدخل في سطر الالتزام: موعدُها الداخليُّ ومسؤولُها **الفعليّ**. */
export interface ObligationTaskRef {
  id: number;
  internal_deadline: string;
  assignee: ObligationAssignee | null;
}

/**
 * سطرُ التزامٍ كما يعيده الخادم.
 *
 * `amount` نصٌّ عشريّ أو `null`؛ **و`null` تعني «لا ترى المبالغ»** فيُعرض «—».
 * و`badges` تُحسب على يوم الطلب: الصفُّ نفسه قد يكون «قريباً» اليوم وغيرَه غداً.
 * و`due_date` (#277) هو الموعدُ الساري — الممدَّدُ إن وُجد — وما تُقرأ عليه
 * الشاراتُ والتصفيةُ في الخادم.
 */
export interface ObligationRow {
  id: number;
  client: { id: number; name: string };
  task: ObligationTaskRef;
  name: string;
  rule_code: string;
  origin: string;
  origin_label: string;
  period_label: string;
  official_date: string;
  actual_deadline: string;
  internal_deadline: string;
  /** الموعدُ الساري: `extended_to` أو `actual_deadline`. */
  due_date: string;
  extended_to: string | null;
  extension_note: string;
  /** تاريخُ المنصة حين يختلف عن موعد المكتب المعدَّل (#277). */
  platform_official_date: string | null;
  estimated: boolean;
  warnings: string[];
  badges: ObligationBadge[];
  amount: string | null;
  direction: string;
  direction_label: string;
  client_paid: boolean;
  status: string;
  status_label: string;
  /**
   * #278: تقدّمُ أوراق الالتزام — `{received, required}` أو `null`.
   *
   * `null` تعني «لا صفَّ ورقةٍ محسوباً لهذا الالتزام»، لا «صفر»: الشاشةُ تُظهر
   * العدّادَ حين يوجد وحدَه ولا تكتب «وصل 0/0».
   */
  docs: DocumentProgress | null;
}

/** تقدّمُ الأوراق: كم وصل من كم — من الخادم، بلا حسابٍ في الواجهة. */
export interface DocumentProgress {
  received: number;
  required: number;
}

export interface TodayCounters {
  /** «متأخّر رسمي» — أحمر. */
  late: number;
  /** «متأخّر داخلي» — أصفر. */
  late_internal: number;
  week: number;
  /** #278: «ناقصه أوراق» — عدّادٌ إضافيّ فوق شارات التأخير. */
  missing_docs: number;
  /** #281: مواعيدُ اليوم المحجوزة — قسمٌ مستقلٌّ لا صفوفَ التزامات. */
  appointments: number;
  all: number;
}

export interface TodayPayload {
  day: string;
  filter: string;
  counters: TodayCounters;
  rows: ObligationRow[];
  /** #281: مواعيدُ اليوم — لا يقصّها `filter`: الفلترُ للالتزامات وحدها. */
  appointments: OfficeAppointmentRow[];
  /** تسمياتُ اتجاه المبلغ — من الخادم، فلا نسخةً في الشاشة. */
  direction_choices: SettingChoice[];
}

/** شغلةُ فترةٍ في ملفّ الزبون — بكلِّ التزاماتها في كلّ الحالات. */
export interface ClientTaskRow {
  id: number;
  /** خدمةُ الشغلة: شغلتا «كانون الثاني» لق.م وللرواتب لا تُميَّزان بغيره. */
  service: { id: number; name: string };
  period_start: string;
  period_end: string;
  period_label: string;
  internal_deadline: string;
  assignee: ObligationAssignee | null;
  obligations: ObligationRow[];
}

export interface ClientObligationsPayload {
  client: { id: number; name: string };
  day: string;
  tasks: ClientTaskRow[];
  direction_choices: SettingChoice[];
}

/** نصُّ الخادم إن وصل، وإلا القيمةُ الخام — لا تسميةَ محليّةً تُنافسه. */
function serverLabel(label: string | null | undefined, value: string): string {
  const clean = (label ?? '').trim();
  return clean || (value ?? '');
}

/** تسميةُ حالة الالتزام — من `status_label` الذي يرسله الخادم. */
export function statusLabelOf(row: Pick<ObligationRow, 'status' | 'status_label'>): string {
  return serverLabel(row.status_label, row.status);
}

/** تسميةُ اتجاه المبلغ («عليه»/«إله») — من `direction_label`. */
export function directionLabelOf(
  row: Pick<ObligationRow, 'direction' | 'direction_label'>,
): string {
  return serverLabel(row.direction_label, row.direction);
}

/** تسميةُ الشارة — من `badges[].label`، والمفتاحُ احتياطاً. */
export function badgeLabelOf(badge: ObligationBadge): string {
  return serverLabel(badge.label, badge.key);
}

/**
 * نصُّ المبلغ كما يُعرض: «عليه ₪ 620.00» أو «إله ₪ …»، والمخفيُّ «—» وحدها.
 *
 * المبلغُ يصل نصّاً عشرياً من الخادم، فلا تحويلَ إلى `float` ولا تقريب. وحين
 * يغيب (`null` = لا رؤية مبالغ) لا يُعرض اتجاهٌ ولا صفر.
 */
export function obligationAmountText(
  row: Pick<ObligationRow, 'amount' | 'direction_label'>,
): string {
  const amount = formatOfficeAmount(row.amount);
  if (amount === AMOUNT_MASK) return AMOUNT_MASK;
  const direction = (row.direction_label ?? '').trim();
  return direction ? `${direction} ₪ ${amount}` : `₪ ${amount}`;
}

/** أصنافُ شارة الحالة المشتقّة — اللونُ عرضٌ، والنصُّ من الخادم. */
export function obligationBadgeClass(key: string): string {
  // #276: أحمرُ للرسميّ، وأصفرُ للداخليّ، و«قريب» محايدٌ فلا يلتبس بالأصفر.
  if (key === 'late') {
    return 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200';
  }
  if (key === 'late_internal') {
    return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200';
  }
  // #278: «ناقصه أوراق» كهرمانيّ — نقصُ ورقةٍ ليس تأخيراً رسمياً (أحمر).
  if (key === 'missing_docs') {
    return 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200';
  }
  if (key === 'near') {
    return 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300';
  }
  // #283/ب: «قبضٌ وصل» أخضر — خبرُ مالٍ دخل المكتب لا موعدٌ يقترب ولا ورقةٌ نقصت.
  if (key === 'payment_received') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200';
  }
  return 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300';
}

/** أصنافُ شارة الحالة المخزّنة («انقدّم»/«مش لازم هالفترة»). */
export function obligationStatusClass(status: string): string {
  if (status === 'submitted') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300';
  }
  if (status === 'not_required') {
    return 'border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400';
  }
  return 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300';
}

/**
 * الفلترُ المقروء من العنوان — `mine`/`week`/`late`، وأيُّ نصٍّ آخر «الكل».
 *
 * الفسادُ (رابطٌ قديمٌ أو معدَّلٌ يدوياً) لا يُرمى به: الشاشةُ تعرض الكلّ بدل أن
 * تنكسر، والخادمُ يرفض المجهول 400 فلو أُرسل كما هو لسقط الطلب.
 */
export function readTodayFilter(search: string): TodayFilter {
  const params = new URLSearchParams(search.startsWith('?') ? search : `?${search}`);
  const raw = params.get(TODAY_FILTER_PARAM) ?? '';
  return (TODAY_FILTERS as readonly string[]).includes(raw)
    ? (raw as TodayFilter)
    : '';
}

/** معاملاتُ العنوان لفلترٍ مختار — «الكل» بلا معامل، فيبقى العنوانُ نظيفاً. */
export function todayFilterParams(filter: TodayFilter): Record<string, string> {
  return filter ? { [TODAY_FILTER_PARAM]: filter } : {};
}

/**
 * تاريخٌ قصيرٌ `dd/MM` من نصّ ISO — بلا كائن `Date` ولا منطقةٍ زمنية.
 *
 * `2026-04-30T23:00-05:00` يبقى 30/04، والنصُّ الفاسد يعيد `''` (لا «NaN/NaN»).
 */
export function shortIsoDate(iso: string | null | undefined): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  if (!match) return '';
  return `${match[3]}/${match[2]}`;
}

// ── إشعار الدفع (#285) ──────────────────────────────────────────────────
//
// **اللونُ من الإشارة لا من العرض**: موجبٌ أحمر («عليك»)، وسالبٌ أخضر («إلك»)،
// و`|المبلغ| ≤ الحدّ` رماديّ يغلب على الاثنين. والقاعدةُ نفسُها في الخادم
// (`appointments.payment_notice_tone`) لأن الورقةَ المصيَّرة تُلوَّن هناك؛ وهذه
// مرآتُها المختبرة بـ`node --test`، فلا تنحرف صورُ الصفحة عمّا يعرفه العميل.
// والنصوصُ («عليك»/«إلك») لا تُكتب هنا — تصل من الخادم كسائر نصوص الموديول.

/** ألوانُ سطر الإشعار أو مجموعه — مفاتيحُ عرضٍ، لا نصوصَ تُعرَض. */
export type PaymentNoticeTone = 'owed' | 'refund' | 'neutral';

/** مبلغٌ نصٌّ عشريّ من الخادم ← عدد؛ الفاسدُ والغائبُ صفرٌ لا `NaN`. */
function noticeAmount(value: number | string | null | undefined): number {
  const parsed = typeof value === 'number'
    ? value
    : Number.parseFloat(String(value ?? '').trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * لونُ مبلغٍ في إشعار الدفع عند حدٍّ رماديٍّ — دالّةٌ نقيّة.
 *
 * القاعدةُ من قيمتين لا من ثلاث حالات: `|المبلغ| ≤ الحدّ` رماديّ (**شاملٌ**:
 * مبلغُ 10 بحدِّ 10 رماديّ)، وما فوقه أحمرُ للإيجابيّ وأخضرُ للسالب. والحدُّ
 * المطلقُ هو المستعمل: حدٌّ سالبٌ يُقرأ كموجبه بدل أن يقلب كلَّ مبلغٍ رماديّاً.
 *
 * **ومقارنةُ نطاقٍ لا حسابُ مال**: المبالغُ تُصلَح في الخادم بـ`Decimal`، وهذه
 * تلوّن ما وصل منه — فـ`Number` هنا لا يُقارَب به قرش.
 */
export function paymentNoticeTone(
  amount: number | string | null | undefined,
  threshold: number | string | null | undefined,
): PaymentNoticeTone {
  const value = noticeAmount(amount);
  if (Math.abs(value) <= Math.abs(noticeAmount(threshold))) return 'neutral';
  return value > 0 ? 'owed' : 'refund';
}

// ── التنبيهات والجرس (#276) ──────────────────────────────────────────────
//
// **ولا تسميةَ نوعٍ هنا ولا خريطةُ نوعٍ ← شارة**: `kind_label` و`badge` يصلان من
// الخادم (`OFFICE_ALERT_KIND_LABELS`/`OFFICE_ALERT_KIND_BADGES`)، والواجهة تُلوّن
// بـ`obligationBadgeClass(alert.badge)` بلا معرفة أنواع. والرسالةُ نصُّه كما وُلد.

/** تنبيهٌ كما يعيده `GET alerts/` — **بلا مبلغ**. */
export interface OfficeAlertRow {
  id: number;
  kind: string;
  /** تسميةُ النوع من الخادم — لا نسخةً محليّة تنافسها. */
  kind_label: string;
  /** مفتاحُ شارة النوع (`late`/`late_internal`) أو `''` لنوعٍ لم تُعرَّف شارته. */
  badge: string;
  /** وجهةُ الفتح: `client` (ملفّ الزبون) أو `deadline_rules` (شاشة اللائحة). */
  opens: string;
  message: string;
  client: { id: number; name: string } | null;
  task_id: number | null;
  obligation_id: number | null;
  day: string;
  seen: boolean;
  created_at: string;
}

export interface OfficeAlertsPayload {
  /** عددُ غير المرئيّ **وغير المحسوم** — يُنقصه «شفته». */
  unseen: number;
  rows: OfficeAlertRow[];
}

// ── تعديل المكتب والتمديد والأحداث (#277) ────────────────────────────────
//
// **ولا تسميةَ نوعِ قاعدةٍ هنا**: `rule_kind_label` يصل من الخادم، ويُستعمل بديلاً
// حين لا يكون للنوع وصفٌ حسابيّ. والوصفُ نفسُه تركيبٌ من اليوم والشهر — لا تاريخٌ
// قانونيّ مكتوبٌ في الواجهة.

/**
 * وصفُ قاعدة سطر اللائحة كما يُعرض: «يوم 15 من الشهر التالي».
 *
 * يُركَّب من `rule_day`/`rule_month` لأن الرقم هو ما يعدّله المكتب، ويُرجَع نصُّ
 * الخادم (`rule_kind_label`) لنوعٍ لا وصفَ حسابيّ له — ولا فراغ.
 */
export function deadlineRuleDescription(rule: {
  rule_kind: string;
  rule_kind_label?: string | null;
  rule_day?: number | null;
  rule_month?: number | null;
}): string {
  const label = (rule.rule_kind_label ?? '').trim();
  const day = rule.rule_day ?? null;
  const month = rule.rule_month ?? null;
  if (rule.rule_kind === 'end_of_period') return label || 'آخر يوم في الفترة';
  if (rule.rule_kind === 'day_of_next_month') {
    return day === null ? 'الشهر التالي' : `يوم ${day} من الشهر التالي`;
  }
  if (rule.rule_kind === 'month_day_next_year') {
    return day === null || month === null
      ? 'السنة التالية'
      : `يوم ${day} من الشهر ${month} من السنة التالية`;
  }
  if (rule.rule_kind === 'days_after_event') {
    return day === null ? 'بعد الحدث' : `بعد ${day} يوماً من الحدث`;
  }
  return label || rule.rule_kind || '';
}

/**
 * مدخلُ `deadlineRuleDescription` لسطرٍ معدَّل: **التعديلُ جزئيّ**، و`null` فيه
 * «كالمنصة» — فكلُّ حقلٍ يُدمج وحده (`التعديل ?? المنصة`) لا يُمرَّر خاماً.
 */
export function overriddenRuleInput(
  platform: {
    rule_kind: string;
    rule_kind_label?: string | null;
    rule_day?: number | null;
    rule_month?: number | null;
  },
  override: { rule_day?: number | null; rule_month?: number | null },
): {
  rule_kind: string;
  rule_kind_label?: string | null;
  rule_day: number | null;
  rule_month: number | null;
} {
  return {
    rule_kind: platform.rule_kind,
    rule_kind_label: platform.rule_kind_label,
    rule_day: override.rule_day ?? platform.rule_day ?? null,
    rule_month: override.rule_month ?? platform.rule_month ?? null,
  };
}

/**
 * نصُّ التمديد: «ممدَّد حتى 15/04 — مدّدنا». وصفٌّ بلا تمديدٍ يعيد `''`.
 *
 * والملاحظةُ تُقرأ من الخادم كما هي ولا تُعاد صياغتها.
 */
export function obligationExtensionText(row: {
  extended_to?: string | null;
  extension_note?: string | null;
}): string {
  if (!row.extended_to) return '';
  const day = shortIsoDate(row.extended_to);
  const note = (row.extension_note ?? '').trim();
  return note ? `ممدَّد حتى ${day} — ${note}` : `ممدَّد حتى ${day}`;
}

/**
 * شارةُ أصل الالتزام: «من المكتب» أو «حدث» — والرسميُّ بلا شارة.
 *
 * النصُّ من `origin_label` الذي يرسله الخادم، فإضافةُ أصلٍ ثالثٍ لا تلمس الواجهة.
 */
export function obligationOriginLabel(row: {
  origin: string;
  origin_label?: string | null;
}): string {
  return row.origin === 'official' ? '' : (row.origin_label ?? '').trim();
}

/** «المنصة: 16/02» — تاريخُ المنصة بجانب تاريخ المكتب حين يختلفان، وإلا `''`. */
export function platformOfficialText(row: {
  platform_official_date?: string | null;
}): string {
  if (!row.platform_official_date) return '';
  return `المنصة: ${shortIsoDate(row.platform_official_date)}`;
}

/** ثلاثون يوماً — مدىً شهريٌّ معتادٌ للتمديد، لا تاريخٌ قانونيّ. */
const EXTENSION_DEFAULT_DAYS = 30;

/**
 * تاريخُ تمديدٍ مقترح: **ثلاثون يوماً بعد الموعد الساري**.
 *
 * التمديدُ بعده شرطٌ خادميّ (وإلا فهو تقديمٌ لا تمديد)، فالافتراضُ لا يقع في
 * تاريخٍ يرفضه. والناتجُ نصُّ ISO بلا كائن `Date` منطقةً زمنية، والسطرُ الفاسد
 * يعيد `''` فلا يُملأ حقلُ التاريخ بقيمةٍ مخترعة.
 */
export function defaultExtensionDate(dueDate: string): string {
  const ms = msFromIso(dueDate);
  if (ms === null) return '';
  return isoFromMs(ms + EXTENSION_DEFAULT_DAYS * MS_PER_DAY);
}

// ── قائمة الأوراق وشبكة الأشهر (#278) ───────────────────────────────────────
//
// **الخادمُ يعرف الحالة والاسم والفترة**، وهنا حسابُ عرضٍ لا قرار: شكلُ الشبكة
// (خانةٌ لكل شهرٍ دائماً)، ولونُ الخانة ورمزُها، وعدّادُ «وصل n/م»، وسطرُ
// «ناقصٌ لشهر…». ولا نُسمّي حالةً من عندنا: `status_label` يُقرأ من الخادم،
// وتسميةُ «مش لازمة هالسنة» السنوية تأتي `annual_label` معه.

/** حقلُ ملفّ الورقة كما يعيده الخادم — **بلا `file_url`** أبداً. */
export interface DocumentFileRow {
  id: number;
  uid: string;
  document_type: string;
  issuer_registration: string;
  document_date: string | null;
  document_number: string;
  captured_at: string | null;
  file_name: string;
  is_copy: boolean;
  /** وسمُ النسخة: «صورة — الأصل عند الزبون» حين تكون نسخة. */
  copy_label: string;
  created_by_name: string;
}

/** خانةُ شهرٍ — `row_id === null` تعني «لا صفَّ لهذا البند في هذا الشهر». */
export interface DocumentCell {
  month: string;
  row_id: number | null;
  status: string | null;
  status_label: string;
  received_on: string | null;
  received_by_name: string;
  channel: string;
  channel_label: string;
  files_count: number;
}

export interface DocumentItemRow {
  item_code: string;
  name: string;
  cells: DocumentCell[];
}

/** سطرُ ورقةٍ كاملاً — من فعل الحالة ومن القائمة السنوية. */
export interface DocumentRowPayload {
  row_id: number;
  client_id: number;
  item_code: string;
  name: string;
  service_codes: string[];
  cadence: string;
  period_start: string;
  period_end: string;
  period_label: string;
  status: string;
  status_label: string;
  received_on: string | null;
  received_by_name: string;
  channel: string;
  channel_label: string;
  files_count: number;
  /** القائمةُ السنوية وحدها تحمل الملفات كاملةً. */
  files?: DocumentFileRow[];
}

/** مدةُ حفظٍ قانونية — النصُّ يصوغه الخادم (`text`) والواجهةُ ترسمه. */
export interface DocumentRetentionRow {
  code: string;
  name: string;
  years: number;
  alt_years: number | null;
  basis: string;
  basis_label: string;
  source_url: string;
  text: string;
}

/** اختيارٌ من الخادم: قيمةٌ وتسمية — والحالةُ السنوية لها `annual_label`. */
export interface DocumentChoice {
  value: string;
  label: string;
  annual_label?: string;
}

export interface ClientDocumentsPayload {
  client: { id: number; name: string };
  year: number;
  months: string[];
  items: DocumentItemRow[];
  annual: DocumentRowPayload[];
  retention: DocumentRetentionRow[];
  status_choices: DocumentChoice[];
  channel_choices: DocumentChoice[];
  cadence_choices: DocumentChoice[];
  available_years: number[];
}

/** سطرُ بندٍ في قالب المكتب — المنصّةُ والمكتبُ في شكلٍ واحد. */
export interface OfficeDocumentItemRow {
  /** معرّفُ بند المكتب وحده؛ بندُ المنصّة `null` (لا صفَّ له في `OfficeDocumentItem`). */
  id: number | null;
  item_code: string;
  name: string;
  cadence: string;
  cadence_label: string;
  service_codes: string[];
  card_conditions: Record<string, string[]>;
  included: boolean;
  is_custom: boolean;
  is_active: boolean;
  sort_order: number | null;
  /** خيارُ الزبون على هذا البند — `null` إن لا خيار (لوحُ التخصيص وحده). */
  client_included?: boolean | null;
}

export interface OfficeDocumentItemsPayload {
  system: string;
  items: OfficeDocumentItemRow[];
  services: { code: string; name: string }[];
  cadence_choices: DocumentChoice[];
  condition_fields: string[];
}

/** عنوانُ عمود شهرٍ — اسمُ الشهر من `utils/monthKey.ts` وحده، بلا جدولٍ ثانٍ. */
export function documentMonthLabel(iso: string): string {
  return monthNameOf(iso);
}

/** أعمدةُ الشبكة: الشهرُ وتسميتُه، بترتيب الخادم (تصاعداً). */
export function documentMonthColumns(
  months: readonly string[],
): { iso: string; label: string }[] {
  return months.map((iso) => ({ iso, label: documentMonthLabel(iso) }));
}

/** خانةٌ فارغةٌ لشهرٍ بلا صفّ — **الشكلُ نفسه** فلا تفريعَ في الرسم. */
export function emptyDocumentCell(month: string): DocumentCell {
  return {
    month,
    row_id: null,
    status: null,
    status_label: '',
    received_on: null,
    received_by_name: '',
    channel: '',
    channel_label: '',
    files_count: 0,
  };
}

/**
 * صفوفُ الشبكة كما تُرسم: **خانةٌ لكل شهرٍ في كل صفّ** (معيار القبول ٥).
 *
 * الخادمُ يُرسل الخانات بعدد الأشهر، وهذه الدالّةُ تُعيد بناءها بالمفتاح على
 * الشهر لا بالترتيب: صفٌّ ناقصُ خانةٍ (أو مربوطٌ بشهرٍ آخر) لا يُزيح صفوفَه،
 * والفارغُ يُملأ بخانةٍ محايدةٍ فيبقى الجدولُ مستقيماً.
 */
export function documentGridRows(
  payload: Pick<ClientDocumentsPayload, 'months' | 'items'>,
): { item_code: string; name: string; cells: DocumentCell[] }[] {
  return payload.items.map((item) => {
    const byMonth = new Map<string, DocumentCell>();
    for (const cell of item.cells) byMonth.set(cell.month, cell);
    return {
      item_code: item.item_code,
      name: item.name,
      cells: payload.months.map(
        (month) => byMonth.get(month) ?? emptyDocumentCell(month),
      ),
    };
  });
}

/** ألوانُ الحالات الأربع كما في النموذج المرئي — والفراغُ محايد. */
export type DocumentCellTone =
  | 'received' | 'partial' | 'required' | 'skipped' | 'empty';

/** لونُ الخانة من حالتها وحدها (والفراغُ حالةُ `row_id === null`). */
export function documentCellTone(cell: DocumentCell): DocumentCellTone {
  if (cell.row_id === null || !cell.status) return 'empty';
  if (cell.status === 'received') return 'received';
  if (cell.status === 'partial') return 'partial';
  if (cell.status === 'not_needed') return 'skipped';
  return 'required';
}

/** أصنافُ خانة الشبكة — Tailwind وحده، والوضعُ الداكن معها. */
export function documentCellClass(cell: DocumentCell): string {
  switch (documentCellTone(cell)) {
    case 'received':
      return 'border-emerald-200 bg-emerald-50 text-emerald-600 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300';
    case 'partial':
      return 'border-amber-200 bg-amber-50 text-amber-600 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300';
    case 'required':
      return 'border-2 border-rose-200 bg-white text-rose-500 dark:border-rose-900 dark:bg-slate-900 dark:text-rose-300';
    case 'skipped':
      return 'border-slate-200 bg-slate-100 text-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500';
    default:
      return 'border-slate-100 bg-transparent text-transparent dark:border-slate-800';
  }
}

/** رمزُ الخانة: ✓ وصلت، ! ناقصة، نقطةٌ للمطلوبة، – لمش لازمة، وفراغ. */
export function documentCellGlyph(cell: DocumentCell): string {
  switch (documentCellTone(cell)) {
    case 'received':
      return '✓';
    case 'partial':
      return '!';
    case 'required':
      return '•';
    case 'skipped':
      return '–';
    default:
      return '';
  }
}

/** تسميةُ الخانة لغير البصر: تُقرأ بالشاشة القارئة من `status_label` الخادم. */
export function documentCellTitle(cell: DocumentCell): string {
  if (cell.row_id === null) return '';
  const label = serverLabel(cell.status_label, cell.status ?? '');
  return cell.files_count
    ? `${label} — ${cell.files_count} ملف`
    : label;
}

/** الحالاتُ الأربع للاختيار — والسنويةُ تأخذ تسميةَ «مش لازمة هالسنة». */
export function documentStatusChoicesFor(
  choices: readonly DocumentChoice[],
  annual: boolean,
): { value: string; label: string }[] {
  return choices.map((choice) => ({
    value: choice.value,
    label: annual
      ? (choice.annual_label ?? choice.label)
      : choice.label,
  }));
}

/** نصُّ «وصل 3/5» — `''` حين لا صفوفَ محسوبة (لا «0/0»). */
export function documentDocsText(
  docs: DocumentProgress | null | undefined,
): string {
  if (!docs || !docs.required) return '';
  return `وصل ${docs.received}/${docs.required}`;
}

/**
 * سطرُ «ناقصٌ لشهر…» فوق الشبكة: آخرُ شهرٍ فيه خانةٌ مطلوبةٌ أو ناقصة.
 *
 * يعيد `null` إن لم ينقص شيء — فلا شريطَ كهرمانيٌّ بلا سبب. والاسمُ من لقطة
 * الصفّ (`name`) لا من الكتالوج: ما رُسم هو ما يُقال.
 */
export function documentMissingBar(
  payload: Pick<ClientDocumentsPayload, 'months' | 'items'>,
): { monthLabel: string; names: string[]; counts: string } | null {
  if (!payload.months.length) return null;
  const month = payload.months[payload.months.length - 1];
  const names: string[] = [];
  let required = 0;
  let partial = 0;
  for (const item of payload.items) {
    const cell = item.cells.find((entry) => entry.month === month);
    if (!cell) continue;
    if (cell.status === 'partial') partial += 1;
    else if (cell.status === 'required') required += 1;
    else continue;
    names.push(item.name);
  }
  if (!names.length) return null;
  const counts = [
    required ? `${required} مطلوبة` : '',
    partial ? `${partial} ناقصة` : '',
  ].filter(Boolean).join(' · ');
  return { monthLabel: documentMonthLabel(month), names, counts };
}

/** وسمُ الملف: نسخةُ عملٍ أم أصلٌ موثَّق — النصُّ من الخادم. */
export function documentFileTag(file: Pick<DocumentFileRow, 'copy_label'>): string {
  return (file.copy_label ?? '').trim();
}

/** سنةٌ معروضةٌ في المنتقي — من `available_years` وحدها (الأحدثُ أوّلاً). */
export function documentYearOptions(
  payload: Pick<ClientDocumentsPayload, 'available_years'>,
): number[] {
  return [...payload.available_years];
}


/** صنفُ رقاقة الحالة في دليل الألوان — نفس ألوان الخانة بلا موضعٍ خاصّ. */
export function documentStatusChipClass(status: string): string {
  return documentCellClass({
    month: '',
    row_id: 1,
    status,
    status_label: '',
    received_on: null,
    received_by_name: '',
    channel: '',
    channel_label: '',
    files_count: 0,
  });
}


// ── رقم واتساب المكتب (#280/D10) ─────────────────────────────────────────────
//
// **الرقمُ يُبنى هنا لأن الرابط لا يُبنى في الخادم**: الخادم يرسل هاتفاً كما
// أدخله المكتب («0599123456»)، و`wa.me` لا يقبل إلا رقماً دولياً بأرقامٍ فقط.
// وبناءُ الرقم في الخادم كان يعني رابطاً محفوظاً في ردٍّ يُخزَّن أو يُنسخ؛
// والدالّةُ الخالصة تُختبر وحدها وتُقرأ من الشاشة كلّها.
//
// **مفتاحُ الدولة من نظام الزبون الضريبي** حين لا يكون الرقم جوالاً فلسطينياً
// معروفاً: 059/056 جوالٌ فلسطينيّ، و05 غيرُهما جوالٌ إسرائيليّ، وأيُّ صفرٍ آخر
// (أرضيّ) يأخذ دولة النظام. ونظامٌ مجهول مع أرضيّ ⇒ `null` لا تخمين: رقمٌ
// يُبنى بمفتاح بلدٍ خطأ يفتح محادثةً مع شخصٍ آخر.

/** مفاتيحُ الدولة المعروفة — من النظام الضريبي للزبون، لا من جدولٍ ثالث. */
const OFFICE_DIAL_CODES: Record<string, string> = {
  PS: '970',
  IL: '972',
};

/** أقصر رقم دوليّ فعليّ ثمانية أرقام، وأطولُه خمسةَ عشر (E.164). */
const MIN_INTERNATIONAL_DIGITS = 8;
const MAX_INTERNATIONAL_DIGITS = 15;

/**
 * رقمُ واتساب دوليٌّ من هاتفٍ محلّيٍّ أو دوليّ — أو `null` صراحةً.
 *
 * `taxSystem` نظامُ الزبون الضريبيّ (`PS`/`IL`) ويُقرأ للحاجة إليه وحده: رقمٌ
 * محلّيٌّ يبدأ بـ`0` غيرِ `05` (أرضيّ) لا يُعرف مفتاحُ دولته إلا منه.
 */
export function officeWhatsappNumber(
  phone?: string | null,
  taxSystem?: string | null,
): string | null {
  const raw = (phone ?? '').trim();
  if (!raw) return null;
  const hadPlus = raw.startsWith('+');
  const digits = raw.replace(/\D/g, '');
  if (!digits) return null;

  // «دوليٌّ أصلاً»: `+` أو `00` — يُقصّ الصفران ويبقى مفتاحُ الدولة.
  if (hadPlus || digits.startsWith('00')) {
    const international = digits.startsWith('00') ? digits.slice(2) : digits;
    // رقمٌ دوليّ لا يبدأ بصفر: `+0599…` إدخالٌ فاسد لا رقم.
    if (!international || international.startsWith('0')) return null;
    return withinDialLength(international) ? international : null;
  }

  if (!digits.startsWith('0')) return null;

  // جوالٌ فلسطينيّ: 059/056 ⇒ 970، وغيرُهما من 05 جوالٌ إسرائيليّ ⇒ 972.
  if (digits.startsWith('059') || digits.startsWith('056')) {
    return withinDialLength('970' + digits.slice(1)) ? '970' + digits.slice(1) : null;
  }
  if (digits.startsWith('05')) {
    return withinDialLength('972' + digits.slice(1)) ? '972' + digits.slice(1) : null;
  }

  // أرضيٌّ أو أيُّ صفرٍ آخر: مفتاحُ الدولة من نظام الزبون وحده.
  const country = OFFICE_DIAL_CODES[(taxSystem ?? '').trim().toUpperCase()];
  if (!country) return null;
  const international = country + digits.slice(1);
  return withinDialLength(international) ? international : null;
}

function withinDialLength(digits: string): boolean {
  return (
    digits.length >= MIN_INTERNATIONAL_DIGITS
    && digits.length <= MAX_INTERNATIONAL_DIGITS
  );
}

/**
 * رابطُ محادثة واتساب مع نصٍّ جاهز — أو `null` إن كان الرقم غير قابلٍ للبناء.
 *
 * `null` مقصودٌ لا خطأ: الشاشةُ تعرض «بلا واتساب» بدل زرٍّ يفتح محادثةً مع
 * شخصٍ آخر. والنصُّ يُرمَّز دائماً — عربيٌّ وأسطرٌ جديدة في `?text=`.
 */
export function officeWhatsappLink(
  phone?: string | null,
  taxSystem?: string | null,
  text = '',
): string | null {
  const number = officeWhatsappNumber(phone, taxSystem);
  if (!number) return null;
  return `https://wa.me/${number}?text=${encodeURIComponent(text)}`;
}


// ── «جاهز للإرسال» وسجلّ التذكيرات (#280/ب) ─────────────────────────────────
//
// **ولا تسميةَ نوعٍ ولا تسميةَ صفٍّ هنا**: `reminder_type_label` و`kind_label`
// و`channel_label` تصل نصوصاً من الخادم، فلا نسخةً محليّةً تنافسها. والباقي
// حسابُ عرضٍ حقيقيّ: رقائقُ الأنواع من رسائل اليوم وحدها، والرسالةُ تُرشَّح
// **كاملةً** لأنها وحدةُ الإرسال، و«أُلغي» يُشتقّ من `reverts_id` لا من علمٍ
// ثانٍ يحتمل أن يفترق عنه.

/** مسار شاشة «جاهز للإرسال» — مصدرٌ واحدٌ للموجّه والقائمة. */
export const OFFICE_READY_TO_SEND_PATH = '/accounting-office/ready-to-send';

/** مسارُ شاشة «المسودّات» (#282/أ٢/٢) — مصدرٌ واحدٌ للموجّه والقائمة. */
export const OFFICE_FEE_DRAFTS_PATH = '/accounting-office/fee-drafts';

/**
 * مفاتيحُ إعداداتٍ **مقفلةٌ مطفأةً** في المرحلة الأولى (‏`LOCKED_SETTING_MESSAGES`
 * خادمياً): الخادمُ يردّ 400 على أيّ قيمةٍ أخرى، والشاشةُ تُقفل ضابطها كي لا
 * يجرّب الموظفُ حفظاً مصيرُه الرفض. القفلُ **عرضٌ لا إنفاذ** — الحكمُ للخادم.
 */
export const OFFICE_LOCKED_SETTING_KEYS: readonly string[] = ['reminder_auto_send'];

/** هل هذا الإعدادُ مقفلٌ مطفأً؟ (‏`reminder_auto_send` وحده اليوم.) */
export function isLockedOfficeSetting(key: string): boolean {
  return OFFICE_LOCKED_SETTING_KEYS.includes(key);
}

/** قيمةُ رقاقة «الكل» — فارغةٌ كما في فلتر «اليوم»، فيبقى العنوانُ نظيفاً. */
export const READY_TO_SEND_TYPE_ALL = '';

/** أقلُّ ما تحتاجه رقاقةُ النوع من الرسالة — ويُلبّيه حمولُ الخادم كما هو. */
interface ReadyToSendTypeSource {
  items: readonly { reminder_type: string; reminder_type_label: string }[];
}

/**
 * رقائقُ أنواع اليوم: **«الكل» أوّلاً، ثم ما له رسائلُ فعلاً** بتسمية الخادم،
 * وعدُّ كل رقاقةٍ عددُ الرسائل التي تحمل بنداً من نوعها (لا عددُ البنود: الكبسةُ
 * تُرشِّح رسائل). يومٌ بلا رسائلَ لا رقاقةَ فيه — ولا «الكل» وحدها.
 */
export function readyToSendTypeChips(
  messages: readonly ReadyToSendTypeSource[],
): { value: string; label: string; count: number }[] {
  if (!messages.length) return [];
  const labels = new Map<string, string>();
  messages.forEach((message) => {
    message.items.forEach((item) => {
      if (!labels.has(item.reminder_type)) {
        labels.set(item.reminder_type, item.reminder_type_label);
      }
    });
  });
  return [
    { value: READY_TO_SEND_TYPE_ALL, label: 'الكل', count: messages.length },
    ...[...labels].map(([value, label]) => ({
      value,
      label,
      count: filterReadyToSendMessages(messages, value).length,
    })),
  ];
}

/**
 * رسائلُ نوعٍ مختار — **الرسالةُ كاملةً** إذا حملت بنداً من نوعه: النصُّ المرسَل
 * نصُّ الرسالة كلِّها، فقصُّ بنودها يعرض نصّاً غيرَ الذي سيخرج. والفراغُ «الكل».
 */
export function filterReadyToSendMessages<T extends ReadyToSendTypeSource>(
  messages: readonly T[],
  reminderType: string,
): T[] {
  if (!reminderType) return [...messages];
  return messages.filter((message) =>
    message.items.some((item) => item.reminder_type === reminderType),
  );
}

/** أقلُّ ما يحتاجه مفتاحُ الرسالة وبندُ فعلها — نفسُ حمول الخادم بلا زيادة. */
interface ReadyToSendKeySource {
  recipient: { contact_id: number };
  items: readonly {
    client_id: number;
    reminder_type: string;
    period_start: string;
    period_end: string;
  }[];
}

/**
 * مفتاحُ مسوّدةِ النصّ لكل رسالة — **مشتقٌّ من محتواها** لا من فهرسها: بعد كل
 * فعلٍ تُقرأ القائمةُ من جديد، ففهرسٌ متحرّكٌ كان ينسخ مسوّدةَ رسالةٍ إلى أخرى.
 * والبنودُ مرتَّبةٌ قبل البناء فلا يتغيّر المفتاحُ بتبديل ترتيبها.
 */
export function readyToSendMessageKey(message: ReadyToSendKeySource): string {
  const parts = message.items
    .map((item) => (
      `${item.client_id}:${item.reminder_type}:${item.period_start}:${item.period_end}`
    ))
    .sort();
  return `${message.recipient.contact_id}|${parts.join('؛')}`;
}

/**
 * بندُ الفعل: **المفتاحُ الحقيقيُّ للتذكير** — الزبون والنوع وطرفا الفترة.
 * لا تسميةَ ولا نصَّ فيه، والخادمُ يعيد حلَّ كلٍّ منها على زبائن العضو.
 */
export function readyToSendItemKeys(message: ReadyToSendKeySource): {
  client_id: number;
  reminder_type: string;
  period_start: string;
  period_end: string;
}[] {
  return message.items.map((item) => ({
    client_id: item.client_id,
    reminder_type: item.reminder_type,
    period_start: item.period_start,
    period_end: item.period_end,
  }));
}

/** أقلُّ ما يحتاجه مفتاحُ صفّ البند — الورقةُ إن كان البندُ فاتورةً. */
interface ReadyToSendRowKeySource {
  client_id: number;
  reminder_type: string;
  period_start: string;
  period_end: string;
  invoice?: { id: number } | null;
}

/**
 * مفتاحُ صفّ البند في «جاهز للإرسال» — **معرّفُ الورقة** لبنود الفواتير.
 *
 * ورقتان لزبونٍ واحدٍ صادرتان في اليوم نفسه تتشاركان (الزبون، النوع، الفترة):
 * مفتاحٌ من الأربعة يسلّم React مفتاحين متطابقين فيرسو على الصفّ الخطأ. والورقةُ
 * نفسُها هي المفتاح حين تكون البندَ، وما ليس فاتورةً يبقى على الأربعة.
 */
export function readyToSendItemRowKey(item: ReadyToSendRowKeySource): string {
  if (item.invoice) return `invoice:${item.invoice.id}`;
  return `${item.client_id}|${item.reminder_type}|${item.period_start}|${item.period_end}`;
}

/**
 * أنواعُ الصفوف القابلة للإبطال — `sent` و`manual` (`REMINDER_COUNTED_KINDS`
 * خادمياً). مفتاحان لا تسميتان، والخادمُ يرفض ما عداهما 400 على أيّ حال.
 */
const REMINDER_UNDOABLE_KINDS: readonly string[] = ['sent', 'manual'];

/** معرّفاتُ الصفوف التي أبطلها صفُّ `undo` لاحق — «أُلغي» في السجلّ. */
export function revertedReminderLogIds(
  rows: readonly { id: number; reverts_id: number | null }[],
): Set<number> {
  const reverted = new Set<number>();
  rows.forEach((row) => {
    if (row.reverts_id !== null && row.reverts_id !== undefined) {
      reverted.add(row.reverts_id);
    }
  });
  return reverted;
}

/**
 * هل يُعرض «ما انبعتت» على هذا الصف؟ إرسالٌ أو مكالمةٌ **لم يُبطَل أحدُهما**
 * (والـ`undo` لا يُبطَل، فلا حلقةَ في السجلّ).
 */
export function canUndoReminderRow(
  row: { id: number; kind: string },
  revertedIds: ReadonlySet<number>,
): boolean {
  return REMINDER_UNDOABLE_KINDS.includes(row.kind) && !revertedIds.has(row.id);
}

/** أصنافُ شارة نوع الصفّ — اللونُ عرضٌ، والنصُّ من `kind_label` كما وصل. */
export function reminderLogKindClass(kind: string): string {
  if (kind === 'sent') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300';
  }
  if (kind === 'manual') {
    return 'border-teal-200 bg-teal-50 text-teal-700 dark:border-teal-900 dark:bg-teal-950/40 dark:text-teal-300';
  }
  if (kind === 'dismissed') {
    return 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200';
  }
  return 'border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400';
}

/**
 * الغدُ من تاريخ ISO — أدنى تاريخٍ يقبله «أجّل» (الخادم يرفض اليوم 400).
 * حسابٌ بـUTC كنظائره في هذا الملفّ، والنصُّ الفاسدُ يعيد `''` فلا يُملأ الحقل.
 */
export function nextDayIso(iso: string): string {
  const ms = msFromIso(iso);
  if (ms === null) return '';
  return isoFromMs(ms + MS_PER_DAY);
}

/**
 * نظامُ الزبون الضريبيّ **المشترك** بين بنود رسالة — أو `null`.
 *
 * **`null` تعني «لا نظامَ واحداً لهذه الرسالة»**: بنودُ مستلِمٍ واحدٍ قد تعود
 * لزبونين بنظامين مختلفين، أو لبندٍ غاب نظامُ زبونه. والنظامُ يُقرأ في
 * `officeWhatsappLink` **للأرضيّ وحده** (‏`059/056` و`05` والدوليُّ يُصاغون بلا
 * مفتاح دولة) — فتمريرُ نظامٍ مخترَعٍ لرسالةٍ مختلطةٍ كان يفتح محادثةً بمفتاح
 * بلدٍ خطأ. والخادمُ يرسل النظامَ في كل بندٍ من زبونه (#280/ب).
 */
export function commonTaxSystem(
  items: readonly { tax_system?: string | null }[],
): string | null {
  if (!items.length) return null;
  const systems = items.map((item) => (item.tax_system ?? '').trim());
  const first = systems[0];
  if (!first) return null;
  return systems.every((system) => system === first) ? first : null;
}

// ── المواعيد (#281) ─────────────────────────────────────────────────────
//
// **ولا تسميةَ نوعٍ ولا حالةٍ هنا**: `kind_label` و`status_label` وتسمياتُ
// `kind_choices` تصل من الخادم، فلا جدولَ تسمياتٍ ثانٍ يفترق عنه. والباقي
// حسابُ عرض: تجميعُ المواعيد على أيامها للتقويم، وقيمةُ حقل الوقت، وشكلُ إدخالٍ
// من نصّ ISO بلا كائن `Date` منطقةً زمنية (كسائر تواريخ هذا الملف).

/** موعدُ زبون كما يعيده الخادم — بتاريخه ووقته وحالته. */
export interface OfficeAppointmentRow {
  id: number;
  client: { id: number; name: string };
  /** نظامُ زبونه الضريبيّ (`PS`/`IL`) أو `null` — مفتاحُ دولة `wa.me` وحده. */
  tax_system: string | null;
  kind: string;
  kind_label: string;
  /** ISO واعٍ بتوقيت الخادم — و`day`/`time` منه محلولَين. */
  scheduled_at: string;
  /** يومُ الموعد `YYYY-MM-DD` — مفتاحُ التقويم وفلتر «اليوم». */
  day: string;
  /** الوقتُ `HH:MM` — لا يبنيه المتصفّح من `scheduled_at`. */
  time: string;
  note: string;
  status: string;
  status_label: string;
  confirmed_at: string | null;
  cancelled_at: string | null;
  created_by: { id: number; name: string } | null;
  created_at: string;
}

/** تبويبُ المواعيد في ملفّ الزبون — بكلّ مواعيده ومنتقي أنواعها. */
export interface ClientAppointmentsPayload {
  client: { id: number; name: string };
  day: string;
  rows: OfficeAppointmentRow[];
  kind_choices: SettingChoice[];
}

/** قائمةُ مواعيد اليوم أو المكاتب كلِّها — بلا زبونٍ واحد. */
export interface AppointmentsListPayload {
  day: string;
  client: null;
  rows: OfficeAppointmentRow[];
  kind_choices: SettingChoice[];
}

/** عناصرُ التقويم مجموعةً بمفتاح يومها — المواعيدُ تُرسم بقراءة قاموسٍ لا بمسح. */
export function groupAppointmentsByDay(
  rows: readonly OfficeAppointmentRow[],
): Record<string, OfficeAppointmentRow[]> {
  const byDay: Record<string, OfficeAppointmentRow[]> = {};
  rows.forEach((row) => {
    (byDay[row.day] ??= []).push(row);
  });
  return byDay;
}

/** معرّفُ موعدٍ في الصفحة — يُمرَّر إليه ويُبرز عند القدوم من تنبيهٍ أو تقويم. */
export function officeAppointmentAnchorId(appointmentId: number): string {
  return `office-appointment-${appointmentId}`;
}

/**
 * قيمةُ `input[type=datetime-local]` من نصّ ISO — «YYYY-MM-DDTHH:MM».
 *
 * قصٌّ لا تحويل: الوقتُ المعروضُ هو وقتُ المكتب كما حلّه الخادم، فلا `Date` ولا
 * انزياحَ منطقةٍ يكسر الموعد ساعتين. والنصُّ الفاسدُ يعيد `''` فلا يُملأ الحقل.
 */
export function appointmentSlotValue(scheduledAt: string | null | undefined): string {
  const match = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/.exec(scheduledAt ?? '');
  return match ? `${match[1]}T${match[2]}` : '';
}

/** أصنافُ شارة حالة الموعد — اللونُ عرضٌ، والنصُّ من `status_label`. */
export function appointmentStatusClass(status: string): string {
  if (status === 'done') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300';
  }
  if (status === 'cancelled') {
    return 'border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400';
  }
  return 'border-teal-200 bg-teal-50 text-teal-700 dark:border-teal-900 dark:bg-teal-950/40 dark:text-teal-300';
}

/** هل يبقى على الموعد فعلٌ؟ المحجوزُ وحده يُؤكَّد ويُؤجَّل ويُلغى. */
export function isOpenAppointment(row: Pick<OfficeAppointmentRow, 'status'>): boolean {
  return row.status === 'scheduled';
}

/**
 * نتيجةُ «ابعت تأكيد»: السطرُ المحدَّث والنصُّ المرسَل ورقمُ المستلِم.
 *
 * الخادمُ يبني النصَّ ويكتب صفَّ السجلّ، والواجهةُ تفتح به واتساب إن عرف نظامَ
 * الزبون — والرابطُ يُبنى في `officeWhatsappLink` وحدها.
 */
export interface AppointmentConfirmation {
  appointment: OfficeAppointmentRow;
  log: { id: number };
  body: string;
  phone: string;
}

/**
 * نتيجةُ التأكيد بشكلها المعروض: النصُّ كما بناه الخادم، ورابطُ واتساب جاهزاً.
 *
 * **دالّةٌ واحدة لسطحَين** — بطاقةُ الموعد في ملفّ الزبون وشريحةُ التقويم: الرابطُ
 * يُبنى في `officeWhatsappLink` وحدها، ونظامُ الزبون من السطر العائد (ونظامُ
 * البطاقة احتياطاً لسطرٍ غاب نظامُ زبونه)، فلا نسخةَ ثانية تفترق عند أوّل تعديل.
 */
export function appointmentConfirmationView(
  result: AppointmentConfirmation,
  taxSystem?: string | null,
): { body: string; link: string | null } {
  return {
    body: result.body,
    link: officeWhatsappLink(
      result.phone,
      result.appointment.tax_system ?? taxSystem ?? null,
      result.body,
    ),
  };
}

// ── دفترُ الزبون (#286/ب) ────────────────────────────────────────────────────
//
// **ولا تسميةَ هنا**: نوعُ الدفتر (`kind_label`) ونوعُ الحركة (`kind_label`) ونوعُ
// الحساب (`account_type_label`) وطريقةُ الإدخال (`entry_method_label`) وقائمتُها
// كلّها تصل نصوصاً من الخادم. والباقي منطقُ عرضٍ حقيقيّ: نوعُ الدفتر **في تاريخ
// الحركة** (قاعدةُ `kind_on` نفسها في الخادم، بها تُقاس متوازنةُ المزدوج)،
// والانتقالُ الذي يسمح به الخادم، وتاريخُ حركةِ شهرٍ مضى، وأوراقُ «للإدخال»
// **مشتقّةً** من حمولتَي الأوراق والحركات: المشروعُ لا يخزّن «انأدخلت»، فورقةٌ
// مسجَّلةٌ «واصلة» **ولها رابطٌ في حركةٍ حيّة** هي المُدخلة وحدها.

/** اسم معامل شهر الإدخال — يفتح الدفتر على شهر ورقةٍ من «للإدخال». */
export const CLIENT_BOOK_MONTH_PARAM = 'month';

/** نوعا الدفتر — **قيمتان لا تسميتان**: «بسيط» و«مزدوج» يصلان في `kind_label`. */
export const BOOK_KIND_SIMPLE = 'simple';
export const BOOK_KIND_DOUBLE = 'double';

/** اختيارٌ من الخادم: قيمةٌ وتسمية (نوعُ الحركة ونوعُ الحساب). */
export interface BookChoice {
  value: string;
  label: string;
}

/**
 * سطرُ دفتر زبون كما يعيده الخادم.
 *
 * `writable` تعني «خدمةُ مسك الدفاتر نشطة» لا «الموظفُ يملك مفتاح الكتابة»:
 * الإيقافُ يُبقي الدفترَ للقراءة ويمنع الكتابة عليه (400 من الخادم)، والمفتاحُ
 * يحكم من يكتب. والشرطان مختلفان فلا يُدمجان.
 */
export interface ClientBookRow {
  client_id: number;
  client_name: string;
  kind: string;
  kind_label: string;
  opened_on: string;
  kind_changed_on: string | null;
  entry_method: string | null;
  entry_method_label: string;
  writable: boolean;
  /** أنواعُ الحركة وتسمياتها — تصل من الخادم، فلا جدولَ تسمياتٍ في الواجهة. */
  entry_kind_choices?: BookChoice[];
  /** أنواعُ الحساب وتسمياتها — في المسار المفرد وحده (#286/ب). */
  account_type_choices?: BookChoice[];
}

/**
 * حمولةُ `client-books/choices/`: تسمياتُ الأنواع الثلاثة من النموذج.
 *
 * **`book_kinds` لا `kind_choices`**: `kind` في هذا الموديول نوعُ **الدفتر**،
 * وأنواعُ الحركة `entry_kinds`. والتسميةُ المضلّلة هي التي جعلت زرَّ الانتقال
 * يبحث عن `double` في أنواع الحركة فيظهر دائماً «غيّر نوع الدفتر».
 */
export interface ClientBookChoicesPayload {
  book_kinds: BookChoice[];
  entry_kinds: BookChoice[];
  account_types: BookChoice[];
}

/** بندُ حركةٍ — والمبلغُ `null` حين لا يرى العضو المبالغ فيُعرض «—». */
export interface BookEntryLineRow {
  account_code: string;
  account_name: string;
  debit: string | null;
  credit: string | null;
  side_party: string;
}

/**
 * حركةُ دفترٍ كما يعيدها الخادم.
 *
 * `reverses` معرّفُ الأصل (هذه حركةٌ عكسية)، و`reversed_by` معرّفُ عكسها (هذه
 * حركةٌ عُكست). و**الحركةُ الحيّةُ ما كانت الاثنين `null`** — وحدها تُعدّ أوراقَها
 * مُدخلة، وعليها وحدها يُعرض «اعكس» (الخادم يردّ عكسَ العكس 400).
 */
export interface BookEntryRow {
  id: number;
  number: number;
  year: number;
  entry_date: string;
  kind: string;
  kind_label: string;
  memo: string;
  documents: number[];
  reverses: number | null;
  reversed_by: number | null;
  total_debit: string | null;
  total_credit: string | null;
  lines: BookEntryLineRow[];
}

/** حسابٌ في شجرة الزبون — نسختُه عن قالب المكتب/المنصّة، تُقرأ كوداً في الواجهة. */
export interface BookAccountRow {
  code: string;
  name: string;
  parent_code: string | null;
  account_type: string;
  account_type_label: string;
  is_system: boolean;
  is_active: boolean;
}

/**
 * نوعُ تقريرٍ متاحٌ لنوع الدفتر (#288/ب-١) — **يأتي من الخادم لا من قائمةٍ هنا**.
 * القاعدةُ في `book_reports.REPORTS_BY_BOOK_KIND` (البسيطُ لا يعطي ميزانَ
 * مراجعة، والمزدوجُ لا يعطي قبضاً ودفعاً)، وقائمةٌ في الواجهة تفترق عنها عند
 * أوّل تعديل فتعرض نوعاً يردّه الخادم 400.
 */
export interface ClientBookReportKind {
  kind: string;
  title: string;
  /** معاملاتٌ لا يقوم التقريرُ بغيرها — `statement` يحتاج حساباً أو طرفاً. */
  params: string[];
}

/** فهرسُ `client-books/<id>/reports/`: الأنواعُ المتاحة والعلامةُ المائية. */
export interface ClientBookReportsPayload {
  client: string;
  book_kind: string;
  book_kind_label: string;
  watermark: string;
  reports: ClientBookReportKind[];
}

/** فترةُ المستخرج — `YYYY-MM-DD`، ومنها تُبنى `from`/`to` في الطلب. */
export interface BookReportPeriod {
  from: string;
  to: string;
}

/** رابطُ مشاركةِ تقرير — `POST …/reports/<kind>/share/`، والانتهاءُ من الخادم. */
export interface ClientBookReportShare {
  url: string;
  expires_at: string;
}

/** صفُّ «للإدخال»: زبونٌ وشهرٌ وعددُ أوراقه — تجميعُ الخادم لا الواجهة. */
export interface PendingEntryRow {
  client_id: number;
  client_name: string;
  month: string;
  month_label: string;
  count: number;
  entry_method: string | null;
  entry_method_label: string;
}

export interface PendingEntryPayload {
  rows: PendingEntryRow[];
  /** مجموعُ الأوراق المنتظرة (لا عددُ الصفوف) — عدّادُ «اليوم» من الخادم. */
  total: number;
}

/** ورقةٌ واصلةٌ بلا إدخال — تُختار في نموذج الحركة. */
export interface PendingDocument {
  row_id: number;
  name: string;
  received_on: string | null;
}

/** مسوّدةُ بندٍ في نموذج الإدخال — نصوصُ الحقول كما كتبها الموظف. */
export interface BookLineDraft {
  account_code: string;
  debit: string;
  credit: string;
  side_party: string;
}

/**
 * عِلَلُ المسوّدة — رموزٌ لا نصوص: نصُّ الرسالة في الشاشة، والمنطقُ هنا يُختبر.
 * والثلاثةُ الأولى والأخيرةُ هي رسائلُ الخادم نفسها (‏`_prepare_lines`)، فلا
 * نرسل ما نعلم أنه سيُردّ.
 */
export type BookDraftProblem =
  | ''
  | 'no-lines'
  | 'no-account'
  | 'no-side'
  | 'two-sides'
  | 'invalid'
  | 'unbalanced';

/** مفتاحُ شهرٍ صالح (`YYYY-MM`) أو `''` — الفاسدُ لا يبلغ العنوانَ ولا الحقل. */
function validMonthKey(value: string | null | undefined): string {
  const raw = (value ?? '').trim();
  return /^\d{4}-(0[1-9]|1[0-2])$/.test(raw) ? raw : '';
}

/** مبلغٌ بالسنتات من نصّ الحقل — `null` لغير رقم. **ولا تخمينَ لفاصلة**: «1,5» مرفوضة. */
function amountCents(raw: string | null | undefined): number | null {
  const clean = (raw ?? '').trim();
  if (clean === '') return 0;
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return null;
  const [whole, fraction = ''] = clean.split('.');
  return Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
}

/** نوعُ الدفتر **في تاريخ الحركة** — القاعدةُ نفسها في `kind_on` الخادمية. */
export function bookKindOn(
  book: Pick<ClientBookRow, 'kind' | 'kind_changed_on'>,
  day: string,
): string {
  const changed = book.kind_changed_on;
  if (changed && day.slice(0, 4) < changed.slice(0, 4)) return BOOK_KIND_SIMPLE;
  return book.kind;
}

/**
 * النوعُ التالي في الانتقال — أو `null` حيث يرفضه الخادمُ دائماً.
 *
 * الرجوعُ من المزدوج إلى البسيط مرفوضٌ أبداً («طرفٌ من كل حركةٍ لا يُمحى»)،
 * فلا يُعرض زرُّ انتقالٍ مصيرُه الرفض. وبقيّةُ الشروط (سنةُ الفتح، وحركاتُ
 * السنة الجارية) تُكتشف في الخادم وحده فتُعرض رسالتُه كما هي.
 */
export function nextBookKind(book: Pick<ClientBookRow, 'kind'>): string | null {
  return book.kind === BOOK_KIND_DOUBLE ? null : BOOK_KIND_DOUBLE;
}

/**
 * تاريخُ حركةِ شهر: شهرُ اليوم ⇒ اليوم، وغيرُه ⇒ آخرُ يومٍ فيه.
 *
 * الرقمُ السنويّ للحركة يُشتقّ من تاريخها لا من تاريخ اليوم: ورقةُ آذار 2025
 * المُرحَّلة اليوم كانت تُكتب في تسلسل 2026 بلا هذا الحساب. والشهرُ الفاسدُ يعيد
 * `''` فيبقى الحقلُ فارغاً ولا يُحفظ تاريخٌ لم يره الموظف.
 */
export function entryDateForMonth(month: string, today: string): string {
  const key = validMonthKey(month);
  if (!key) return '';
  if (monthKeyOf(today) === key) return today.slice(0, 10);
  return monthKeyRange(key).end;
}

/** رابطُ تبويب «الدفتر» — وبشهرٍ يُفتح الإدخال على شهر ورقةٍ بعينها. */
export function clientBookPath(clientId: number, month?: string | null): string {
  const base = `${clientFilePath(clientId)}&${CLIENT_TAB_PARAM}=${CLIENT_BOOK_TAB}`;
  const key = validMonthKey(month);
  return key ? `${base}&${CLIENT_BOOK_MONTH_PARAM}=${key}` : base;
}

/** الشهرُ المطلوب من العنوان — `YYYY-MM` وحدها، وإلا `null`. */
export function bookMonthFromSearch(search: string): string | null {
  const params = new URLSearchParams(search.startsWith('?') ? search : `?${search}`);
  return validMonthKey(params.get(CLIENT_BOOK_MONTH_PARAM)) || null;
}

/** حركةٌ **حيّة**: ليست عكساً ولم تُعكس — تقيسها القاعدةُ نفسها في `_live_entries`. */
export function isLiveBookEntry(
  entry: Pick<BookEntryRow, 'reverses' | 'reversed_by'>,
): boolean {
  return entry.reverses === null && entry.reversed_by === null;
}

/** أوراقُ الحركات الحيّة — ما صار مُدخلاً، فلا يعود إلى «للإدخال». */
export function bookedDocumentIds(
  entries: readonly Pick<BookEntryRow, 'documents' | 'reverses' | 'reversed_by'>[],
): Set<number> {
  const booked = new Set<number>();
  entries.forEach((entry) => {
    if (!isLiveBookEntry(entry)) return;
    entry.documents.forEach((id) => booked.add(id));
  });
  return booked;
}

/**
 * أوراقُ شهرٍ في «للإدخال»: واصلةٌ (`received`) ولا رابطَ حيّ لها.
 *
 * المشروعُ لا يخزّن «انأدخلت» (د9): الورقةُ تخرج من القائمة لأن شرطَها صار
 * كاذباً. والاشتقاقُ هنا يستعمل الحمولتين القائمتين — شبكةَ الأوراق (بمعرّفات
 * صفوفها) وحركاتِ الدفتر (بأوراق كل حركة) — فلا نقطةَ جديدة تُخترع.
 *
 * **والقائمتان تُقرآن معاً**: `items` فيها الشهريّ وحده، و`annual` فيها السنويّ
 * و`period_start` لها أوّلُ السنة. الخادمُ يعدّ الواصلةَ السنوية في صفّ **كانون
 * الثاني** (`pending_entry_payload`)، فقراءةُ `items` وحدها كانت تفتح الصفَّ على
 * «ما في أوراق بانتظار الإدخال» فلا تُصفَّر أبداً. والورقةُ السنوية تُعرض في شهر
 * بدء فترتها وحدها — لا في كل شهر.
 */
export function pendingMonthDocuments(
  payload: Pick<ClientDocumentsPayload, 'items' | 'annual'>,
  booked: ReadonlySet<number>,
  month: string,
): PendingDocument[] {
  const key = validMonthKey(month);
  if (!key) return [];
  const rows: PendingDocument[] = [];
  payload.items.forEach((item) => {
    item.cells.forEach((cell) => {
      if (cell.row_id === null || booked.has(cell.row_id)) return;
      if (cell.status !== 'received') return;
      if (monthKeyOf(cell.month) !== key) return;
      rows.push({ row_id: cell.row_id, name: item.name, received_on: cell.received_on });
    });
  });
  payload.annual.forEach((row) => {
    if (booked.has(row.row_id)) return;
    if (row.status !== 'received') return;
    if (monthKeyOf(row.period_start) !== key) return;
    rows.push({ row_id: row.row_id, name: row.name, received_on: row.received_on });
  });
  return rows;
}

/** هل تُختار أوراقُ الحركة متعدّدةً؟ وضعُ «إدخال الشهر» وحده يسمح بذلك. */
export function multipleDocumentsAllowed(
  entryMethod: string | null | undefined,
): boolean {
  return entryMethod === 'monthly';
}

/**
 * عِلّةُ المسوّدة إن وُجدت — بالسنتات لا بالعشرية، مقارنةُ مجموعين تحتاج رقماً واحداً.
 *
 * والمزدوجُ وحده يُسأل عن التوازن: البسيطُ طرفٌ واحد لكل بند بالتعريف، فمطالبتُه
 * بالتوازن ترفض ورقاً صحيحة (القاعدةُ في `_assert_balanced`).
 */
export function bookDraftProblem(
  lines: readonly BookLineDraft[],
  options: { doubleEntry: boolean },
): BookDraftProblem {
  const written = lines.filter((line) => (
    line.account_code.trim() !== ''
    || line.debit.trim() !== ''
    || line.credit.trim() !== ''
  ));
  if (!written.length) return 'no-lines';
  let debitTotal = 0;
  let creditTotal = 0;
  for (const line of written) {
    if (!line.account_code.trim()) return 'no-account';
    const debit = amountCents(line.debit);
    const credit = amountCents(line.credit);
    if (debit === null || credit === null) return 'invalid';
    if (debit > 0 && credit > 0) return 'two-sides';
    if (debit === 0 && credit === 0) return 'no-side';
    debitTotal += debit;
    creditTotal += credit;
  }
  if (options.doubleEntry && debitTotal !== creditTotal) return 'unbalanced';
  return '';
}

/** مفتاحُ صفّ «للإدخال» — الزبونُ والشهر، لا العدُّ: الصفُّ هو هو بعد كل إدخال. */
export function pendingEntryRowKey(
  row: Pick<PendingEntryRow, 'client_id' | 'month'>,
): string {
  return `${row.client_id}|${row.month}`;
}

/** عددُ الزبائن الذين لهم ورقٌ بانتظار الإدخال — عدٌّ لا تكرار. */
export function pendingEntryClientCount(
  rows: readonly Pick<PendingEntryRow, 'client_id'>[],
): number {
  return new Set(rows.map((row) => row.client_id)).size;
}


// ── المسودّات وتبويبُ «الحساب» (#282/أ٢/٢) ─────────────────────────────────
//
// **النصوصُ من الخادم لا هنا**: `status_label` و`state_label` و`period_label`
// تصل جاهزةً من `models.py`/`payments.py`، ولا جدولَ تسمياتٍ محليّاً. ما في هذا
// القسم **حكمٌ لا نصّ**: أيُّ زرٍّ يظهر لأيّ حالة، وأيُّ صفٍّ يمرّ من الفلتر.

/** مفاتيحُ حالة المسودّة — أسماءُ الخادم (`FeeDraft.STATUS_*`) لا تسمياتِه. */
export const FEE_DRAFT_STATUS_DRAFT = 'draft';
export const FEE_DRAFT_STATUS_APPROVED = 'approved';
export const FEE_DRAFT_STATUS_CANCELLED = 'cancelled';

/** فلترُ شاشة «المسودّات»: الفارغ «الكل»، والباقي حالةٌ واحدة. */
export type FeeDraftFilter = '' | 'draft' | 'approved' | 'cancelled';

/**
 * الفلاترُ الأربعة بترتيبها في الشاشة — **المنتظرةُ أوّلاً**: هي ما يعمل عليه
 * المكتب اليوم، والمعتمدةُ والملغاةُ تاريخٌ يُراجَع.
 */
export const FEE_DRAFT_FILTERS: readonly { key: FeeDraftFilter; label: string }[] = [
  { key: FEE_DRAFT_STATUS_DRAFT, label: 'منتظرة' },
  { key: FEE_DRAFT_STATUS_APPROVED, label: 'معتمدة' },
  { key: FEE_DRAFT_STATUS_CANCELLED, label: 'ملغاة' },
  { key: '', label: 'الكل' },
];

/** صفوفُ المسودّات المطابقةُ للفلتر — تصفيةُ عرضٍ على قائمةٍ مقروءةٍ كاملة. */
export function filterFeeDrafts<T extends { status: string }>(
  rows: readonly T[],
  filter: FeeDraftFilter,
): T[] {
  if (!filter) return [...rows];
  return rows.filter((row) => row.status === filter);
}

/** عددُ المنتظرةِ في القائمة — «اعتمد الكل» يُطفأ على صفر. */
export function pendingFeeDraftCount(rows: readonly { status: string }[]): number {
  return rows.filter((row) => row.status === FEE_DRAFT_STATUS_DRAFT).length;
}

/**
 * أفعالُ صفّ المسودّة: الاعتمادُ والإلغاءُ **من حالة «مسودّة» وحدها**.
 *
 * المعتمدةُ لا تُعتمد ثانيةً (الخادم يردّ 400)، ولا تُلغى من هنا — إلغاءُ ورقتها
 * إجراءٌ على الفاتورة (`fees/invoices/<id>/cancel/`). وزرٌّ مصيرُه الرفض لا يظهر.
 */
export function feeDraftActions(status: string): { approve: boolean; cancel: boolean } {
  const pending = status === FEE_DRAFT_STATUS_DRAFT;
  return { approve: pending, cancel: pending };
}

/** أصنافُ Tailwind لشارة الحالة — **عرضٌ لا نصّ**: النصُّ من `status_label`. */
export function feeDraftStatusClass(status: string): string {
  if (status === FEE_DRAFT_STATUS_APPROVED) {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300';
  }
  if (status === FEE_DRAFT_STATUS_CANCELLED) {
    return 'border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400';
  }
  return 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300';
}

/**
 * نبرةُ رصيد الحساب: موجبٌ «عليه»، سالبٌ «له عندنا»، وصفرٌ مسدَّد.
 *
 * **والرابعُ للقناع**: `null` تعني «لا رؤيةَ للمبالغ» (#272) — لا صفراً. عرضُها
 * «مسدَّداً» يقول لصاحب المكتب إنّ الزبون سدّد وهو لم يرَ رقماً قطّ.
 */
export type AccountBalanceTone = 'owed' | 'refund' | 'settled' | 'masked';

export function accountBalanceTone(
  value: number | string | null | undefined,
): AccountBalanceTone {
  if (value === null || value === undefined || value === '') return 'masked';
  const amount = noticeAmount(value);
  if (amount > 0) return 'owed';
  if (amount < 0) return 'refund';
  return 'settled';
}

/** أصنافُ اللون لنبرة الرصيد — النصُّ لا يُبنى هنا. */
export function accountBalanceClass(tone: AccountBalanceTone): string {
  if (tone === 'owed') return 'text-rose-700 dark:text-rose-300';
  if (tone === 'refund') return 'text-emerald-700 dark:text-emerald-300';
  if (tone === 'masked') return 'text-slate-500 dark:text-slate-400';
  return 'text-slate-700 dark:text-slate-200';
}

// ── لوحة صاحب المكتب (#289) ────────────────────────────────────────────────
//
// **كلُّ رقمٍ من الخادم**: `due_total` مجموعُ «اللي عليه» من الدالّة الواحدة،
// و`late_total` و`red` محسوبان هناك — والواجهةُ ترسم ولا تعيد الحساب. والقناعُ
// يصل بـ`due_total: null` فيُعرض «—» بـ`formatMoney(value, '—')`.

/** مسار شاشة لوحة صاحب المكتب — مصدرٌ واحدٌ للموجّه والقائمة. */
export const OFFICE_DASHBOARD_PATH = '/accounting-office/dashboard';

/** صفُّ موظّفٍ في جدول اللوحة — `red` قرارُ الخادم لا شرطٌ هنا. */
export interface DashboardStaffRow {
  id: number;
  name: string;
  clients: number;
  late: number;
  missing_docs: number;
  overdue_clients: number;
  red: boolean;
}

/**
 * مجموعةُ «بانتظارك»: `count` من الخادم، و`action` مفتاحٌ تربطه الشاشة بفعلها.
 * المجموعةُ الفارغة لا تُرسَل أصلاً — الشاشةُ لا تعرض صفراً ثلاث مرّات.
 */
export interface DashboardWaitingGroup {
  kind: string;
  label: string;
  count: number;
  action: string;
}

export interface DashboardWaiting {
  total: number;
  groups: DashboardWaitingGroup[];
}

/** العتبتان كما تُقرآن من السجلّ — للعرض، والاحمرارُ محسوبٌ في الخادم. */
export interface DashboardThresholds {
  late_share_percent: number;
  late_ratio: string;
  office_average_late: string;
}

export interface DashboardPayload {
  day: string;
  /** مجموعُ «اللي عليه» — `null` لمن لا يملك `office.amounts.view`. */
  due_total: string | null;
  late_total: number;
  staff: DashboardStaffRow[];
  waiting: DashboardWaiting;
  single_person: boolean;
  thresholds: DashboardThresholds;
}

/** أفعالُ مجموعات «بانتظارك» — مفاتيحُ يرسلها الخادم، والشاشةُ تعرف ثلاثتها. */
export const DASHBOARD_ACTION_APPROVE_ALL = 'approve_all';
export const DASHBOARD_ACTION_OPEN_READY_TO_SEND = 'open_ready_to_send';
export const DASHBOARD_ACTION_OPEN_DEADLINE_RULES = 'open_deadline_rules';

/**
 * شرحُ عتبة الاحمرار كما يراه صاحبُ المكتب — من أرقام الخادم وحدها.
 *
 * ولا رقمَ مكتوبٌ هنا: تغييرُ العتبة في الإعدادات يغيّر النصَّ معه، وإلا قرأ
 * المكتبُ «20٪» وهو يعمل بـ5.
 */
export function dashboardThresholdHint(thresholds: DashboardThresholds): string {
  return (
    `الصفُّ يحمرّ حين يبلغ متأخّرُ الموظف ${thresholds.late_share_percent}٪ من زبائنه، `
    + `أو ${thresholds.late_ratio}× متوسط المكتب (${thresholds.office_average_late}).`
  );
}

/** اسمُ معامل العنوان الذي يقيّد قائمةَ الزبائن بمسؤولٍ واحد. */
export const RESPONSIBLE_QUERY_PARAM = 'responsible';

/** رابطُ قائمة الزبائن مقيَّدةً بموظّفٍ واحد — كبسةُ صفّه في اللوحة. */
export function clientsOfResponsiblePath(responsibleId: number): string {
  return `${OFFICE_CLIENTS_PATH}?${RESPONSIBLE_QUERY_PARAM}=${responsibleId}`;
}

/** معرّفُ المسؤول من نصّ العنوان — `null` للغياب أو لغير الرقم. */
export function responsibleFromSearch(search: string): number | null {
  const value = new URLSearchParams(search.startsWith('?') ? search : `?${search}`)
    .get(RESPONSIBLE_QUERY_PARAM);
  if (!value) return null;
  const id = Number(value);
  return Number.isInteger(id) && id > 0 ? id : null;
}
