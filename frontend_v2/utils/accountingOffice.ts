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
import { userRoleLabel } from './userRoleLabel.ts';

/** مسار شاشة الزبائن — مصدرٌ واحدٌ للرابط وقراءته. */
export const OFFICE_CLIENTS_PATH = '/accounting-office/clients';

/** مسار شاشة إعدادات المكتب — بجانب مسار الزبائن، مصدرٌ واحدٌ لجدول المسارات. */
export const OFFICE_SETTINGS_PATH = '/accounting-office/settings';

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
