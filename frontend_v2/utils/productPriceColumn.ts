import type { SqlProduct } from "../types/inventory";

/**
 * M3-COGS: خيارات الرقم الأساسي المعروض في عمود السعر بجدول المنتجات —
 * تطابق `SalesSettings.PRODUCT_PRICE_COLUMN_CHOICES` في الخادم بالترتيب نفسه.
 */
export const PRODUCT_PRICE_COLUMN_OPTIONS = [
  {
    value: "last_purchase",
    label: "آخر سعر شراء",
    hint: "آخر سعر شراء في فاتورة شراء مرحَّلة — لا متوسط التكلفة",
  },
  {
    value: "lowest_purchase",
    label: "أقلّ شراء (آخر ٥)",
    hint: "أقلّ سعر شراء في آخر ٥ فواتير شراء مرحَّلة",
  },
  {
    value: "method_cost",
    label: "التكلفة حسب الطريقة المختارة",
    hint: "التكلفة حسب طريقة تكلفة المبيعات المختارة في إعدادات المبيعات",
  },
  {
    value: "inventory_avg",
    label: "متوسط تكلفة المخزون",
    hint: "قيمة المخزون المفتوح ÷ كميّته — لا متوسط التكلفة المخزَّن",
  },
  {
    value: "standard",
    label: "السعر الثابت",
    hint: "السعر الثابت المسجَّل في بطاقة الصنف",
  },
] as const;

export type ProductPriceColumn = typeof PRODUCT_PRICE_COLUMN_OPTIONS[number]["value"];

export type ProductPriceFields = Pick<
  SqlProduct,
  | "last_purchase_price"
  | "indicative_purchase_price"
  | "method_cost"
  | "inventory_avg_cost"
  | "standard_cost"
>;

export type ProductPriceDetailItem = {
  key: ProductPriceColumn;
  label: string;
  value: string | null;
};

const VALID_COLUMNS = new Set<string>(PRODUCT_PRICE_COLUMN_OPTIONS.map((o) => o.value));

export function normalizeProductPriceColumn(column?: string | null): ProductPriceColumn {
  return column && VALID_COLUMNS.has(column)
    ? (column as ProductPriceColumn)
    : "last_purchase";
}

export function productPriceColumnLabel(column?: string | null): string {
  const key = normalizeProductPriceColumn(column);
  return PRODUCT_PRICE_COLUMN_OPTIONS.find((o) => o.value === key)!.label;
}

export function productPriceColumnHint(column?: string | null): string {
  const key = normalizeProductPriceColumn(column);
  return PRODUCT_PRICE_COLUMN_OPTIONS.find((o) => o.value === key)!.hint;
}

export function productPriceValue(
  product: ProductPriceFields,
  column?: string | null,
): string | null {
  const key = normalizeProductPriceColumn(column);
  let raw: string | number | null | undefined;
  switch (key) {
    case "last_purchase":
      raw = product.last_purchase_price;
      break;
    case "lowest_purchase":
      raw = product.indicative_purchase_price;
      break;
    case "method_cost":
      raw = product.method_cost;
      break;
    case "inventory_avg":
      raw = product.inventory_avg_cost;
      break;
    case "standard":
      raw = product.standard_cost;
      break;
  }
  if (raw == null || raw === "") return null;
  return String(raw);
}

export function productPriceDetails(
  product: ProductPriceFields,
  column?: string | null,
): ProductPriceDetailItem[] {
  const active = normalizeProductPriceColumn(column);
  return PRODUCT_PRICE_COLUMN_OPTIONS
    .filter((o) => o.value !== active)
    .map((o) => ({
      key: o.value,
      label: o.label,
      value: productPriceValue(product, o.value),
    }));
}
