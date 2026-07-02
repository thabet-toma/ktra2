export interface SqlProduct {
  id: number;
  sku: string;
  barcode?: string | null;
  name_ar?: string | null;
  name_en?: string | null;
  /** الصنف الفرعي/المجموعة الصريحة (مثل 185/65/14) — يصير عقدة أب يتجمّع تحتها. */
  variant_group?: string | null;
  /** البراند (روك بيلد/جلاكسي…) — يظهر بين قوسين على الورقة. */
  brand?: string | null;
  /** مفتاح التجميع (المجموعة الصريحة أو المقاس/الأساس) — يُحسب خادمياً. */
  group_key?: string | null;
  /** اسم العرض = الاسم + البراند بين قوسين (للورقة في الشجرة/الجرد/الجدول). */
  display_name?: string | null;
  /** هل المجموعة صريحة — فيظهر المجلّد حتى لو منتج واحد. */
  has_group?: boolean;
  category?: number | null;
  category_name?: string | null;
  uom_id?: number | null;
  weight_kg?: string | null;
  volume_cbm?: string | null;
  hs_code?: string | null;
  min_stock_level?: number | null;
  quantity_on_hand: number;
  avg_cost: number;
  stock_status: "in_stock" | "low_stock" | "out_of_stock";
}

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
