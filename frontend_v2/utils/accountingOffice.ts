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
