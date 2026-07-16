/**
 * إصلاح اتصال عالق في متصفح المستخدم.
 *
 * البلاغ: كروم يفتح الواجهات لكن بلا بيانات (تعذّر الاتصال بالخادم)، ويعمل في
 * التصفّح الخفي فقط. السبب حالة عالقة في ملف تعريف المستخدم: نسخة Service Worker
 * قديمة و/أو Cache Storage قديم و/أو اتصال HTTP/3 (QUIC) معطوب على النطاق الفرعي
 * للـ API — والتصفّح الخفي يبدأ بحالة نظيفة فيعمل.
 *
 * هذه الدالة تعمل فقط بطلب صريح من المستخدم: تلغي عامل الخدمة الذي يغطي صفحة
 * K.T.R.A الحالية وتمسح كاشات K.T.R.A ذات البادئة `ktra-` ثم تعيد التحميل.
 * لا تمس تسجيلات أو كاشات أخرى على الأصل، ولا تُمسّ `localStorage`.
 *
 * كل خطوة معزولة في try/catch حتى لا يمنع فشل إحداها الوصول لإعادة التحميل النهائية.
 */
import { clientLogger } from "../services/logger";
import { isKtraCacheName, serviceWorkerScopeCoversPage } from "./connectionRecoveryPolicy";

export async function recoverConnection(): Promise<void> {
  clientLogger.info("connection.recovery.start");

  if ("serviceWorker" in navigator) {
    try {
      const regs = await navigator.serviceWorker.getRegistrations();
      const currentPage = window.location.href;
      const matching = regs.filter((r) =>
        serviceWorkerScopeCoversPage(r.scope, currentPage)
      );
      await Promise.all(matching.map((r) => r.unregister()));
    } catch (e) {
      clientLogger.warn("connection.recovery.sw_failed", { error: String(e) });
    }
  }

  if ("caches" in window) {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.filter(isKtraCacheName).map((k) => caches.delete(k)));
    } catch (e) {
      clientLogger.warn("connection.recovery.cache_failed", { error: String(e) });
    }
  }

  clientLogger.info("connection.recovery.reload");
  window.location.reload();
}
