/**
 * ISSUE #118 — صيانة مسودّات المستندات المحلية: مكنسة الـ٣٠ يوماً ومسح تسجيل
 * الخروج/مهلة الخمول (issue #109 §٥). القرار (من يُكنَس) في `utils/documentDraft.ts`
 * (`selectExpiredDraftKeys`) — هذا الملف وحده يلمس Dexie.
 */
import db from "./db";
import { selectExpiredDraftKeys } from "../../utils/documentDraft";

/** يُشغَّل مرّةً عند إقلاع التطبيق — مسودّةٌ عمرها ٣٠ يوماً فأكثر تُكنَس. */
export async function sweepExpiredDocumentDrafts(
  now: number = Date.now(),
): Promise<number> {
  try {
    const rows = await db.document_drafts.toArray();
    const doomed = selectExpiredDraftKeys(
      rows.map((r) => ({ key: r.key, updatedAt: r.updated_at })),
      now,
    );
    for (const key of doomed) {
      await db.document_drafts.delete(key);
    }
    return doomed.length;
  } catch {
    return 0; // IndexedDB غير متاحة (تصفّح خاص) — لا تُسقط الإقلاع
  }
}

/**
 * يمسح كل المسودّات المحلية — تسجيل الخروج أو مهلة الخمول (خصوصية: أسماء
 * عملاء وأسعار على جهاز مشترك، issue #109 §٥). يشمل `invoice_drafts` القديم
 * (`SalesInvoiceEditor`) أيضاً — نفس دافع الخصوصية، ونفس الجهاز المشترك.
 */
export async function clearAllDocumentDrafts(): Promise<void> {
  try {
    await db.document_drafts.clear();
    await db.invoice_drafts.clear();
  } catch {
    /* أفضل جهد — لا يجوز أن يعطّل تسجيل الخروج نفسه */
  }
}
