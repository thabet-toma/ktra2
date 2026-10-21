/**
 * T-ITEMS M1 — تعريفٌ واحد لـ«الوضع البسيط» في المنتج.
 *
 * النافذتان السريعتان تبنيان حمولتهما من هنا: `ItemQuickEditModal`
 * (`dirtySimplePayload`) و`ItemQuickCreateModal` (`simplePayload`)، وكذلك تعديل
 * الاسم في مكانه (`ItemsManagement`). ثلاث شاشات تبني حمولتها بيدها = ثلاث
 * حمولات متباعدة، وقد كان ذلك حاصلاً: الإنشاء السريع يرسل وحدة القياس باسمٍ
 * ليس في العقد فتُبتلع.
 *
 * التسعة هي ما يلزم لبيع المنتج وشرائه وإيجاده. الباقي (النوع، حدود المخزون،
 * الكفالات، الحسابات) في الكرت الكامل `ItemForm` الذي فيه قسم «متقدم» — أما
 * النوافذ السريعة فلا قسمَ متقدّم فيها، فلا حقلَ مخفيٌّ وراءه.
 *
 * **والبراند منها** (B2): حقلُ صفٍّ لا حقلُ عائلة — «المنتج» عائلةٌ و«البراند»
 * صفٌّ قابلٌ للبيع، وتسميةُ العائلة تأتي من الاسم.
 */

export type ItemSimpleFields = {
  name_ar: string;
  name_en: string;
  brand: string;
  category: number | null;
  uom_id: number | null;
  sale_price: string;
  barcode: string;
  is_service: boolean;
  is_serialized: boolean;
};

export const blankSimpleFields = (): ItemSimpleFields => ({
  name_ar: "",
  name_en: "",
  brand: "",
  category: null,
  uom_id: null,
  sale_price: "",
  barcode: "",
  is_service: false,
  is_serialized: false,
});

/** صفّ منتج خام (من الخادم) ← حقول النموذج. */
export const simpleFieldsFromProduct = (p: Record<string, unknown>): ItemSimpleFields => ({
  name_ar: String(p.name_ar ?? ""),
  name_en: String(p.name_en ?? ""),
  brand: String(p.brand ?? ""),
  category: p.category != null && p.category !== "" ? Number(p.category) : null,
  uom_id: p.uom_id != null && p.uom_id !== "" ? Number(p.uom_id) : null,
  sale_price: p.sale_price != null ? String(p.sale_price) : "",
  barcode: String(p.barcode ?? ""),
  is_service: Boolean(p.is_service),
  is_serialized: Boolean(p.is_serialized),
});

/**
 * حقول النموذج ← حمولة الخادم.
 *
 * الفراغ يصير `null` لا `""`: الباركود الفارغ نصّاً يجعل منتجين بلا باركود
 * متصادمين في حارس التفرّد، وسعر البيع الفارغ نصّاً يصير صفراً في القراءة
 * فيبدو أن المنتج يُباع مجّاناً — بينما `null` يعني «لا سعر محفوظ» فيرجع
 * محرّك التسعير إلى مصادره الأخرى.
 *
 * البراند نصٌّ فارغٌ لا `null`: الخادم `CharField(blank=True)` بلا NULL، فارغُه
 * «بلا براند» شرعاً.
 */
export const simplePayload = (f: ItemSimpleFields): Record<string, unknown> => ({
  name_ar: f.name_ar.trim() || null,
  name_en: f.name_en.trim() || null,
  brand: f.brand.trim(),
  category: f.category,
  uom_id: f.uom_id,
  sale_price: f.sale_price.trim() ? Number(f.sale_price) : null,
  barcode: f.barcode.trim() || null,
  is_service: f.is_service,
  // الخدمة بلا وحدات مادّية تُتتبَّع — التتبّع معها تناقض لا خيار.
  is_serialized: f.is_service ? false : f.is_serialized,
});

/**
 * فرقُ ما تغيّر وحده — حمولة PATCH.
 *
 * التحرير السريع من داخل فاتورة يجب ألا يعيد كتابة حقلٍ لم يلمسه المستخدم:
 * إرسال الحمولة كاملةً يجعل تغيير الاسم يكتب `category` و`sale_price` معه،
 * فيُسجَّل في سجلّ النشاط تعديلٌ لم يحدث، وتُداس قيمةٌ غيّرها شخصٌ آخر بين
 * فتح النافذة وحفظها.
 */
export const dirtySimplePayload = (
  before: ItemSimpleFields,
  after: ItemSimpleFields,
): Record<string, unknown> => {
  const beforePayload = simplePayload(before);
  const afterPayload = simplePayload(after);
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(afterPayload)) {
    if (afterPayload[key] !== beforePayload[key]) out[key] = afterPayload[key];
  }
  return out;
};

/** هل يستحق الحفظ أصلاً — نافذةٌ بلا تغيير تُغلق بلا طلب. */
export const hasSimpleChanges = (
  before: ItemSimpleFields,
  after: ItemSimpleFields,
): boolean => Object.keys(dirtySimplePayload(before, after)).length > 0;

/** الاسم مطلوب — بالعربية أو بالإنجليزية (نفس قاعدة الخادم). */
export const validateSimpleFields = (f: ItemSimpleFields): string | null =>
  f.name_ar.trim() || f.name_en.trim()
    ? null
    : "اسم المنتج مطلوب — أدخل الاسم بالعربية أو بالإنجليزية.";
