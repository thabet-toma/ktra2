
import { InvoiceItem } from './invoice';

export type PriceOfferStatus = 'initial' | 'pending_info' | 'under_discussion' | 'approved_for_shipping' | 'rejected';

export interface PriceOfferItem extends InvoiceItem {
    factoryImageUrl?: string;
    /** ISSUE #113 (مواصفة #108 §٤): وحدة القياس عمودٌ في الطلبية والعرض معاً —
     *  ورقةٌ تقول «١٠» ولا تقول «١٠ ماذا» تدعو المورد أن يُسعّر الصندوق بدل
     *  الحبّة، ولا يُكتشَف الفرق إلّا عند الاستلام. */
    unitOfMeasure?: string;
    /**
     * ISSUE #122: بندُ الطلبية الذي يُسعّره هذا السطر — نَسَبٌ صريح.
     *
     * المصفوفةُ (`comparison/`) تطابق به لا بترتيب السطر: العرضُ يُحرَّر بحرّية،
     * وحذفُ بندٍ من وسطه يُعيد ترقيم البقية — فمطابقةُ الترتيب تضع سعرَ الصنف
     * الثاني تحت الثالث بلا أن يقول شيءٌ في الشاشة. فارغٌ في العرض الحرّ، وفي
     * سطرٍ يزيده المالك ولم تطلبه الطلبية.
     */
    rfqLineId?: number;
    /**
     * ISSUE #133 §٤: نصّ المورّد نفسه على هذا البند — **للقراءة فقط**. يصل من
     * رابطه العام وحده (`submit_rfq_supplier_quote`)، ولا يُرسَل من الشاشة.
     */
    supplierNote?: string;
    /** تعليقنا نحن على ردّ المورّد — منفصلٌ بنيوياً عنه، وقابلٌ للكتابة هنا. */
    internalNote?: string;
    /** كاتبُ التعليق الداخليّ ووقتُه — يُختمان في الخادم لا في المتصفّح، فهما
     *  للعرض وحده: كلُّ تعديلٍ محليّ يمحوهما حتى يُعيدهما حفظٌ ناجح. */
    internalNoteBy?: string;
    internalNoteAt?: string;
}

/** T-IMPOFFER: ملف عرض السعر كما وصل من المورد (رابط مستضاف، لا محتوى). */
export interface PriceOfferAttachment {
    name: string;
    url: string;
    type?: string;
    size?: number;
}

/** T-OFFERSTATE: ملاحظة مؤرَّخة على العرض — `at`/`by` يُختمان في الخادم. */
export interface PriceOfferNote {
    text: string;
    at?: string;
    by?: string;
}

export interface PriceOffer {
    id: string;
    offerNumber: string;
    /** اسم ووصف الطلبية اللذان يعرّفان الغرض منها في القائمة والبحث. */
    orderName?: string;
    orderDescription?: string;
    supplierId: string;
    /** T-DRAFTPARTY: اسم مورد **مبدئي** غير مسجَّل — يُستعمل حين يكون
     *  `supplierId` فارغاً، ويصير شريكاً حقيقياً عند التحويل فقط. */
    supplierDraftName?: string;
    factoryName?: string;
    offerDate?: string;
    validUntil?: string;
    currency?: string;
    exchangeRate?: number;
    totalWeight?: number;
    totalVolume?: number;
    shipmentNotes?: string;
    shippingMethod?: string;
    shippingCost?: number;
    shippingIncluded?: boolean;
    deliveryDays?: number;
    productionDays?: number;
    paymentMethod?: string;
    warrantyDuration?: number;
    certificates?: string;
    quote_pdfs?: { name: string; url: string; size: number; type: string }[];
    quote_images?: string[];
    items: PriceOfferItem[];
    status: PriceOfferStatus;
    /** الحالة الأصلية في API SQL؛ تستخدم لقفل المستندات المحوّلة/المؤكدة. */
    backendStatus?: string;
    /** رقم المستند الناتج عن التحويل (فاتورة الشراء / الطلبية / الصفقة) — يُعرض
     *  بجانب الحالة كي يظهر أثر «تحويل» بدل أن يبدو كأنه لم يحدث. */
    linkedDocNumber?: string;
    /** T-PLINEAGE: نوع المستند الناتج ومعرّفه — الرقم وحده لا يُفتح بنقرة. */
    linkedDocKind?: "invoice" | "order" | "deal";
    linkedDocId?: number;
    /**
     * T-RECVIS: تقدّم استلام المستند المرتبط، جاهزاً للعرض.
     *
     * نصٌّ مبنيٌّ من أرقام الخادم لا حسبةٌ في الواجهة — «الباقي» رقمٌ واحد في
     * النظام كلّه (`purchase_invoice_receipt_summary`).
     */
    linkedDocReceiptText?: string;
    /** هل بقي شيء لم يصل؟ لتلوين النصّ تنبيهاً. */
    linkedDocHasRemaining?: boolean;
    /**
     * ISSUE #122: العرض مبذورٌ من طلبية — رقمها ورقمُ مستقبِلها فيها.
     *
     * يعبران مع الحمولة حتى نداء الإنشاء (`addPriceOfferToDb` ← `rfq`/
     * `rfq_recipient`) فيُربط العرضُ بمستقبِله على الخادم. عند **التعديل**
     * لا يُرسَلان: الربط محسومٌ عند الإنشاء ولا يُنقل عرضٌ من طلبيةٍ لأخرى.
     */
    rfqId?: number;
    rfqRecipientId?: number;
    /** T-IMPOFFER: مصدر التسعير — يُنقل إلى الصفقة عند التحويل. */
    alibabaLink?: string;
    /** T-IMPOFFER: رقم التواصل مع مندوب المورد لهذا العرض. */
    supplierContact?: string;
    /** T-IMPOFFER: سبب اعتبار العرض «غير ملائم» — إلزامي عند الرفض. */
    decisionReason?: string;
    /** T-IMPOFFER: ملفات العرض المرفوعة (PDF/صور). */
    attachments?: PriceOfferAttachment[];
    /** T-OFFERSTATE: دفتر ملاحظات مؤرَّخ (بدل ملاحظة واحدة تُدهس عند كل تعديل). */
    notesLog?: PriceOfferNote[];
    internalNotes?: string;
    subtotal: number;
    discountAmount: number;
    taxRate: number;
    taxAmount: number;
    taxType?: 'percentage' | 'amount';
    grandTotal: number;
    supplierSnapshot?: {
        tradeName?: string;
        alias?: string;
        address?: string;
        salesRepName?: string;
        salesRepPhone?: string;
    };
    createdBy: string;
    creatorName?: string;
    createdAt: string;
    updatedAt: string;
}
