/**
 * تسمياتُ نوع المستند وحركةِ المخزون — **قاعدةٌ واحدةٌ لا ثلاثُ نسخ** (#214-ب).
 *
 * بلاغُ المالك (#214-ب): المرتجعُ يظهر في حركة المخزون باسم مستند البيع
 * نفسِه. ونصُّه حرفيّاً في `docs/CHANGELOG.md`: اسمُ المستند مُقنَّنٌ في المعجم
 * (`utils/terms.ts`) فلا يُكتب في ملفٍّ آخرَ حرفيّاً — يحرسه حارسُ المعجم.
 *
 * السببُ أنّ مرتجعَ البيع يكتب حركتَه بـ`movement_type="RETURN_IN"` (صحيح)
 * و`reference_type="SALE"` — **كالبيعة تماماً**، لأنّه فعلاً صفُّ
 * `SalesInvoice` بنوعٍ آخر. وثلاثةُ مواضعَ في الواجهة كانت تشتقّ التسميةَ من
 * المرجع لا من نوع الحركة، فتكتب «مبيعات» و«بيع» على ما هو مرتجع.
 *
 * والبياناتُ لم تكن خاطئةً قطّ — العرضُ وحدَه كان يكذب. ولذلك لا هجرةَ هنا ولا
 * لمسَ صفٍّ تاريخيّ: كلُّ مرتجعٍ قديمٍ يُقرأ صحيحاً بمجرّد تصحيح القراءة.
 *
 * وكُتبت هنا لا في المكوّنات الثلاثة: نسخةٌ ثانيةٌ من قاعدةٍ هي عطبُ تباعدٍ
 * مؤجَّل — يُصلَح أحدُ المواضع ويبقى الآخران يكذبان بلا أن يشتكي شيء.
 */
type RelatedInvoice = {
  document_type: string;
  invoice_kind?: string | null;
};

type StockLedgerMovement = {
  reference_type: string | null;
  movement_type: string | null;
  movement_type_label: string;
};

type StockMovementReference = {
  reference_type?: string | null;
  movement_type?: string | null;
  reference_type_display?: string | null;
};

const isReturnMovement = (movementType: string | null | undefined): boolean =>
  movementType === 'RETURN_IN' || movementType === 'RETURN_OUT';

export const relatedInvoiceTypeLabel = (invoice: RelatedInvoice): string => {
  if (invoice.document_type === 'SALES_INVOICE') {
    return invoice.invoice_kind === 'sale_return' ? 'مرتجع بيع' : 'بيع';
  }
  return 'شراء';
};

export const stockLedgerMovementTypeLabel = (movement: StockLedgerMovement): string => {
  if (isReturnMovement(movement.movement_type)) return movement.movement_type_label;
  if (movement.reference_type === 'PURCHASE_INVOICE') return 'مشتريات';
  if (movement.reference_type === 'SALE') return 'مبيعات';
  return movement.movement_type_label;
};

export const stockMovementReferenceLabel = (movement: StockMovementReference): string => {
  if (movement.reference_type === 'SALE' && isReturnMovement(movement.movement_type)) {
    return 'مرتجع بيع';
  }
  return movement.reference_type_display || '—';
};
