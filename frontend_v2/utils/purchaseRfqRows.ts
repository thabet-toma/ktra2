/**
 * ISSUE #114 (مواصفة #108 §١١) — سطرُ طلبيةٍ واحد مُحوَّلاً إلى صفّ حمولة.
 *
 * دالّةٌ صرفة واحدة يستهلكها كلٌّ من `purchaseRfqXlsx.ts` (ملفّ المورد)
 * و`purchaseRfqPrintPayload.ts` (حمولة الطباعة) — فلا نسخة ثانية من تحويل
 * `PurchaseRFQLineDto` إلى صفّ. الصفّ يحمل `estimatedPrice` دائماً؛ ما يحسم
 * خروجه من عدمه هو قائمة السماح في `procurementColumns.ts`
 * (`pickProcurementRowFields`)، لا هذه الدالّة.
 */
import type { PurchaseRFQLineDto } from '../services/procurementDocumentsApi.ts';

export interface RfqExportRow extends Record<string, unknown> {
  seq: number;
  product: string;
  specs: string;
  quantity: string | number;
  unitOfMeasure: string;
  /** داخليٌّ بحت — لا يخرج إلى أي سطح خارجي (#112 §١). موجودٌ هنا فقط ليُقصّه
   * بانيَ الحمولة عبر قائمة السماح، لا ليُنسخ يدوياً. */
  estimatedPrice: string | number | null;
}

export const rfqLineToRow = (line: PurchaseRFQLineDto, idx: number): RfqExportRow => {
  const quantity = Number(line.quantity);
  return {
    seq: line.seq ?? idx + 1,
    product: line.name_snapshot || line.product_name || '',
    specs: line.specs || '',
    quantity: Number.isFinite(quantity) ? quantity : (line.quantity ?? ''),
    unitOfMeasure: line.unit_of_measure || '',
    estimatedPrice: line.estimated_price ?? null,
  };
};
