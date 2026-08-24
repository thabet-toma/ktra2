/**
 * مشاركة المستندات برابط عام — عميل نقاط `/api/document-shares/`.
 *
 * الرابط العام نفسه (`/s/<token>`) صفحةٌ **خادمية** لا شاشة في هذا التطبيق:
 * زاحف واتساب لا ينفّذ JavaScript، فمعاينة الرابط تلزمها صفحة مُصيَّرة من
 * جانغو. هذا الملف يخاطب سطح الإدارة وحده — الإنشاء والقراءة والإبطال.
 */
import { apiGetList, apiPostObject } from "./restApi";

export type ShareDocType = "sales_invoice" | "sales_quotation";
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

/** روابط مستند بعينه، الأحدث أولاً. */
export function listDocumentShares(
  docType: ShareDocType,
  docId: number,
  tenantId?: number
): Promise<DocumentShare[]> {
  return apiGetList<DocumentShare>("document-shares/", {
    tenantId,
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
    { tenantId }
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
    { tenantId }
  );
}

/** رابط واتساب جاهز بنصّ مرافق — `wa.me` بلا رقم يفتح منتقي جهات الاتصال. */
export function whatsappShareUrl(message: string): string {
  return `https://wa.me/?text=${encodeURIComponent(message)}`;
}
