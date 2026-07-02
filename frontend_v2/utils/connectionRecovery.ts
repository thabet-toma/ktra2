/**
 * إصلاح اتصال عالق في متصفح المستخدم.
 *
 * البلاغ: كروم يفتح الواجهات لكن بلا بيانات (تعذّر الاتصال بالخادم)، ويعمل في
 * التصفّح الخفي فقط. السبب حالة عالقة في ملف تعريف المستخدم: نسخة Service Worker
 * قديمة و/أو Cache Storage قديم و/أو اتصال HTTP/3 (QUIC) معطوب على النطاق الفرعي
 * للـ API — والتصفّح الخفي يبدأ بحالة نظيفة فيعمل.
 *
 * هذه الدالة تمنح المستخدم مكافئ «التصفّح الخفي» بضغطة واحدة دون معرفة الحيلة:
 * إلغاء تسجيل كل عمّال الخدمة + مسح كل Cache Storage ثم إعادة تحميل الصفحة (تفتح
 * عامل خدمة/اتصالاً جديدين). لا تُمسّ `localStorage` (التوكن/الفرع النشط) كي يبقى
 * المستخدم مسجّلاً دخوله.
 *
 * كل خطوة معزولة في try/catch حتى لا يمنع فشل إحداها الوصول لإعادة التحميل النهائية.
 */
import { clientLogger } from "../services/logger";

export async function recoverConnection(): Promise<void> {
  clientLogger.info("connection.recovery.start");

  if ("serviceWorker" in navigator) {
    try {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.unregister()));
    } catch (e) {
      clientLogger.warn("connection.recovery.sw_failed", { error: String(e) });
    }
  }

  if ("caches" in window) {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    } catch (e) {
      clientLogger.warn("connection.recovery.cache_failed", { error: String(e) });
    }
  }

  clientLogger.info("connection.recovery.reload");
  window.location.reload();
}
