/**
 * T113-2: عرض استيراد مقبول ← صفقة **غير محفوظة** جاهزة للتحرير.
 *
 * كان التحويل يقع في الخادم بضغطة واحدة (`convert_import_quotation_to_deal`):
 * تُنشأ الصفقة والمورد والأصناف قبل أن يرى المستخدم شيئاً. صار «تحويل إلى صفقة»
 * يفتح محرّر الصفقة معبّأً، ولا يُنشأ شيء قبل «حفظ». هذه الدالة هي خريطة الحقول
 * التي كانت داخل تلك الخدمة، منقولة كما هي إلى الواجهة — ومختبَرة وحدها.
 *
 * وحدة نقية (بلا متصفح ولا شبكة) كي تُختبر عبر `node --test`.
 */
import type { Deal, DealItem } from "../types/deal";
import type {
  SupplierQuotationDto,
  SupplierQuotationLineDto,
} from "../services/procurementDocumentsApi";

/** مورد مسجَّل كما تعرضه الواجهة — الاسم هو ما يُطابَق به اسم المورد المبدئي. */
export interface DraftDealSupplierRef {
  id: string;
  name: string;
  /** اسم بديل (الاسم القانوني عادةً)؛ الواجهة تعرض أحدهما بحسب ما يملأه المورد. */
  alias?: string;
}

const num = (value: unknown): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

/**
 * نفس قاعدة الخادم المحذوفة: تطابق **تام** بعد تشذيب الفراغات، لا مطابقة تقريبية.
 * الفرق أنّها كانت تُنشئ المورد بصمت عند عدم التطابق؛ الآن تُرشِّح الموجود فقط
 * ويبقى القرار للمستخدم أمام عينه.
 */
function matchSupplierByName(
  name: string,
  suppliers: DraftDealSupplierRef[],
): DraftDealSupplierRef | undefined {
  const target = name.trim();
  if (!target) return undefined;
  return (
    suppliers.find((s) => (s.name || "").trim() === target)
    ?? suppliers.find((s) => (s.alias || "").trim() === target)
  );
}

/**
 * بند العرض ← بند الصفقة. البند المكتوب يدوياً (`product = null`) يصل **بلا**
 * `itemId`: حارس G1 في نموذج الصفقة يمنع الحفظ حتى يربطه المستخدم أو يُنشئه
 * بـ«إضافة كصنف جديد» — بدل أن يخلقه النظام نيابةً عنه كما كان.
 */
function lineToDealItem(line: SupplierQuotationLineDto, idx: number): DealItem {
  const linked = line.product != null;
  const quantity = num(line.quantity);
  const unitPrice = num(line.unit_price);
  return {
    id: `qline-${idx + 1}`,
    itemId: linked ? String(line.product) : "",
    name: (linked ? line.product_name : "") || line.name_snapshot || "",
    seq: line.seq ?? idx + 1,
    categoryId: "",
    categoryName: "",
    specifications: line.description_line || "",
    imageUrls: [],
    quantity,
    unitPrice,
    totalPrice: num(line.line_total) || quantity * unitPrice,
  };
}

export function quotationToDraftDeal(
  quotation: SupplierQuotationDto,
  suppliers: DraftDealSupplierRef[] = [],
): Partial<Deal> {
  const draftName = (quotation.supplier_draft_name || "").trim();
  const matched =
    quotation.supplier == null ? matchSupplierByName(draftName, suppliers) : undefined;
  const totalWeightKg = num(quotation.total_weight_kg);
  const grandTotal = num(quotation.grand_total);

  return {
    status: "initial",
    dealDate: quotation.quotation_date,
    supplierId:
      quotation.supplier != null ? String(quotation.supplier) : (matched?.id || ""),
    factoryName:
      quotation.supplier != null
        ? (quotation.supplier_name || "")
        : (matched?.name || draftName),
    /* أثر المستند: الخادم يشتقّ `price_offer_id`/`original_offer_number` من العرض
       نفسه عند الحفظ، وهذه القيم للعرض في النموذج قبله. */
    sourceQuotationId: String(quotation.id),
    priceOfferId: String(quotation.id),
    originalOfferNumber: quotation.quotation_number,
    dealDescription: `طلبية من عرض سعر ${quotation.quotation_number}`,
    currencyId: quotation.currency,
    currencyRate: num(quotation.exchange_rate) || 1,
    incoterms: quotation.incoterms || undefined,
    shippingMethod: quotation.shipping_method || undefined,
    paymentMethod: quotation.payment_method || undefined,
    productionDays: quotation.production_days || 0,
    deliveryDays: quotation.delivery_days || 0,
    totalVolume: num(quotation.total_cbm),
    totalWeight: totalWeightKg,
    totalWeightKg,
    internalNotes: quotation.notes || "",
    alibabaOrderLink: quotation.alibaba_link || "",
    items: (quotation.lines || []).map(lineToDealItem),
    subtotal: num(quotation.subtotal),
    discountAmount: num(quotation.discount_amount),
    shippingCost: num(quotation.shipping_cost_estimate),
    shippingIncluded: Boolean(quotation.is_shipping_included),
    /* الصفقة الدولية بلا ضريبة — تُدفع عند التخليص (نفس ما كانت الخدمة تكتبه). */
    taxRate: 0,
    taxAmount: 0,
    totalAmount: grandTotal,
    remainingAmount: grandTotal,
    payments: [],
    installments: [],
    installmentPlanEnabled: false,
    statusHistory: [],
    quoteImages: [],
    quotePdfs: [],
  };
}
