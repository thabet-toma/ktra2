/**
 * ISSUE #271 — دوالُّ خالصة لموديول مكتب المحاسبة.
 *
 * **لا تسميةَ في هذا الملف.** كلُّ نصٍّ يعرضه الموديول يأتي من الخادم:
 * `status_label` و`language_label` و`label` (نوع التذكير) وتسميةُ قيمة الإعداد
 * (`value_label`) واختياراتُه (`choices`، ومنها أيام الأسبوع). نسخةٌ هنا تعني
 * مصطلحين لشيءٍ واحد يفترقان عند أول تعديل في السجلّ.
 *
 * الباقي هنا **منطقٌ حقيقيّ**: ما يُعرض لزبونٍ إسرائيليّ، واشتقاقُ «مخصَّص»،
 * وقراءةُ معرّف الزبون من العنوان وبناءُ رابطه. صرفةٌ بلا React كي تُختبر
 * بـ`node --test` في بوّابة `npm test`.
 */

/** مسار شاشة الزبائن — مصدرٌ واحدٌ للرابط وقراءته. */
export const OFFICE_CLIENTS_PATH = '/accounting-office/clients';

/** مسار شاشة إعدادات المكتب — بجانب مسار الزبائن، مصدرٌ واحدٌ لجدول المسارات. */
export const OFFICE_SETTINGS_PATH = '/accounting-office/settings';

/** اسم معامل العنوان الذي يحمل معرّف الزبون المفتوح. */
export const CLIENT_QUERY_PARAM = 'client';

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
