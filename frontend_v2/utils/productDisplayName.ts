/** #40/#41: عنوان مقروء للمنتج — يقدّم `display_name` القادم من الخادم قبل أي
 * اشتقاق محلي. كانت هذه الدالة تسكن داخل `components/sales/SalesProductPickerModal.tsx`
 * فتكرّرت خمس مرات في شاشاتٍ لا تستورد من مكوّنات المبيعات؛ هذا موضعها المشترك.
 * لا تُبنى الأقواس (الاسم + البراند) يدوياً هنا — القادم من الخادم كافٍ، ولو غاب
 * فالاحتياط أسماءٌ خامة لا تركيبٌ جديد. */

export type ProductNameFields = {
  id: number;
  sku?: string | null;
  name_ar?: string | null;
  name_en?: string | null;
  display_name?: string | null;
  name?: string | null;
};

export function formatProductPrimaryName(p: ProductNameFields): string {
  if (p.display_name) return p.display_name;
  const ar = (p.name_ar || "").trim();
  const en = (p.name_en || "").trim();
  const n = (p.name || "").trim();
  if (ar && en) return `${ar} — ${en}`;
  if (ar) return ar;
  if (en) return en;
  if (n) return n;
  return p.sku || `منتج #${p.id}`;
}

/** اسمُ الصنف على **سطر مستند**: اللقطةُ المجمَّدة عند الترحيل (THA-18) أوّلاً،
 * وإلّا الاسمُ الحيّ بصيغة `formatProductPrimaryName` — أي بالبراند.
 *
 * كانت هذه القاعدة مكتوبةً ثلاثَ مرّات في فاتورة البيع بمآلين: خليّةُ المحرِّر
 * تعرض البراند، ووجهُ المستند والطباعة يسقطان إلى `name_ar` الخامّ. فالمسودّة
 * (بلا لقطة) تُفتح بلا براند والمرحَّلة به — «أحياناً آه وأحياناً لا». */
export function documentLineProductName(
  snapshot: string | null | undefined,
  product: ProductNameFields | null | undefined,
): string {
  const frozen = (snapshot || "").trim();
  if (frozen) return frozen;
  return product ? formatProductPrimaryName(product) : "";
}
