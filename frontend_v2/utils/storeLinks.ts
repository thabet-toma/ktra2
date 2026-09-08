/**
 * روابط المتجر العام — المشاركة على واتساب ونسخ رابط المنتج.
 *
 * منطق خالص بلا React كي يُختبَر وحده: رابط `wa.me` هو الطريق الوحيد بين
 * الزائر وصاحب المتجر (لا سلة ولا دفع)، فرقمٌ يُبنى خطأً يعني زبوناً ضائعاً
 * بلا أي رسالة خطأ تظهر لأحد.
 */

/** مسار واجهة المتجر — نفس النمط الذي يقرؤه `index.tsx`. */
export function storeHomePath(slug: string): string {
  return `/store/${encodeURIComponent(slug)}`;
}

/**
 * جزءٌ نصّيٌّ صالحٌ لرابط — يُستعمَل زخرفةً بعد المعرّف الحاكم، لا مصدرَ حقيقة.
 * لا سيرفر يبنيه ولا يقرؤه؛ تصحيح إملاءٍ في الاسم لا يكسر رابطاً قديماً لأن
 * المعرّف وحده يُقرأ عند الفتح (انظر `parseLeadingId` أدناه).
 */
export function slugifyForUrl(text: string): string {
  return text
    .trim()
    .replace(/\s+/g, "-")
    .replace(/[^\p{L}\p{N}-]+/gu, "")
    .replace(/-{2,}/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

/**
 * رابط صفحة المنتج داخل متجر الشركة — نفس النمط الذي يقرؤه `index.tsx`.
 * `name` اختياريّ: بلا اسمٍ يبقى الرابط `/p/<id>` كما كان دائماً (توافقٌ خلفي
 * حرفيّ)؛ معه يصير `/p/<id>-<slug>` — والمعرّف وحده هو ما يُقرأ عند الفتح.
 */
export function storeProductPath(
  slug: string,
  productId: number | string,
  name?: string | null,
): string {
  const slugPart = name ? slugifyForUrl(name) : "";
  const segment = slugPart ? `${productId}-${slugPart}` : String(productId);
  return `${storeHomePath(slug)}/p/${encodeURIComponent(segment)}`;
}

/**
 * يقرأ المعرّف الحاكم من جزء المسار `<id>` أو `<id>-<slug>` — الشقّ النصّيّ
 * زخرفةٌ محضة (انظر `slugifyForUrl` أعلاه)، فرابطٌ قديمٌ بلا شقّ يبقى يعمل.
 */
export function parseLeadingId(param: string): string {
  const match = /^(\d+)/.exec((param || "").trim());
  return match ? match[1] : param;
}

/** رابط صفحة الفئة — نفس نمط `storeProductPath` (معرّفٌ حاكمٌ + زخرفةٌ نصّية). */
export function storeCategoryPath(
  slug: string,
  categoryId: number | string,
  name?: string | null,
): string {
  const slugPart = name ? slugifyForUrl(name) : "";
  const segment = slugPart ? `${categoryId}-${slugPart}` : String(categoryId);
  return `${storeHomePath(slug)}/cat/${encodeURIComponent(segment)}`;
}

/**
 * الرابط الذي ينسخه صاحب المتجر من شاشة «متجري» ويرسله على واتساب.
 * الأصل من المتصفح لا من ثابت — نفس قاعدة `storeProductUrl` أدناه، فالمنصة
 * تُخدَم من أكثر من مضيف (تطوير، مجال الإنتاج) ورابطٌ مثبَّت في الكود يكذب.
 */
export function storeHomeUrl(origin: string, slug: string): string {
  return `${origin.replace(/\/+$/, "")}${storeHomePath(slug)}`;
}

/** الرابط المطلق الذي يُنسَخ أو يُرسَل — الأصل يأتي من المتصفح لا من ثابت. */
export function storeProductUrl(
  origin: string,
  slug: string,
  productId: number | string,
  name?: string | null,
): string {
  return `${origin.replace(/\/+$/, "")}${storeProductPath(slug, productId, name)}`;
}

/**
 * رقم واتساب دولي من هاتف الشركة كما أدخله صاحبها — أو `null` صراحةً.
 *
 * `wa.me` لا يقبل إلا رقماً دولياً بلا رموز. الرقم المحلي («0791234567») لا
 * يمكن إكماله هنا: تخمين مفتاح الدولة يفتح محادثة مع رقم شخصٍ آخر في بلد آخر.
 * لذلك نُعيد `null` بدل رابط يبدو صالحاً ويفشل عند الضغط، ويعرض المتصل زر
 * اتصال عادي بدلاً منه.
 */
export function whatsappNumber(phone?: string | null): string | null {
  const digits = (phone || "").replace(/\D/g, "");
  // بادئة الاتصال الدولي `00` مكافئة لـ`+` — تُقصّ ويبقى مفتاح الدولة.
  const international = digits.startsWith("00") ? digits.slice(2) : digits;
  if (!international || international.startsWith("0")) return null;
  // أقصر رقم دولي فعلي ثمانية أرقام؛ ما دونه إدخالٌ ناقص لا رقم هاتف.
  if (international.length < 8 || international.length > 15) return null;
  return international;
}

/** رابط محادثة واتساب مع نص جاهز، أو `null` إن كان رقم الشركة غير دولي. */
export function whatsappLink(phone: string | null | undefined, message: string): string | null {
  const number = whatsappNumber(phone);
  if (!number) return null;
  return `https://wa.me/${number}?text=${encodeURIComponent(message)}`;
}

/** نص رسالة الاستفسار: اسم المنتج ثم رابطه — كي يعرف البائع ما يُسأل عنه. */
export function productInquiryMessage(productName: string, productUrl: string): string {
  return `مرحباً، أستفسر عن: ${productName}\n${productUrl}`;
}

/**
 * رابط واتساب جاهزٌ للاستفسار عن منتج — الفعلُ الأساسيّ في بطاقة منتجٍ
 * سعرُه مخفيٌّ (مواصفة #166 م٧، قسم هـ). `origin` يأتي من المتصفح لا ثابت،
 * كنظيراتها أعلاه؛ `null` إن كان رقم المتجر غير دوليّ.
 */
export function productWhatsappHref(
  origin: string,
  phone: string | null | undefined,
  storeSlug: string,
  productId: number | string,
  productName: string,
): string | null {
  const url = storeProductUrl(origin, storeSlug, productId);
  return whatsappLink(phone, productInquiryMessage(productName, url));
}
