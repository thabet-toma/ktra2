import { prepareHandoffUrl } from "./tabLink";

/** حدث «فُتح تبويب جديد» — يستمع له `AppLayout` وحده. */
export const TAB_OPENED_EVENT = "ktra:tab-opened";

export interface TabOpenedDetail {
  url: string;
  label?: string;
}

/**
 * G2: طلب فاتورة أو كشف حساب أو طباعة يجب أن يفتح في تبويب جديد —
 * لا يستبدل التبويب الحالي أبداً.
 *
 * مصدر حقيقة واحد بدل تكرار window.open في كل شاشة (DRY). يعمل مع مسارات
 * SPA الداخلية (BrowserRouter) ومع الروابط الخارجية على حد سواء.
 *
 * ويُعلن الفتحَ في **التبويب الحالي** أيضاً: المتصفّح قد يفتح التبويب في
 * الخلفية (إعداد المستخدم، أو ضغطة بالزرّ الأوسط)، فبلا إعلانٍ هنا يظنّ
 * المستخدم أن الضغطة لم تعمل ويكرّرها. الحدث يلتقطه `AppLayout` ويعرض رسالة
 * عابرة — والـutil يبقى بلا React.
 *
 * @param url   المسار أو الرابط.
 * @param label اسمٌ اختياري يُذكر في رسالة التأكيد («كرت الصنف»).
 * @returns true إذا فُتح التبويب، false إذا حجبه مانع النوافذ المنبثقة
 *          (ليقرّر المستدعي بديلاً).
 */
export function openInNewTab(url: string, label?: string): boolean {
  if (!url) return false;
  try {
    // المسار الداخلي يحمل رمز مناولة يخبر التبويب الجديد من أين جاء؛
    // الرابط الخارجي يمرّ كما هو.
    const href = prepareHandoffUrl(url);
    const a = document.createElement("a");
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.dispatchEvent(
      new CustomEvent(TAB_OPENED_EVENT, { detail: { url, label } }),
    );
    return true;
  } catch (e) {
    console.error("Failed to open tab via anchor", e);
    return false;
  }
}
