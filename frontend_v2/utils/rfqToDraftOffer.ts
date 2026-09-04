/**
 * ISSUE #122: مستقبِلٌ في طلبية ← **عرض سعرٍ غير محفوظ** جاهزٌ للتحرير.
 *
 * المورّد الذي يُسعّر على الهاتف لا نافذةَ إدخالٍ خاصّة له: يُفتح محرِّرُ العرض
 * القائم (`PriceOfferForm`) معبّأً ببنود الطلبية وكمياتها ووحداتها **بلا
 * أسعار**، فيكتب المالك ما سمعه، ويحذف بندَ ما لا يحمله المورّد، ويختار
 * العملة وسعرَ صرفها — وكلُّها في المحرِّر أصلاً فلا تُبنى مرّةً ثانية. ولا
 * يُنشأ شيءٌ في الخادم قبل «حفظ».
 *
 * **نسبُ العرض يعبر مع الحمولة** (`rfqId`/`rfqRecipientId`): `buildPayload` في
 * المحرِّر يبدأ بـ`...offer` فيحملهما إلى `addPriceOfferToDb`، ومنها إلى
 * `rfq`/`rfq_recipient` على نداء الإنشاء. بلا ذلك يبقى العرضُ يتيماً فلا يظهر
 * مورّده في المصفوفة ولا تصحّ الترسيةُ عليه.
 *
 * **والسعرُ التقديريّ لا يُنقل** (#112 §١): رقمٌ داخليٌّ لا يخرج إلى ورقة
 * المورّد ولا إلى عرضه — نقلُه هنا يجعله «سعرَ المورّد» بعد أوّل حفظ.
 *
 * وحدة نقية (بلا متصفح ولا شبكة) كي تُختبر عبر `node --test` — على نمط
 * `utils/quotationToDraftDeal.ts`.
 */
import type { PriceOffer, PriceOfferItem } from "../types/offer";
import type {
  PurchaseRFQDto,
  PurchaseRFQLineDto,
  PurchaseRFQRecipientDto,
} from "../services/procurementDocumentsApi";

const num = (value: unknown): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

/**
 * بند طلبية ← بند عرض. البند المكتوب يدوياً (`product = null`) يصل **بلا**
 * `itemId` كما هو في الطلبية — عرضُ السعر يقبل المنتج المبدئي (T-DRAFTPARTY)،
 * ويتجسّد عند التحويل لا هنا.
 */
function lineToOfferItem(line: PurchaseRFQLineDto, idx: number): PriceOfferItem {
  const linked = line.product != null;
  return {
    id: `rfq-line-${line.id ?? idx + 1}`,
    itemId: linked ? String(line.product) : "",
    name: line.name_snapshot || line.product_name || "",
    categoryId: "",
    categoryName: "",
    specifications: line.specs || "",
    unitOfMeasure: line.unit_of_measure || "",
    imageUrls: [],
    quantity: num(line.quantity),
    // ISSUE #122: نَسَبُ السطر يبدأ هنا ويعبر إلى `rfq_line` عند الحفظ —
    // بلا ذلك تُطابِق المصفوفةُ بالترتيب، وحذفُ بندٍ من وسط العرض (وهو
    // الغرضُ من فتح المحرِّر أصلاً) يُزحزح كلَّ سعرٍ بعده صنفاً واحداً.
    rfqLineId: line.id,
    // السعر يبقى فارغاً — هذا كلُّ الغرض: المالك يكتب ما قاله المورّد.
    unitPrice: 0,
    totalPrice: 0,
  };
}

export function rfqToDraftOffer(
  rfq: PurchaseRFQDto,
  recipient: PurchaseRFQRecipientDto,
  /** اسم المورّد كما تعرضه القائمة — احتياطٌ حين لا يحمله المستقبِل نفسه. */
  supplierName = "",
): Partial<PriceOffer> {
  // ترتيب الطلبية هو ترتيب القراءة على الهاتف — `seq` لا ترتيب الاستجابة.
  const lines = [...(rfq.lines || [])].sort(
    (a, b) => (a.seq ?? 0) - (b.seq ?? 0),
  );

  return {
    status: "initial",
    supplierId: String(recipient.supplier),
    supplierDraftName: "",
    factoryName: recipient.supplier_name || supplierName,
    /* اسم العرض = رقم الطلبية: من يفتح العرض بعد شهرٍ يعرف من أين جاء، ومن
       يبحث في قائمة العروض يجدها كلَّها تحت رقم طلبيتها. */
    orderName: rfq.rfq_number || "",
    orderDescription: "",
    rfqId: rfq.id,
    rfqRecipientId: recipient.id,
    items: lines.map(lineToOfferItem),
    subtotal: 0,
    discountAmount: 0,
    taxRate: 0,
    taxAmount: 0,
    grandTotal: 0,
    internalNotes: "",
  };
}
