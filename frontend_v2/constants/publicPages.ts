/**
 * الصفحات العامة القابلة للفهرسة — **مصدر الحقيقة الوحيد** لـ SEO.
 *
 * يقرأ منه: وسوم الرأس في المتصفّح (`components/PublicPageHead.tsx`)، والتصيير
 * المسبق وقت البناء (`dist/<route>/index.html`) و`sitemap.xml` المولَّد
 * (إضافة `seoBuildPlugin` في `vite.config.ts`)، وحارس `robots.txt`
 * (`utils/seoHead.test.ts`). صفحةٌ تُضاف هنا تظهر في الأربعة معاً.
 *
 * `component` مسار ملف مكوّن الصفحة نسبةً إلى `frontend_v2/` — منه يُؤخذ
 * `lastmod` في الخريطة (تاريخ آخر commit مسّه).
 */
export const SITE_ORIGIN = "https://ktra-pro.tech";

export interface PublicPage {
  path: string;
  title: string;
  description: string;
  /** عنوان مطلق بلا شرطة مائلة في الآخر — مطابق حرفياً لـ`<loc>` في الخريطة. */
  canonical: string;
  component: string;
}

const canonicalFor = (path: string): string => (path === "/" ? SITE_ORIGIN : `${SITE_ORIGIN}${path}`);

const page = (path: string, title: string, description: string, component: string): PublicPage => ({
  path,
  title,
  description,
  canonical: canonicalFor(path),
  component,
});

export const PUBLIC_PAGES: readonly PublicPage[] = [
  page(
    "/",
    "K.T.R.A — نظام متكامل لإدارة الاستيراد والمبيعات والمخزون والمحاسبة",
    "K.T.R.A نظام إدارة أعمال عربي متكامل: فواتير المبيعات والمشتريات، المخزون والمستودعات، الاستيراد والشحن والتخليص الجمركي، والمحاسبة المترابطة — في منصة واحدة.",
    "components/LandingPage.tsx",
  ),
  page(
    "/about-us",
    "من نحن — نظام K.T.R.A لإدارة الاستيراد والمبيعات والمخزون والمحاسبة",
    "تعرّف على K.T.R.A: شركة عالمية النشاط في مجال التجارة والاستيراد، ومنصتها العربية لإدارة الاستيراد والمبيعات والمخزون والمحاسبة.",
    "components/AboutUs.tsx",
  ),
  page(
    "/contact",
    "تواصل معنا — نظام K.T.R.A",
    "تواصل مع أقسام K.T.R.A مباشرة: أسماء المسؤولين والبريد الإلكتروني وأرقام الواتساب لكل قسم.",
    "components/pages/Contact.tsx",
  ),
  page(
    "/gallery",
    "معرض الصور — نظام K.T.R.A",
    "معرض الصور العام لمنصة K.T.R.A — صور يشاركها فريق الشركة وزوّارها.",
    "components/PublicGallery.tsx",
  ),
  page(
    "/store",
    "المتاجر الإلكترونية — K.T.R.A",
    "لكل شركة على منصة K.T.R.A متجرها الإلكتروني الخاص برابطه المستقل — اطلب رابط المتجر من الشركة مباشرة.",
    "components/store/StoreIndexPage.tsx",
  ),
];

/** الصفحة العامة لمسارٍ ما (تُهمَل الشرطة المائلة الأخيرة)، أو `null`. */
export function findPublicPage(pathname: string): PublicPage | null {
  const path = (pathname || "/").replace(/\/+$/, "") || "/";
  return PUBLIC_PAGES.find((p) => p.path === path) ?? null;
}
