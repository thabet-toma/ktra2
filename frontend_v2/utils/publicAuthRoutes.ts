/**
 * ISSUE #55 — إغلاق باب التسجيل المنفصل: زائرٌ غير مسجَّل الدخول يفتح `authView`
 * خاصاً عبر رابطٍ مباشر (لا عبر أزرار الواجهة) من خريطة مسارٍ واحدة هنا — لا شرطٍ
 * متضخّم داخل `App`. باب تسجيل المحاسب القانوني الخارجي (`/accountant/signup`،
 * `/accountant/verify-email`) كان العنصر الوحيد في هذه الخريطة، وإغلاقه (بطلب
 * المالك) يعني حذفه من السِجلّ — لا تجاوزاً يتخطّاه.
 */
export type PublicAuthView = "signup";

/** خريطة مسار ← authView لزائر غير مسجَّل. فارغة اليوم عمداً — الباب مُغلَق. */
export const PUBLIC_AUTH_ROUTES: Readonly<Record<string, PublicAuthView>> = {};

const normalize = (pathname: string): string => {
  const path = (pathname || "/").replace(/\/$/, "");
  return path === "" ? "/" : path;
};

export function resolvePublicAuthView(pathname: string): PublicAuthView | null {
  return PUBLIC_AUTH_ROUTES[normalize(pathname)] ?? null;
}
