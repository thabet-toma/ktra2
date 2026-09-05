/**
 * ISSUE #133 — منتقي أصنافٍ واحد للبيع والشراء: أيّ حقول تظهر في نتيجة
 * منتقي المستندات (منتقي الشراء/الطلبية والمنتقي المدمج في فاتورة البيع)
 * حسب سياق الاستخدام وحالة زرّ العين. دالّةٌ نقيّة — لا حالة ولا DOM — على
 * غرار `procurementColumns.ts` حرفياً: قوائم سماح صريحة، لا قوائم منع.
 *
 * **ثلاثة سياقات لا اثنان**: تركيب مستند شراء (`purchase`) · تركيب مستند
 * بيع (`sale`) · طباعة أو تصدير (`print`) — والثالث يبتلع الحقول الحسّاسة
 * دائماً بصرف النظر عن أي شيء آخر، تماماً كما ابتلعت `procurementColumns`
 * السعرَ الداخلي من مستندها.
 *
 * **السعر التقديري وحده خلف زرّ العين** (`indicative_purchase_price` +
 * `indicative_purchase_price_source` من `ProductLookupSerializer`، مصدرها
 * `core/pricing.py` — `indicative_purchase_prices`؛ أقلّ شراء ضمن آخر ٥
 * فواتير شراء مرحَّلة، وليس تكلفة). شارة حالة المخزون والمتاح بعد الحجز لا
 * علاقة لهما بالخصوصية — بائعٌ ومشترٍ كلاهما يحتاج «هل يوجد؟» ليقرّر، فتبقى
 * ظاهرة في سياقَي المستند معاً بصرف النظر عن العين.
 */

export type PickerUsageContext = 'purchase' | 'sale' | 'print';

export interface PickerFieldVisibility {
  /** السعر التقديري (أقلّ شراء ضمن آخر ٥ فواتير) ولافتة مصدره — حقلٌ واحد
   *  مرئياً، لا رقماً منفصلاً عن مصدره: من يرى القيمة يرى من أين أتت. */
  indicativePurchasePrice: boolean;
  /** شارة حالة المخزون (نفذ/منخفض) — من `stock_status` الوارد أصلاً في عقد
   *  المنتقي؛ هذه الدالّة تقرّر الرسم لا الجلب. */
  stockBadge: boolean;
  /** المتاح بعد خصم المحجوز — لا الرصيد الخام (`available_quantity`). */
  availableAfterReservation: boolean;
}

/**
 * `eyeOpen` تعبيرٌ عرضيٌّ بحت — تفضيلٌ محلّي على متصفح المستخدم نفسه
 * (`PriceVisibilityContext`، مفتاح `ktra_prices_visible` في `localStorage`)
 * لا إعداد شركة. طيُّ الحقل هنا **عرضٌ لا حراسة**: لا يغيّر شيئاً فيما
 * يُطلب من الخادم — البيانات وصلت الشاشة فعلاً، وهذه الدالّة تقرّر رسمها أو
 * طيّها فقط. من أراد حجباً حقيقياً فمرجعه صلاحيات الخادم (`core/access.py`)
 * لا هذا التفضيل — سببه أن الزبون الواقف أمام شاشة البائع قد يلمح الشاشة
 * لحظة، لا أن البائع نفسه غير موثوق.
 *
 * والطباعة/التصدير حالةٌ مقفلة بلا أي إمكان فتحٍ عبر العين: السعر التقديري
 * رقمٌ داخلي للتفاوض معنا لا معه — غيابه عن الورقة **حقيقة** لا **تفضيل**.
 */
export function getPickerFieldVisibility(
  context: PickerUsageContext,
  eyeOpen: boolean,
): PickerFieldVisibility {
  const isDocumentContext = context === 'purchase' || context === 'sale';
  return {
    // لا استثناء للطباعة مهما كانت حالة العين — الشرطان معاً لا أحدهما.
    indicativePurchasePrice: isDocumentContext && eyeOpen,
    stockBadge: isDocumentContext,
    availableAfterReservation: isDocumentContext,
  };
}
