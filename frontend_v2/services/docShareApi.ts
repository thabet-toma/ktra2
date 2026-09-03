/**
 * مشاركة المستندات برابط عام — عميل نقاط `/api/document-shares/`.
 *
 * الرابط العام نفسه (`/s/<token>`) صفحةٌ **خادمية** لا شاشة في هذا التطبيق:
 * زاحف واتساب لا ينفّذ JavaScript، فمعاينة الرابط تلزمها صفحة مُصيَّرة من
 * جانغو. هذا الملف يخاطب سطح الإدارة وحده — الإنشاء والقراءة والإبطال.
 */
import { apiGetList, apiPostObject } from "./restApi";
import { resolveTenantId } from "../utils/tenantContext";

/**
 * أنواع المستندات القابلة للمشاركة — **مرآة `docshare/documents/DOC_TYPES`**.
 *
 * جانبان بجمهورين: أنواع البيع يفتحها الزبون وتلزمها `sales.document.share`،
 * وأنواع الشراء يفتحها المورّد وتلزمها `purchase.document.share`. الخادم هو
 * من يفرض ذلك — وهذا النوع يمنع الخطأ المطبعي قبل أن يصل إليه.
 */
export type ShareDocType =
  // جانب البيع — جمهوره الزبون، ويلزمه `sales.document.share`
  | "sales_invoice"
  | "sales_quotation"
  | "sales_order"
  | "delivery_order"
  | "customer_payment"
  | "credit_debit_note"
  // ما بعد البيع — جمهوره الزبون، ووحدته مرخّصة
  | "warranty_card"
  | "service_order"
  // جانب الشراء — جمهوره المورّد، ويلزمه `purchase.document.share`
  | "purchase_invoice"
  | "purchase_order"
  | "logistics_deal"
  | "supplier_quotation"
  | "local_purchase_invoice"
  | "supplier_payment"
  // ISSUE #115: رابط المورّد الخاص على طلب عرض السعر — لا يقبل قراراً (accept/reject)
  // بل تسعيراً (`quote`)، انظر `docs/modules/docshare.md` §«تسعير المورّد».
  | "purchase_rfq";
export type ShareDecision = "" | "accepted" | "rejected";

export interface DocumentShare {
  id: number;
  doc_type: ShareDocType;
  doc_id: number;
  token: string;
  public_url: string;
  expires_at: string;
  revoked_at: string | null;
  is_live: boolean;
  view_count: number;
  first_viewed_at: string | null;
  last_viewed_at: string | null;
  decision: ShareDecision;
  decided_at: string | null;
  decided_name: string;
  decided_note: string;
  created_at: string;
  created_by_name: string;
}

/** مُدد الصلاحية المسموحة — مرآة `ALLOWED_EXPIRY_DAYS` في `docshare/services.py`. */
export const SHARE_EXPIRY_OPTIONS = [
  { days: 7, label: "٧ أيام" },
  { days: 30, label: "٣٠ يوماً" },
  { days: 90, label: "٩٠ يوماً" },
] as const;

export const DEFAULT_SHARE_EXPIRY_DAYS = 30;

/**
 * الشركة تُحلّ هنا لا عند المستدعي — نفس نمط `afterSalesApi.ts`.
 *
 * تركُها خياراً على كل نداء كان يعني أن كل نقطة التحام تتذكّر تمريرها،
 * ونسيانُها لا يُكسِر البناء ولا الأنواع: يُحذف الرأس بصمت فيردّ الخادم
 * «لم يتم تحديد الشركة» وقت التشغيل وحده. الوحدة تملك هذا الشأن.
 */
const tenantOpts = (tenantId?: number) => ({ tenantId: tenantId ?? resolveTenantId() });

/** روابط مستند بعينه، الأحدث أولاً. */
export function listDocumentShares(
  docType: ShareDocType,
  docId: number,
  tenantId?: number
): Promise<DocumentShare[]> {
  return apiGetList<DocumentShare>("document-shares/", {
    ...tenantOpts(tenantId),
    query: { doc_type: docType, doc_id: docId },
  });
}

/**
 * ينشئ رابطاً — أو يعيد الحيّ القائم إن وُجد (الخادم يقرّر، لا الواجهة).
 *
 * لعرض سعر ما زال مسودة: هذا الاستدعاء **ينقله إلى «أُرسل»**، وبدونه يسقط
 * قبول الزبون على آلة حالات العرض. النافذة تُعلن ذلك قبل الضغط.
 */
export function createDocumentShare(
  docType: ShareDocType,
  docId: number,
  days: number = DEFAULT_SHARE_EXPIRY_DAYS,
  tenantId?: number
): Promise<DocumentShare> {
  return apiPostObject<DocumentShare>(
    "document-shares/",
    { doc_type: docType, doc_id: docId, days },
    tenantOpts(tenantId)
  );
}

/** يُبطل الرابط فوراً. الصفّ يبقى — «من شارك ومتى» سؤالٌ يُسأل بعد الإبطال. */
export function revokeDocumentShare(
  shareId: number,
  tenantId?: number
): Promise<DocumentShare> {
  return apiPostObject<DocumentShare>(
    `document-shares/${shareId}/revoke/`,
    {},
    tenantOpts(tenantId)
  );
}

/** رابط واتساب جاهز بنصّ مرافق — `wa.me` بلا رقم يفتح منتقي جهات الاتصال. */
export function whatsappShareUrl(message: string): string {
  return `https://wa.me/?text=${encodeURIComponent(message)}`;
}
