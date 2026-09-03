/**
 * ISSUE #114 (مواصفة #108 §١١) — ملفّ Excel لطلبية الشراء الذي يخرج إلى
 * المورد: صفَّا عناوين (العبريّ فوق العربيّ، معتمَدان من المالك — تعليق
 * 2026-09-03 على #114)، ورقةٌ من اليمين، وعمودُ سعرٍ فارغ يملؤه المورد
 * («السعر المقترح» / `מחיר מוצע`).
 *
 * المكتبة `ExcelJS 4.4.0` القائمة (`reportXlsx.ts` نمطها) — استيرادٌ ديناميكي
 * عند أوّل تصدير فلا تدخل حزمة الإقلاع لمن لا يصدّر.
 *
 * الحمولة تُبنى بقائمة سماح لا قائمة منع — `getSupplierColumns('rfq')` +
 * `pickProcurementRowFields` (`utils/procurementColumns.ts`) فوق صفٍّ يبنيه
 * `utils/purchaseRfqRows.ts` (المشترك مع حمولة الطباعة). «السعر التقديري»
 * موجودٌ على الصفّ ولا يظهر في قائمة سماح المورد فلا يُنسخ — حارسه اختبار
 * السطر ٩٩٩٫٩٩ في `purchaseRfqXlsx.test.ts`.
 *
 * **العبرية عناوينُ أعمدةٍ فقط**: `RFQ_SUPPLIER_XLSX_HEADERS` هو الثابتُ
 * الوحيد الذي يحمل الكلمتين معاً — تبديلُهما لاحقاً سطرٌ واحد فيه. أسماءُ
 * الأصناف تخرج عربية/إنجليزية كما هي، بلا ترجمة ولا حقل `name_he`.
 *
 * **لا محارف RLM/LRM أبداً** — `alignment.readingOrder: 'rtl'` وحدها تكفي
 * لاتجاه الخلية. محرفٌ داخل *قيمة* الخلية يصير جزءاً من النصّ فيكسر
 * `VLOOKUP` وأيّ قراءةٍ آلية للورقة حين تعود من المورد.
 */
import { getSupplierColumns, pickProcurementRowFields } from './procurementColumns.ts';
import { rfqLineToRow, type RfqExportRow } from './purchaseRfqRows.ts';
import type { PurchaseRFQDto } from '../services/procurementDocumentsApi.ts';

export type RfqXlsxColumnKey = 'seq' | 'product' | 'specs' | 'quantity' | 'unitOfMeasure' | 'price' | 'notes';

export interface RfqXlsxHeaderDef {
  key: RfqXlsxColumnKey;
  /** العربية — الصفّ الثاني. */
  ar: string;
  /** העברית — الصفّ الأوّل (فوق العربية). */
  he: string;
}

/**
 * **مصدر التبديل الوحيد** للعناوين السبعة — معتمَدة من المالك حرفياً
 * (issue #114، تعليقا 2026-09-03). `price` و`notes` عمودان خارج مصفوفة
 * `ProcurementColumnKey` المشتركة: الأوّل فارغٌ يملؤه المورد، والثاني حقلُ
 * ملاحظات حرّ لا مصدر بيانات له في الطلبية.
 */
export const RFQ_SUPPLIER_XLSX_HEADERS: RfqXlsxHeaderDef[] = [
  { key: 'seq', ar: 'تسلسل', he: 'מס׳' },
  { key: 'product', ar: 'الصنف', he: 'פריט' },
  { key: 'specs', ar: 'المواصفات', he: 'מפרט' },
  { key: 'quantity', ar: 'الكمية', he: 'כמות' },
  { key: 'unitOfMeasure', ar: 'الوحدة', he: 'יחידה' },
  { key: 'price', ar: 'السعر المقترح', he: 'מחיר מוצע' },
  { key: 'notes', ar: 'ملاحظات', he: 'הערות' },
];

const PRICE_COLUMN_INDEX = RFQ_SUPPLIER_XLSX_HEADERS.findIndex((h) => h.key === 'price') + 1;

/**
 * صفّ المورد الفعلي — قائمة السماح تحسم ما يخرج. `estimatedPrice` موجودٌ
 * على `RfqExportRow` ولا يظهر في `getSupplierColumns('rfq')` فلا يُنسخ (نفس
 * الحارس البنيوي في `procurementColumns.test.ts`).
 */
export const buildRfqSupplierRows = (
  rfq: Pick<PurchaseRFQDto, 'lines'>,
): Partial<RfqExportRow>[] => {
  const columns = getSupplierColumns('rfq');
  return rfq.lines.map((line, idx) => pickProcurementRowFields(rfqLineToRow(line, idx), columns));
};

/**
 * إلزاميّ: `allowBlank: true` على عمود السعر — وإلا اشتكى Excel من كلّ خليةٍ
 * لم يملأها المورد بعد.
 */
const PRICE_DATA_VALIDATION = {
  type: 'decimal' as const,
  operator: 'greaterThanOrEqual' as const,
  formulae: [0],
  allowBlank: true,
};

/** ملفّ Excel كاملاً بايتاتٍ جاهزةً للتنزيل — الملفّ الذي يخرج إلى المورد. */
export const buildRfqSupplierXlsxBuffer = async (
  rfq: Pick<PurchaseRFQDto, 'rfq_number' | 'lines'>,
): Promise<ArrayBuffer> => {
  const ExcelJS = (await import('exceljs')).default;
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet('طلبية', {
    views: [{ rightToLeft: true }],
  });

  const heRow = sheet.addRow(RFQ_SUPPLIER_XLSX_HEADERS.map((h) => h.he));
  heRow.font = { bold: true };
  heRow.alignment = { horizontal: 'center', readingOrder: 'rtl' };

  const arRow = sheet.addRow(RFQ_SUPPLIER_XLSX_HEADERS.map((h) => h.ar));
  arRow.font = { bold: true };
  arRow.alignment = { horizontal: 'center', readingOrder: 'rtl' };

  const rows = buildRfqSupplierRows(rfq);
  for (const row of rows) {
    const cells = RFQ_SUPPLIER_XLSX_HEADERS.map((h) => {
      // عمودا السعر والملاحظات لا مصدر بيانات لهما — يخرجان فارغين دوماً
      // ليملأهما المورد.
      if (h.key === 'price' || h.key === 'notes') return null;
      const value = row[h.key as keyof RfqExportRow];
      return value === undefined || value === '' ? null : value;
    });
    const added = sheet.addRow(cells);
    added.alignment = { horizontal: 'right', readingOrder: 'rtl' };
    added.getCell(PRICE_COLUMN_INDEX).dataValidation = PRICE_DATA_VALIDATION;
  }

  sheet.columns.forEach((col, index) => {
    const header = RFQ_SUPPLIER_XLSX_HEADERS[index];
    col.width = Math.min(32, Math.max(10, (header?.he.length || 8) + 6));
  });

  return workbook.xlsx.writeBuffer() as Promise<ArrayBuffer>;
};
