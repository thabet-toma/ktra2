/**
 * THA-19 — نقطة تحويلٍ واحدة من صفّ منتقي المنتجات (`view=lookup`) إلى بند
 * المستند (`Item`).
 *
 * كانت هذه العملية مكرَّرةً في مُطابِقَين منفصلين: `firestoreService._mapProductToItem`
 * (الشاشة الكاملة) و`ItemSearchModal.productToItem` (نافذة البحث). الحقول
 * تُضاف لأحدهما وتُنسى في الآخر — وقد أنتج ذلك حقلاً ميتاً من قبل، وفحص
 * الأنواع هنا لا يمسك مثله في JSX. الخيارات أدناه ليست تجميلاً: هي التوثيق
 * الصريح للاختلافات الحقيقية القائمة بين المستدعيَين اليوم (راجع
 * `pickerProductToItem.test.ts`)، فحُفظت بدل أن تُذاب في نسخةٍ واحدة تغيّر
 * سلوك أحدهما بصمت.
 */

import type { Item } from "../types";

export type PickerProductMapOptions = {
  /** النصّ حين لا يوجد اسمٌ آخر — يبنيه كل مستدعٍ بصياغته الخاصة اليوم. */
  fallbackName: (p: Record<string, unknown>) => string;
  /** الشاشة الكاملة تشترط category صالحاً (truthy)؛ نافذة البحث تقبل 0 أيضاً (`!= null`). */
  categoryIdAcceptsZero?: boolean;
  /** الشاشة الكاملة تكتب "" حين لا يوجد sku؛ نافذة البحث تترك `undefined`. */
  emptyModelNumberAsUndefined?: boolean;
  /** الحقول الموسّعة (الوصف والصور من المرفقات وبقية حقول الكرت) — نافذة البحث لا تبنيها أصلاً. */
  extended?: boolean;
};

/** صفّ منتج خام (من نقطة `view=lookup`) ← بند مستند (`Item`). */
export const mapPickerProductToItem = (
  p: Record<string, unknown>,
  opts: PickerProductMapOptions,
): Item => {
  const category = (p as any).category;
  const categoryIdValid = opts.categoryIdAcceptsZero ? category != null : Boolean(category);

  const sku = (p as any).sku;
  const modelNumber = sku
    ? sku
    : opts.emptyModelNumberAsUndefined
      ? undefined
      : "";

  const base = {
    id: String((p as any).id),
    name:
      (p as any).display_name ||
      (p as any).name_ar ||
      (p as any).name_en ||
      (p as any).sku ||
      opts.fallbackName(p),
    modelNumber,
    categoryId: categoryIdValid ? String(category) : "",
    categoryName: (p as any).category_name || "",
    // T-SUPSKU: أرقام كتالوج الموردين — بها يبحث المستخدم في منتقي البنود،
    // فهي الأرقام التي تصل بها فاتورة المورّد بيده (מק"ט).
    supplierCodes: (p as any).supplier_codes_text || "",
    specifications: opts.extended ? (p as any).online_description || "" : "",
    imageUrls: opts.extended ? extractImageUrls(p) : [],
    // T-SERIAL: يصلان من عقد `view=lookup` — الأول للبحث بالماسح، والثاني
    // ليعرف سطر الفاتورة أنه منتج يُتتبَّع بالوحدة.
    barcode: (p as any).barcode || "",
    isSerialized: Boolean((p as any).is_serialized),
    // #22: «المنتج» (الأب) — للسياق فقط، لا تُعرض كخيارٍ مستقل في المنتقي.
    familyId: (p as any).family_id != null ? String((p as any).family_id) : undefined,
    familyName: (p as any).family_name || undefined,
    // ISSUE #133: أساسيةٌ لا موسّعة عمداً — نافذة البحث (`ItemSearchModal`)
    // وتدفّق الإنشاء السريع (`onItemCreated`/`onSaved`) يغذّيان نفس مصفوفة
    // `allDbItems` التي يبني منها المنتقي شارته، فحقلٌ موسَّعٌ فقط كان سيصل
    // مستدعياً واحداً دون الآخر وينتج بندَ شارةً صامتاً في نصف الحالات.
    stock_status: (p as any).stock_status,
    is_service: (p as any).is_service,
    available_quantity: (p as any).available_quantity,
    quantity_on_hand: (p as any).quantity_on_hand,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };

  if (!opts.extended) return base as Item;

  return {
    ...base,
    subCategoryId: "",
    subCategoryName: "",
    brandId: "",
    brandName: "",
    hsCodePrimary: (p as any).hs_code || "",
    hsCodeAlternative: "",
    quantity: (p as any).min_stock_level || 0,
    notes: "",
    isActive: Boolean((p as any).is_for_sale_online),
    salePrice: Number((p as any).online_price || 0),
    storeName: (p as any).name_ar || (p as any).name_en || "",
    storeDescription: (p as any).online_description || "",
  } as Item;
};

const extractImageUrls = (p: Record<string, unknown>): string[] => {
  const attach = Array.isArray((p as any).attachments) ? (p as any).attachments : [];
  const urls = attach.map((a: any) => a.file_path).filter(Boolean);
  return urls.length ? urls : ["", "", ""];
};
