export interface SqlProduct {
  id: number;
  sku: string;
  barcode?: string | null;
  name_ar?: string | null;
  name_en?: string | null;
  /** المنتج الفرعي/المجموعة الصريحة (مثل 185/65/14) — يصير عقدة أب يتجمّع تحتها. */
  variant_group?: string | null;
  /** البراند (روك بيلد/جلاكسي…) — يظهر بين قوسين على الورقة. */
  brand?: string | null;
  /** مفتاح التجميع (المجموعة الصريحة أو المقاس/الأساس) — يُحسب خادمياً. */
  group_key?: string | null;
  /** اسم العرض = الاسم + البراند بين قوسين (للورقة في الشجرة/الجرد/الجدول). */
  display_name?: string | null;
  /** هل المجموعة صريحة — فيظهر المجلّد حتى لو منتج واحد. */
  has_group?: boolean;
  /** #23: معرّف «المنتج» (الأب) — البراندات بنفس `family_id` تتجمّع في صفٍّ
   *  واحد في شاشة الأصناف. غائبٌ/null لصفوفٍ ما قبل هذا النموذج. */
  family_id?: number | null;
  /** اسم «المنتج» (الأب) — يُعرض على الصفّ المجمَّع بدل اسم براندٍ بعينه. */
  family_name?: string | null;
  category?: number | null;
  category_name?: string | null;
  uom_id?: number | null;
  weight_kg?: string | null;
  volume_cbm?: string | null;
  hs_code?: string | null;
  min_stock_level?: number | null;
  /** T-REORDER: المستوى الذي يُطلَب حتى بلوغه (نمط min/max). */
  max_stock_level?: number | null;
  /** #35: الحدّ **الحاكم** — نفس ما حُوكِمت به `stock_status` (حدّ الأب إن
   *  كان له أبٌ، وإلا `min_stock_level` نفسه). قراءةٌ فقط — لا تُبعَث في الحفظ. */
  effective_min_stock_level?: number | null;
  effective_max_stock_level?: number | null;
  quantity_on_hand: number;
  reserved_quantity?: number | string;
  available_quantity?: number | string;
  avg_cost: number;
  /** سعر البيع الافتراضي المحفوظ على المنتج (فارغ = يتبع آخر سعر بيع فعلي). */
  sale_price?: string | number | null;
  /** W8: الوارد التراكمي (كل حركات IN) — من StockMovement. */
  purchased_qty?: string | null;
  /** W8: متوسط المبيعات الشهري = صافي (OUT−RETURN_IN) 90ي ÷ 3. */
  avg_monthly_sales?: string | null;
  /** #133: السعر التقديري — أقلّ شراء ضمن آخر ٥ فواتير شراء مرحَّلة (لا
   *  avg_cost ولا كل الفترات). غائبٌ (null) لمنتجٍ بلا شراء مرحَّل — لا صفر. */
  indicative_purchase_price?: string | null;
  /** لافتة مصدر السعر التقديري، مثل «أقل شراء (آخر ٥)» — تحمل النافذة صراحةً. */
  indicative_purchase_price_source?: string | null;
  /** T-SERIAL: المنتج يتتبّع وحداته برقم تسلسلي (يفعّله كرت المنتج). */
  is_serialized?: boolean;
  /** T-REORDER: «overstock» = فوق الحدّ الأقصى. */
  stock_status: "in_stock" | "low_stock" | "out_of_stock" | "overstock";
}

/**
 * T-SERIAL: نمط إدخال الرقم التسلسلي في مستندات الشراء والبيع — مرآة
 * `inventory/serials.py::SERIAL_MODE_CHOICES`. الإعداد لكل شركة وعلى كل جانب
 * مستقلاً (`PurchaseSettings.serial_entry_mode` / `SalesSettings.serial_entry_mode`).
 */
export type SerialEntryMode = "off" | "optional" | "required";

/** خيارات النمط — معرَّفة مرة واحدة كي لا تتباعد شاشتا الشراء والبيع. */
export const SERIAL_ENTRY_MODE_OPTIONS: { value: SerialEntryMode; label: string }[] = [
  { value: "off", label: "معطّل" },
  { value: "optional", label: "اختياري" },
  { value: "required", label: "إجباري" },
];

export const SERIAL_ENTRY_MODE_HINT =
  "إجباري = لا تُرحَّل الفاتورة بدون الأرقام؛ اختياري = تظهر ويمكن الترحيل بدونها.";

export interface StockMovementDto {
  id: number;
  product: number;
  product_name: string;
  product_sku: string;
  movement_type: string;
  movement_type_display: string;
  quantity: string | number;
  unit_cost: string | number;
  total_cost: string | number;
  reference_type: string;
  reference_type_display: string;
  reference_id?: number | null;
  /** مصدر البضاعة: international (استيراد) / local (شراء) / other */
  origin?: 'international' | 'local' | 'other';
  partner?: number | null;
  partner_name?: string | null;
  movement_date: string;
  notes?: string | null;
  created_at: string;
  quantity_before: string | number;
  quantity_after: string | number;
  avg_cost_before: string | number;
  avg_cost_after: string | number;
}

export interface StockSummaryItem {
  id: number;
  sku: string;
  name: string;
  quantity_on_hand: number;
  avg_cost: number;
  total_value: number;
  min_stock_level?: number | null;
  stock_status: "in_stock" | "low_stock";
}

export interface StockSummaryResponse {
  products: StockSummaryItem[];
  total_inventory_value: number;
  total_products_in_stock: number;
}
