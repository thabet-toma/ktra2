/** بند تكلفة التخليص (الموديل الجديد — LogisticsClearanceLine). */
export type ClearanceLine = {
  id?: number;
  clearance?: number;
  seq: number;
  line_type: string;
  account?: number | null;
  description: string;
  debit: number;
  credit: number;
  vat_percent: number;
  cost_center?: number | null;
};

/** بنود تكلفة التخليص القديمة (JSONField — backwards compat). */
export type ClearanceCostLine = { label: string; amount: number };

export const DEFAULT_CLEARANCE_COST_LINES: ClearanceCostLine[] = [
  { label: "ضريبة القيمة المضافة", amount: 0 },
  { label: "رسوم البيان الجمركي", amount: 0 },
  { label: "محطة الشحن", amount: 0 },
  { label: "معالجة التصاريح", amount: 0 },
  { label: "عمولة المخلص", amount: 0 },
  { label: "نظام الجمارك «الجيل الجديد»", amount: 0 },
];
