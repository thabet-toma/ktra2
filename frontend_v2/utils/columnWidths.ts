/**
 * عرض أعمدة الجداول على طريقة Excel — مصدر واحد لكل جدول قابل لتغيير العرض:
 * السحب من حافة العنوان، والعرض التلقائي من أطول نص، والحفظ في المتصفح كي
 * يعود العرض كما تركه المستخدم بعد الخروج من الشاشة.
 * يستهلكه `KitDenseTable` و`DevelopmentNotesPage`.
 */

export type SizeMap = Record<string, number>;

/** حارس: لا يختفي العمود مهما سحب المستخدم. */
export const MIN_COLUMN_WIDTH = 40;

/** حارس مقابل للصف — يبقى سطرٌ واحد ظاهراً على الأقل. */
export const MIN_ROW_HEIGHT = 28;

/** حدود العرض التلقائي (قبل أي تدخّل يدوي). */
export const AUTO_FIT_MIN = 80;
export const AUTO_FIT_MAX = 420;

const CHAR_WIDTH = 8;
const CELL_PADDING = 28;

type StorageLike = {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
};

const browserStorage = (): StorageLike | null => {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
};

/** مفتاح الحفظ = نطاق الجدول + أعمدته، فلا يخلط جدولان عرضيهما. */
export const columnWidthsKey = (scope: string, columnKeys: string[]): string =>
  `ktra_table_widths_${scope}_${columnKeys.join(',')}`;

/** مفتاح ارتفاعات الصفوف — مفاتيحه معرّفات الصفوف لا الأعمدة. */
export const rowHeightsKey = (scope: string): string => `ktra_table_row_heights_${scope}`;

export const readSizes = (key: string, storage?: StorageLike | null): SizeMap => {
  const store = storage ?? browserStorage();
  if (!store || !key) return {};
  try {
    const raw = store.getItem(key);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object') return {};
    const widths: SizeMap = {};
    for (const [colKey, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof value === 'number' && Number.isFinite(value)) widths[colKey] = value;
    }
    return widths;
  } catch {
    return {};
  }
};

export const writeSizes = (
  key: string, widths: SizeMap, storage?: StorageLike | null,
): void => {
  const store = storage ?? browserStorage();
  if (!store || !key) return;
  try {
    store.setItem(key, JSON.stringify(widths));
  } catch {
    // امتلاء/حظر التخزين لا يُسقط الشاشة — العرض يبقى لهذه الجلسة فقط.
  }
};

/** عرض العمود أثناء السحب. في RTL السحب لليسار يوسّع. */
export const nextColumnWidth = (startWidth: number, deltaX: number, rtl: boolean): number =>
  Math.max(MIN_COLUMN_WIDTH, Math.round(startWidth + deltaX * (rtl ? -1 : 1)));

/** ارتفاع الصف أثناء السحب — لأسفل يزيد في الاتجاهين (لا انعكاس في العمودي). */
export const nextRowHeight = (startHeight: number, deltaY: number): number =>
  Math.max(MIN_ROW_HEIGHT, Math.round(startHeight + deltaY));

/** عرض يتّسع لأطول سطر في العمود (العنوان محسوب معه) ضمن حدّي التلقائي. */
export const autoFitColumnWidth = (header: string, values: string[]): number => {
  const longest = [header, ...values].reduce((max, value) => {
    for (const line of String(value ?? '').split('\n')) {
      if (line.length > max) max = line.length;
    }
    return max;
  }, 0);
  return Math.min(AUTO_FIT_MAX, Math.max(AUTO_FIT_MIN, CELL_PADDING + longest * CHAR_WIDTH));
};
