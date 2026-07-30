
import { InvoiceItem } from './invoice';

export type PriceOfferStatus = 'initial' | 'pending_info' | 'under_discussion' | 'approved_for_shipping' | 'rejected';

export interface PriceOfferItem extends InvoiceItem {
    factoryImageUrl?: string;
}

export type PriceOfferType = 'incoming_offer' | 'outgoing_offer' | 'incoming_order' | 'outgoing_order';

/** T-IMPOFFER: ملف عرض السعر كما وصل من المورد (رابط مستضاف، لا محتوى). */
export interface PriceOfferAttachment {
    name: string;
    url: string;
    type?: string;
    size?: number;
}

export interface PriceOffer {
    id: string;
    offerNumber: string;
    supplierId: string;
    factoryName?: string;
    offerType?: PriceOfferType;
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
    /** T-IMPOFFER: مصدر التسعير — يُنقل إلى الصفقة عند التحويل. */
    alibabaLink?: string;
    /** T-IMPOFFER: رقم التواصل مع مندوب المورد لهذا العرض. */
    supplierContact?: string;
    /** T-IMPOFFER: سبب اعتبار العرض «غير ملائم» — إلزامي عند الرفض. */
    decisionReason?: string;
    /** T-IMPOFFER: ملفات العرض المرفوعة (PDF/صور). */
    attachments?: PriceOfferAttachment[];
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
