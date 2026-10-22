/**
 * K4 — منطق نافذة «رابط للموظف» وصفحة العدّ الجوالية، دوالَّ صرفة بلا React.
 *
 * **ثلاث قواعد لا تُنسخ في المكوّنات:**
 * 1. **التقليم:** الشجرة تُعرض إلى العُقد التي في شجرتها الفرعية بندٌ واحد على
 *    الأقل من بنود الجرد (وأسلافها للسياق)، بينما **يُرسل** للخادم ما له بندٌ
 *    مباشر فقط — الخادم يرفض تصنيفاً بلا بندٍ في هذا الجرد.
 * 2. **الحالة:** التسمية العربية الواحدة التي تراها الشاشة، من `status` و
 *    `progress.counted` كما يعيدهما الخادم.
 * 3. **الإدخال:** أرقام العدّ تُكتب على الجوال بلوحة عربية — تُطبَّع إلى ASCII
 *    قبل الإرسال، والفراغ «مسح» لا صفر.
 */
import { categoryKey, type CategoryNodeLike } from './categoryTree.ts';
import { arabicCount, validateCountedQuantity } from './stocktake.ts';
import type { PublicStocktakeCountLine, StocktakeCountLinkRow } from '../types/inventory.ts';

/** ما يُعرض في الشجرة، وما يجوز إرساله — مجموعتان لا واحدة. */
export interface StocktakeCountScope {
  /** العُقد الظاهرة: التصنيفات المباشرة وأسلافها. */
  visible: number[];
  /** التصنيفات التي لها بندٌ مباشر في الجرد — وحدها تُرسل. */
  direct: number[];
}

/**
 * يبني نطاق الشجرة من تصنيفات بنود الجرد: كلُّ تصنيفٍ مباشر وأسلافه، محصوراً
 * في التصنيفات الموجودة فعلاً في القائمة المحمَّلة (تصنيفٌ محذوف لا يُعرض).
 */
export const stocktakeCountScopeIds = <T extends CategoryNodeLike>(
  categories: T[],
  directCategoryIds: ReadonlyArray<number>,
): StocktakeCountScope => {
  const byId = new Map(categories.map((category) => [categoryKey(category.id), category]));
  const visible = new Set<number>();
  const direct = new Set<number>();
  for (const rawId of directCategoryIds) {
    if (!Number.isFinite(rawId)) continue;
    let current = byId.get(categoryKey(rawId));
    if (!current) continue;
    direct.add(Number(rawId));
    const seen = new Set<string>();
    while (current && !seen.has(categoryKey(current.id))) {
      seen.add(categoryKey(current.id));
      visible.add(Number(current.id));
      current = current.parent == null ? undefined : byId.get(categoryKey(current.parent));
    }
  }
  const sorted = (values: Set<number>) => [...values].sort((a, b) => a - b);
  return { visible: sorted(visible), direct: sorted(direct) };
};

/**
 * ما يُرسَل فعلاً: المؤشَّر ∩ ما له بندٌ مباشر. تأشيرُ أبٍ يؤشّر أبناءه بصرياً،
 * وأبناؤه المباشرون هم ما يصل — لا معرّف الأب.
 */
export const filterCountLinkCategoryIds = (
  checkedIds: ReadonlyArray<number>,
  directIds: ReadonlyArray<number>,
): number[] => {
  const allowed = new Set(directIds);
  return [...new Set(checkedIds)].filter((id) => allowed.has(id)).sort((a, b) => a - b);
};

/** الحالة العربية الواحدة — `finished` تسبق التقدّم، والميّت يسبق المكتمل. */
export const countLinkStatusLabel = (
  status: StocktakeCountLinkRow['status'],
  counted: number,
): string => {
  if (status === 'revoked') return 'مُبطَل';
  if (status === 'expired') return 'منتهٍ';
  if (status === 'finished') return 'أنهى';
  if (status === 'active') return counted > 0 ? 'يعدّ' : 'لم يبدأ';
  // استنفدنا الحالات الأربع؛ سطرٌ جديد في السيرفر يوقف البناء هنا بدل أن يُعرض خاماً.
  const unreachable: never = status;
  return String(unreachable);
};

/** «كل الجرد» أو عدد التصنيفات بصياغةٍ عربية سليمة. */
export const countLinkScopeLabel = (categories: number[] | null): string => {
  if (categories == null) return 'كل الجرد';
  return arabicCount(categories.length, {
    one: 'تصنيف واحد',
    two: 'تصنيفان',
    few: 'تصنيفات',
    many: 'تصنيفاً',
  });
};

const ARABIC_INDIC = '٠١٢٣٤٥٦٧٨٩';
const EASTERN_ARABIC = '۰۱۲۳۴۵۶۷۸۹';

/**
 * أرقام عربية-هندية/فارسية ⇒ ASCII. محليّةٌ هنا عن قصد: لا دالّة عامّة مصدَّرة في
 * `utils/` تفعل هذا وحدها — `warranty.ts` (`phoneKeyOf`) تُسقط كل رمزٍ غير رقميّ
 * فتُفسد الكسور، فلا تُستخرج منها.
 */
const asciiDigits = (raw: string): string => {
  let text = raw;
  for (let index = 0; index < ARABIC_INDIC.length; index += 1) {
    text = text.split(ARABIC_INDIC[index]).join(String(index));
    text = text.split(EASTERN_ARABIC[index]).join(String(index));
  }
  return text;
};

/**
 * تطبيع خانة العدّ: أرقام عربية-هندية وفارسية إلى ASCII، و`٫`/`,` إلى نقطة.
 * لا يُفحص الصلاح بعدها — `parseCountedInput` وحدها تقرّر.
 */
export const normalizeCountedInput = (raw: string | null | undefined): string =>
  asciiDigits(String(raw ?? '')).replace(/[٫,]/g, '.').trim();

/** فاصلة آلافٍ مكتوبة: 1–3 أرقام ثم مجموعاتٌ ثلاثية — ليست كسراً. */
const THOUSANDS_TEXT = /^\d{1,3}(,\d{3})+$/;

/** حدّ عمود `StocktakeLine.counted_quantity`: `max_digits=18, decimal_places=4`. */
const MAX_COUNTED_INTEGER_DIGITS = 14;

export const INVALID_COUNTED_MESSAGE =
  'كمية غير صالحة — رقمٌ غير سالب بأربع منازل عشرية على الأكثر.';

export const THOUSANDS_SEPARATOR_MESSAGE =
  'لا تكتب فواصل الآلاف — استعمل النقطة للكسور فقط.';

/**
 * الشكل النصّي المرسَل: بلا أصفارٍ بادئة أو زائدة، وبلا نقطةٍ يتيمة — **بلا
 * `Number` أبداً**: `"12345678901234.5678"` تبقى حرفيةً ولا تُقرَّب.
 * القيمة غير الرقمية تُعاد كما هي (تُقارَن بالخادم نصّاً).
 */
export const canonicalQuantityText = (text: string | null | undefined): string => {
  const normalized = normalizeCountedInput(text);
  if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(normalized)) return normalized;
  const [rawInteger = '', rawFraction = ''] = normalized.split('.');
  const integer = rawInteger.replace(/^0+(?=\d)/, '') || '0';
  const fraction = rawFraction.replace(/0+$/, '');
  return fraction ? `${integer}.${fraction}` : integer;
};

export type ParsedCountedInput =
  | { ok: true; value: string | null }
  | { ok: false; error: string };

/**
 * قيمة الخانة كما تُرسَل: الفراغ `null` (مسح)، وإلا **نصٌّ** مطبَّع بلا أصفارٍ
 * زائدة. السالب وغير الرقمي وأكثر من أربع منازل أو 14 رقماً صحيحاً تُرفض
 * محلياً قبل أي طلب — والحكم في `validateCountedQuantity` وحدها لا نسخةً ثانية.
 */
export const parseCountedInput = (raw: string | null | undefined): ParsedCountedInput => {
  const source = String(raw ?? '').trim();
  // «1,250» فاصلةُ آلافٍ لا كسر 1.25: تُفحص على الأرقام المطبَّعة **قبل** تحويل
  // الفاصلة العشرية، وإلا صارت «1.250» بلا أثرٍ لما كتبه المستخدم.
  if (THOUSANDS_TEXT.test(asciiDigits(source))) {
    return { ok: false, error: THOUSANDS_SEPARATOR_MESSAGE };
  }
  const text = normalizeCountedInput(source);
  if (text === '') return { ok: true, value: null };
  if (!validateCountedQuantity(text)) {
    return { ok: false, error: INVALID_COUNTED_MESSAGE };
  }
  const value = canonicalQuantityText(text);
  const integerDigits = value.split('.')[0] ?? '';
  if (integerDigits.length > MAX_COUNTED_INTEGER_DIGITS) {
    return { ok: false, error: INVALID_COUNTED_MESSAGE };
  }
  return { ok: true, value };
};

/** فرق السطر المعروض: المعدود − رصيد النظام، أو `null` حين لا رقم صالح. */
export const countInputVariance = (
  systemQuantity: string | null | undefined,
  input: string | null | undefined,
): number | null => {
  const parsed = parseCountedInput(input);
  if (!parsed.ok || parsed.value == null) return null;
  const system = Number(systemQuantity);
  if (!Number.isFinite(system)) return null;
  return Number(parsed.value) - system;
};

export interface CountLineGroup<T> {
  key: string;
  label: string;
  lines: T[];
}

const UNCATEGORIZED_LABEL = 'بدون تصنيف';

/** تجميع صفحة العدّ بالمسار: أبجدياً، و«بدون تصنيف» أخيراً. */
export const groupCountLines = <T extends Pick<PublicStocktakeCountLine, 'category_path'>>(
  lines: T[],
): Array<CountLineGroup<T>> => {
  const groups = new Map<string, CountLineGroup<T>>();
  for (const line of lines) {
    const label = String(line.category_path || '').trim();
    const key = label || 'uncategorized';
    let group = groups.get(key);
    if (!group) {
      group = { key, label: label || UNCATEGORIZED_LABEL, lines: [] };
      groups.set(key, group);
    }
    group.lines.push(line);
  }
  const named = [...groups.values()].filter((group) => group.key !== 'uncategorized');
  named.sort((a, b) => a.label.localeCompare(b.label, 'ar'));
  const uncategorized = groups.get('uncategorized');
  if (uncategorized) named.push(uncategorized);
  return named;
};

/** القيمة المعروضة للسطر: المحلية إن وُجدت، وإلا ما وصل من الخادم. */
export const countLineInputValue = (
  line: Pick<PublicStocktakeCountLine, 'line_id' | 'counted_quantity'>,
  values: Record<number, string>,
): string => {
  const local = values[line.line_id];
  if (local !== undefined) return local;
  return line.counted_quantity == null ? '' : String(line.counted_quantity);
};

export interface CountLineFilter {
  query?: string;
  uncountedOnly?: boolean;
  values?: Record<number, string>;
}

/** بحثٌ في الاسم والرمز والبراند + «غير المعدود فقط» بالقيم الحيّة. */
export const filterCountLines = <T extends PublicStocktakeCountLine>(
  lines: T[],
  filter: CountLineFilter = {},
): T[] => {
  const query = String(filter.query ?? '').trim().toLocaleLowerCase('ar');
  const values = filter.values ?? {};
  return lines.filter((line) => {
    if (filter.uncountedOnly) {
      const parsed = parseCountedInput(countLineInputValue(line, values));
      const counted = parsed.ok && parsed.value != null;
      if (counted) return false;
    }
    if (!query) return true;
    const haystack = `${line.name} ${line.sku} ${line.brand}`.toLocaleLowerCase('ar');
    return haystack.includes(query);
  });
};

/** كم بنداً بلا عدّ — بالقيم الحيّة، والصفر كميةٌ معدودة. */
export const countUncounted = (
  lines: Array<Pick<PublicStocktakeCountLine, 'line_id' | 'counted_quantity'>>,
  values: Record<number, string>,
): number => {
  let total = 0;
  for (const line of lines) {
    const parsed = parseCountedInput(countLineInputValue(line, values));
    if (!parsed.ok || parsed.value == null) total += 1;
  }
  return total;
};
