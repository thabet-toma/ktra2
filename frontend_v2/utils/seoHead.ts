/**
 * دوالّ SEO الصرفة — بلا DOM ولا نظام ملفات، يستهلكها وقتُ البناء
 * (`seoBuildPlugin` في `vite.config.ts`) والمتصفّح (`App.tsx`)، ويحرسها
 * `utils/seoHead.test.ts`. مصدر الصفحات: `constants/publicPages.ts`.
 */
import type { PublicPage } from "../constants/publicPages";

const escapeHtml = (value: string): string =>
  value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** يستبدل `content` لوسم `<meta>` واحد معرَّف بـ`name`/`property` — ويرمي إن غاب. */
function setMetaContent(html: string, key: string, value: string): string {
  const tagRe = new RegExp(`<meta\\b[^>]*\\b(?:name|property)="${key.replace(/[.:]/g, "\\$&")}"[^>]*>`);
  const match = html.match(tagRe);
  if (!match) throw new Error(`seoHead: وسم <meta ${key}> غير موجود في القالب`);
  if (!/\bcontent="[^"]*"/.test(match[0])) throw new Error(`seoHead: وسم <meta ${key}> بلا content`);
  const replaced = match[0].replace(/\bcontent="[^"]*"/, () => `content="${escapeHtml(value)}"`);
  return html.replace(match[0], () => replaced);
}

/**
 * HTML الخام لصفحة عامة: يستبدل العنوان والوصف والـcanonical و`og:url`
 * (ومعها عنوان ووصف معاينة الروابط — زاحفو واتساب/فيسبوك لا ينفّذون JS).
 * يرمي إن غاب أيّ وسم: قالبٌ تغيّر يجب أن يُسقط البناء لا أن يُنتج صفحة كاذبة.
 */
export function applyPageHead(html: string, page: PublicPage): string {
  if (!/<title\b[^>]*>[\s\S]*?<\/title>/.test(html)) throw new Error("seoHead: وسم <title> غير موجود في القالب");
  // المستبدِلات دوالّ لا نصوص: `$&` في عنوانٍ ما كانت ستُفسَّر نمطَ استبدال.
  let out = html.replace(/(<title\b[^>]*>)[\s\S]*?(<\/title>)/, (_m, open: string, close: string) => `${open}${escapeHtml(page.title)}${close}`);

  const canonicalRe = /<link\b[^>]*\brel="canonical"[^>]*>/;
  const canonicalTag = out.match(canonicalRe);
  if (!canonicalTag || !/\bhref="[^"]*"/.test(canonicalTag[0])) {
    throw new Error("seoHead: وسم <link rel=\"canonical\"> غير موجود في القالب");
  }
  const canonicalReplaced = canonicalTag[0].replace(/\bhref="[^"]*"/, () => `href="${escapeHtml(page.canonical)}"`);
  out = out.replace(canonicalTag[0], () => canonicalReplaced);

  out = setMetaContent(out, "description", page.description);
  out = setMetaContent(out, "og:url", page.canonical);
  out = setMetaContent(out, "og:title", page.title);
  out = setMetaContent(out, "og:description", page.description);
  out = setMetaContent(out, "twitter:title", page.title);
  out = setMetaContent(out, "twitter:description", page.description);
  return out;
}

/** مسار الملف المصيَّر مسبقاً داخل `dist/`: `/` ← `index.html`، `/about-us` ← `about-us/index.html`. */
export function prerenderFilePath(path: string): string {
  const trimmed = path.replace(/^\/+|\/+$/g, "");
  return trimmed ? `${trimmed}/index.html` : "index.html";
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** `lastmod`: تاريخ آخر commit (`git log --format=%cs`) إن صلح، وإلا يوم البناء (UTC). */
export function resolveLastmod(gitDate: string | null | undefined, buildDate: Date): string {
  const trimmed = (gitDate || "").trim();
  if (ISO_DAY.test(trimmed)) return trimmed;
  return buildDate.toISOString().slice(0, 10);
}

/** `sitemap.xml` — `loc` و`lastmod` وحدهما (جوجل يتجاهل `changefreq` و`priority`). */
export function buildSitemapXml(entries: ReadonlyArray<{ loc: string; lastmod: string }>): string {
  const urls = entries
    .map((e) => {
      if (!ISO_DAY.test(e.lastmod)) throw new Error(`seoHead: lastmod غير صالح «${e.lastmod}» لـ${e.loc}`);
      return `  <url>\n    <loc>${escapeHtml(e.loc)}</loc>\n    <lastmod>${e.lastmod}</lastmod>\n  </url>`;
    })
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
}

/**
 * صفحة 404 لزائر غير مسجَّل؟ المسار **معروف** إن كان «/» أو صفحةً عامة أو
 * بدأ بجذرٍ من جذور التطبيق الداخلية (`/sales/...` لزائر بلا جلسة يبقى على
 * صفحة الهبوط/الدخول كما كان) — وما سوى ذلك غير موجود.
 */
export function isUnknownAnonymousPath(pathname: string, knownRoots: ReadonlySet<string>): boolean {
  const path = (pathname || "/").replace(/\/+$/, "") || "/";
  if (path === "/") return false;
  const root = path.split("/")[1] || "";
  return !knownRoots.has(root);
}

/** أول مقطع من مسار: `/accounting/coa` ← `accounting`. */
export function pathRoot(path: string): string {
  return (path || "").replace(/^\/+/, "").split("/")[0] || "";
}
