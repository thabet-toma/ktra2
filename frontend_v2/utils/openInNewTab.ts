/**
 * G2: طلب فاتورة أو كشف حساب أو طباعة يجب أن يفتح في تبويب جديد —
 * لا يستبدل التبويب الحالي أبداً.
 *
 * مصدر حقيقة واحد بدل تكرار window.open في كل شاشة (DRY). يعمل مع مسارات
 * SPA الداخلية (BrowserRouter) ومع الروابط الخارجية على حد سواء.
 *
 * @returns true إذا فُتح التبويب، false إذا حجبه مانع النوافذ المنبثقة
 *          (ليقرّر المستدعي بديلاً).
 */
export function openInNewTab(url: string): boolean {
  if (!url) return false;
  const win = window.open(url, "_blank", "noopener,noreferrer");
  if (win) {
    win.opener = null;
    return true;
  }
  return false;
}
