/**
 * ISSUE #114 (مواصفة #108 §١١) — حمولة طباعة الطلبية.
 *
 * تُبنى بقائمة سماح لا قائمة منع: `getPrintColumns('rfq')`
 * (`utils/procurementColumns.ts`) تُقصي `estimatedPrice` تلقائياً — هو غيرُ
 * مذكورٍ في `PRINT_ALLOWED_KEYS` أصلاً، فما لا يُبنى لا يُنسى إخفاؤه
 * («السعر التقديريّ غائبٌ — لا يدخل باني الحمولة أصلاً»). و«أقل سعر» ليس
 * حقلاً على `PurchaseRFQLineDto` إطلاقاً فلا حاجة لإقصائه هنا.
 *
 * مقعدها في `utils/` لا داخل مكوّن الطباعة (`.tsx`) لأن ملفّ JSX لا يمرّ من
 * `node --test` — نمط `utils/autocompleteRank.ts` نفسه.
 */
import { getPrintColumns, pickProcurementRowFields } from './procurementColumns.ts';
import { rfqLineToRow, type RfqExportRow } from './purchaseRfqRows.ts';
import type { PurchaseRFQDto } from '../services/procurementDocumentsApi.ts';

export type RfqPrintRow = Partial<RfqExportRow>;

/** أعمدة طباعة الطلبية — نفس أعمدة الشاشة مقصوصةً بقائمة السماح. */
export const purchaseRfqPrintColumns = () => getPrintColumns('rfq');

export const buildPurchaseRfqPrintRows = (
  rfq: Pick<PurchaseRFQDto, 'lines'>,
): RfqPrintRow[] => {
  const columns = purchaseRfqPrintColumns();
  return rfq.lines.map((line, idx) => pickProcurementRowFields(rfqLineToRow(line, idx), columns));
};
