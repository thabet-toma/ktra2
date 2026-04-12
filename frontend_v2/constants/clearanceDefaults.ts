/** بنود تكلفة التخليص الافتراضية (مواءمة مع Django `default_clearance_cost_lines`). */
export type ClearanceCostLine = { label: string; amount: number };

export const DEFAULT_CLEARANCE_COST_LINES: ClearanceCostLine[] = [
  { label: "ضريبة القيمة المضافة", amount: 0 },
  { label: "رسوم البيان الجمركي", amount: 0 },
  { label: "محطة الشحن", amount: 0 },
  { label: "معالجة التصاريح", amount: 0 },
  { label: "عمولة المخلص", amount: 0 },
  { label: "نظام الجمارك «الجيل الجديد»", amount: 0 },
];
