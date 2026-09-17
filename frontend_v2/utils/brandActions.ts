/**
 * أفعالُ البراند — القاعدةُ مرّةً واحدة لكلّ شاشةٍ تُضيف منتجاً أو براندًا.
 *
 * بلاغ المالك (2026-09-17): «مش واضح كيف اضيف منتج وكيف اضيف براند». قيس على
 * الشاشة الحيّة: نموذجُ الإنشاء لا يذكر البراند، و«أضف براند» تحت الطيّ، و1760 من
 * 1763 منتجاً بلا أب **لا بابَ لها**، وزرُّ «إضافة براند آخر (تكرار)» يُنشئ منتجاً
 * منفصلاً. الأبوابُ الجديدة (كرت المنتج · القائمة · الإنشاء السريع من المستندات)
 * تمرّ كلُّها بهذا الملفّ — فلا تُكتب «أيُّ معرّفٍ يُرسَل» أو «ماذا لو فشل البراند
 * الثالث» مرّةً في كلّ شاشة.
 *
 * بلا استيرادٍ من `services/`: النداءاتُ تُحقَن، فيُختبَر الملفّ بـ`node --test`.
 */

/** ما يُرسَل إلى `products/add-brand/` لتعيين المنتج: أبٌ قائم، أو صفٌّ بلا أب
 *  (الخادمُ يتبنّى له أباً في معاملة الإضافة نفسِها). */
export type AddBrandTarget = { family_id: number } | { product_id: number };

type IdLike = number | string | null | undefined;

const positiveId = (value: IdLike): number | null => {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isInteger(n) && n > 0 ? n : null;
};

/**
 * الهدفُ من أيِّ شيءٍ يعرف منتجاً: صفُّ قائمة، ملفُّ كرت، أو اقتراحُ «هذا موجود».
 * الأبُ أوّلاً — وإلّا صفُّ المنتج نفسُه. `null` = لا يُعرَف منتجٌ بعد (لا زرّ).
 */
export function brandTargetOf(ref: {
  family_id?: IdLike;
  product_id?: IdLike;
  id?: IdLike;
}): AddBrandTarget | null {
  const familyId = positiveId(ref.family_id);
  if (familyId != null) return { family_id: familyId };
  const productId = positiveId(ref.product_id ?? ref.id);
  if (productId != null) return { product_id: productId };
  return null;
}

/** مفتاحُ مقارنة البراندات: «Michelin» و«michelin  » براندٌ واحد. */
export const brandKey = (raw: string): string =>
  raw.replace(/\s+/g, " ").trim().toLowerCase();

/** يُلحق براندًا بقائمة الشارات — الفارغُ والمكرَّرُ (بعد التطبيع) يُتجاهَلان. */
export function addBrandChip(chips: readonly string[], raw: string): string[] {
  const clean = raw.replace(/\s+/g, " ").trim();
  if (!clean) return [...chips];
  const key = brandKey(clean);
  if (chips.some((chip) => brandKey(chip) === key)) return [...chips];
  return [...chips, clean];
}

/** معاينةُ ما سيُسجَّل: «الاسم (البراند)» لكلِّ براند، أو الاسمُ وحدَه بلا براند.
 *  نفسُ صيغة الخادم (`inventory.services.product_display_name`). */
export function brandedNamesPreview(name: string, brands: readonly string[]): string[] {
  const base = name.replace(/\s+/g, " ").trim();
  if (!base) return [];
  if (brands.length === 0) return [base];
  return brands.map((brand) => (base.includes(brand) ? base : `${base} (${brand})`));
}

type CreatedProduct = { id: IdLike; family_id?: IdLike } & Record<string, unknown>;
type AddBrandResponse = { id: IdLike; created?: boolean } & Record<string, unknown>;

export type BrandStep =
  | { brand: string; ok: true; productId: number; created: boolean }
  | { brand: string; ok: false; error: string };

export type CreateWithBrandsResult = {
  /** ردُّ إنشاء المنتج كما هو — البراندُ الأوّل (أو بلا براند). */
  product: CreatedProduct;
  /** البراندات من الثاني فصاعداً، بترتيبها. */
  steps: BrandStep[];
};

const errorText = (error: unknown): string =>
  error instanceof Error && error.message ? error.message : "تعذّرت إضافة البراند";

/**
 * يُسجّل منتجاً بعدّة براندات: الإنشاءُ بالبراند الأوّل، ثمّ الباقي **بالتتابع**
 * تحت أبه نفسِه.
 *
 * - فشلُ الإنشاء يُرمى كما هو، **ولا نداءَ `addBrand` واحد** — لا براندات بلا منتج.
 * - فشلُ براندٍ لا يوقف ما بعده ولا يُبتلَع: يُسجَّل في `steps` باسمه وسببه، فتعرضه
 *   الشاشةُ ويعيد المستخدم المحاولة من شريط البراندات. لا معاملةَ تجمع النداءات،
 *   فالصادقُ هو قولُ ما حدث لا ادّعاءُ «كلّه أو لا شيء».
 */
export async function createProductWithBrands(
  deps: {
    createProduct: (payload: Record<string, unknown>) => Promise<CreatedProduct>;
    addBrand: (body: AddBrandTarget & { brand: string }) => Promise<AddBrandResponse>;
  },
  payload: Record<string, unknown>,
  brands: readonly string[],
): Promise<CreateWithBrandsResult> {
  const [first, ...rest] = brands;
  const product = await deps.createProduct({ ...payload, brand: first ?? "" });
  const target = brandTargetOf({ family_id: product.family_id, product_id: product.id });
  const steps: BrandStep[] = [];
  for (const brand of rest) {
    if (target == null) {
      steps.push({ brand, ok: false, error: "لم يُعرَف المنتج المُنشأ" });
      continue;
    }
    try {
      const res = await deps.addBrand({ ...target, brand });
      steps.push({ brand, ok: true, productId: Number(res.id), created: Boolean(res.created) });
    } catch (error) {
      steps.push({ brand, ok: false, error: errorText(error) });
    }
  }
  return { product, steps };
}

/** رسالةُ النتيجة للمستخدم — تسمّي الفاشلَ وسببه، ولا تقول «تمّ» على ما لم يتمّ. */
export function createWithBrandsMessage(
  sku: string,
  totalBrands: number,
  steps: readonly BrandStep[],
  formatCount: (n: number) => string,
): { ok: boolean; text: string } {
  const failed = steps.filter((s): s is Extract<BrandStep, { ok: false }> => !s.ok);
  if (totalBrands <= 1) return { ok: true, text: `تم إنشاء المنتج ${sku}.` };
  const done = totalBrands - failed.length;
  if (failed.length === 0) {
    return { ok: true, text: `تم إنشاء المنتج ${sku} بـ${formatCount(done)} براندات.` };
  }
  const list = failed.map((s) => `«${s.brand}»: ${s.error}`).join("؛ ");
  return {
    ok: false,
    text: `أُنشئ المنتج ${sku} بـ${formatCount(done)} من ${formatCount(totalBrands)} براندات. لم يُضَف: ${list} — أعد المحاولة من شريط البراندات.`,
  };
}

/**
 * الإنشاءُ السريع من مستند حين يطابق الاسمُ منتجاً قائماً: يُضاف البراند تحته، ثمّ
 * يُجلَب **الصفُّ الكامل** — مستدعو النافذة (الفواتير والطلبيّات والعروض) ينتظرون
 * ردَّ `ProductSerializer` كما يعيده `createProduct`، لا ردَّ `add-brand` المختصر
 * (بلا سعرٍ ولا رصيدٍ ولا وحدة) الذي كان سيُدرَج بنداً ناقصاً.
 */
export async function attachBrandToExisting(
  deps: {
    addBrand: (body: AddBrandTarget & { brand: string }) => Promise<AddBrandResponse>;
    getProduct: (id: number) => Promise<Record<string, unknown>>;
  },
  match: { family_id?: IdLike; product_id?: IdLike; id?: IdLike },
  brand: string,
): Promise<Record<string, unknown>> {
  const clean = brand.replace(/\s+/g, " ").trim();
  if (!clean) throw new Error("اكتب اسم البراند أولاً.");
  // `id` في الاقتراح معرّفُ **الأب** (عقد `check-name`) — لا يُقرأ صفَّ منتج.
  const target = brandTargetOf({ family_id: match.family_id ?? match.id, product_id: match.product_id });
  if (target == null) throw new Error("لم يُعرَف المنتج القائم.");
  const res = await deps.addBrand({ ...target, brand: clean });
  return deps.getProduct(Number(res.id));
}
