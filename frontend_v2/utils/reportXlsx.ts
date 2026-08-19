/**
 * تصدير التقرير إلى ملف Excel حقيقي (`.xlsx`) — لا CSV بامتداد آخر.
 *
 * لماذا لا يكفي CSV: المحاسب يفتح الملف **ليعيد الحساب فيه**. وCSV هنا يصدّر
 * المال منسّقاً («2,451.25») فيقرؤه Excel نصّاً في كثير من الإعدادات، فلا تعمل
 * عليه `SUM` ولا يُفرز. هنا تُكتب الأرقام **أرقاماً** بنمط عرضٍ عربي، فيبقى
 * الجدول قابلاً للحساب فوراً.
 *
 * التاريخ يُكتب نصّاً بشكله المحلي عمداً: خلية تاريخ حقيقية تُبنى من سلسلة
 * ISO تنزاح يوماً كاملاً بفارق المنطقة الزمنية — وهي نفس المزلقة التي يحرس
 * منها `utils/formatDate`.
 *
 * المكتبة تُحمَّل عند أول ضغطة تصدير (استيراد ديناميكي) فلا تدخل الحزمة
 * الأولى لمن لا يصدّر.
 */
import { formatDateLocalized } from './formatDate.ts';
import type { ReportColumnDto, ReportResultDto } from './reportFormat.ts';

export interface XlsxMeta {
  /** اسم الشركة كما يظهر في الترويسة. */
  company?: string;
  /** «الفترة من … إلى …» — كما تبنيه الشاشة. */
  period?: string;
  /** مَن ولّد التقرير — يأتي من الخادم (`generated_by`). */
  generatedBy?: string;
}

const MONEY_FORMAT = '#,##0.00';
const NUMBER_FORMAT = '#,##0.####';

/**
 * رقمٌ خالص في عمود نصّي — خانات ساعات كشف الساعات منها («8» / «7.5»).
 *
 * والشرط الثاني هو المهم: يُحوَّل النصّ رقماً **فقط إن عاد كما كان**. فرقم
 * الشيك «0042» شكله رقم، وتحويله يمحو أصفاره البادئة ويسلّم للمحاسب رقماً
 * ليس رقم شيكه — والزرّ اليوم على كل تقارير المنصة لا على الكشفين وحدهما.
 * ما لا يعود كما كان يبقى نصّاً كما هو.
 */
const looksNumeric = (raw: string): boolean =>
  /^-?\d+(\.\d+)?$/.test(raw) && String(Number(raw)) === raw;

export interface XlsxCell {
  value: string | number | null;
  numFmt?: string;
}

/**
 * قاعدة الخلية الواحدة — مفصولة عن بناء الملف كي تُختبر وحدها.
 *
 * فارغ → خلية فارغة (لا شرطة: الشرطة نصّ يكسر `SUM`) · مالٌ أو رقم → عدد ·
 * نصٌّ شكله رقم خالص → عدد أيضاً · تاريخ → نصّ محلي · ما عدا ذلك → نصّ.
 */
export const xlsxCell = (value: unknown, kind: ReportColumnDto['kind']): XlsxCell => {
  if (value === null || value === undefined || value === '') return { value: null };
  const raw = String(value);
  if (kind === 'date') return { value: formatDateLocalized(raw) };
  if (kind === 'money' || kind === 'number' || kind === 'int') {
    const parsed = Number(raw);
    if (Number.isFinite(parsed)) {
      return { value: parsed, numFmt: kind === 'money' ? MONEY_FORMAT : NUMBER_FORMAT };
    }
    return { value: raw };
  }
  if (looksNumeric(raw)) return { value: Number(raw), numFmt: NUMBER_FORMAT };
  return { value: raw };
};

/** أسطر الترويسة فوق الجدول — الشركة والفترة ومتى ولّده ومَن. */
export const xlsxHeaderLines = (result: ReportResultDto, meta: XlsxMeta): string[] => {
  const lines = [result.title];
  if (meta.company) lines.push(meta.company);
  if (meta.period) lines.push(meta.period);
  lines.push(`تاريخ التوليد: ${formatDateLocalized((result.generated_at || '').slice(0, 10))}`);
  if (meta.generatedBy) lines.push(`ولّده: ${meta.generatedBy}`);
  if (result.truncated) {
    lines.push(
      `تنبيه: عُرض ${result.rows.length} صفاً من ${result.total_rows ?? result.rows.length} — والإجماليات على الكل.`,
    );
  }
  return lines;
};

/** صفّ الإجماليات كما يُكتب، أو `null` حين لا إجمالي للتقرير. */
export const xlsxTotalsRow = (result: ReportResultDto): XlsxCell[] | null => {
  const totals = result.totals || {};
  if (Object.keys(totals).length === 0) return null;
  return result.columns.map((column, index) => {
    if (totals[column.key] !== undefined) return xlsxCell(totals[column.key], column.kind);
    return { value: index === 0 ? 'الإجمالي' : null };
  });
};

/** الملف كاملاً بايتاتٍ جاهزةً للتنزيل. */
export const reportToXlsxBuffer = async (
  result: ReportResultDto,
  meta: XlsxMeta = {},
): Promise<ArrayBuffer> => {
  const ExcelJS = (await import('exceljs')).default;
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet(result.title.slice(0, 28) || 'تقرير', {
    // ورقة عربية: تبدأ من اليمين، وصفّ العناوين مثبَّت فلا يضيع مع 31 عموداً.
    views: [{ state: 'frozen', rightToLeft: true, xSplit: 0, ySplit: 0 }],
    pageSetup: { orientation: result.columns.length > 10 ? 'landscape' : 'portrait' },
  });

  for (const line of xlsxHeaderLines(result, meta)) {
    const row = sheet.addRow([line]);
    row.font = { bold: row.number === 1, size: row.number === 1 ? 14 : 11 };
  }
  sheet.addRow([]);

  const headerRow = sheet.addRow(result.columns.map((c) => c.header));
  headerRow.font = { bold: true };
  headerRow.alignment = { horizontal: 'center' };
  sheet.views = [{ state: 'frozen', rightToLeft: true, ySplit: headerRow.number }];

  for (const row of result.rows) {
    const cells = result.columns.map((column) => xlsxCell(row[column.key], column.kind));
    const added = sheet.addRow(cells.map((cell) => cell.value));
    cells.forEach((cell, index) => {
      if (cell.numFmt) added.getCell(index + 1).numFmt = cell.numFmt;
    });
  }

  const totals = xlsxTotalsRow(result);
  if (totals) {
    const added = sheet.addRow(totals.map((cell) => cell.value));
    added.font = { bold: true };
    totals.forEach((cell, index) => {
      if (cell.numFmt) added.getCell(index + 1).numFmt = cell.numFmt;
    });
  }

  result.columns.forEach((column, index) => {
    sheet.getColumn(index + 1).width = Math.min(
      32, Math.max(10, column.header.length + 4),
    );
  });

  return workbook.xlsx.writeBuffer() as Promise<ArrayBuffer>;
};
