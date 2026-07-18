export type ImportJourneyAction =
  | "save_shipment"
  | "link_deals"
  | "set_freight"
  | "pay_freight"
  | "create_clearance"
  | "enter_clearance_costs"
  | "manage_local_transport"
  | "create_invoice"
  | "view_invoice";

export interface ImportJourneyGuidanceInput {
  shipmentSaved: boolean;
  invoiceEligible: boolean;
  dealsCount: number;
  freightTotalUsd: number;
  freightFullyPaid: boolean;
  clearanceExists: boolean;
  clearanceCostTotal: number;
  convertedInvoiceId: number | null;
  remainingDealsCount: number;
}

export interface ImportJourneyGuidance {
  action: ImportJourneyAction;
  step: number;
  title: string;
  description: string;
  actionLabel: string;
}

interface DealMeasureRow {
  deal?: number;
  deal_ref?: string;
  deal_total_cbm?: number | string;
  deal_total_weight_kg?: number | string;
}

export function getMissingDealMeasureRefs(
  allocations: DealMeasureRow[],
  unit: "cbm" | "kg",
): string[] {
  const numberValue = (value: number | string | undefined) => {
    const parsed = typeof value === "string" ? parseFloat(value) : value ?? 0;
    return Number.isFinite(parsed) ? parsed : 0;
  };
  return allocations
    .filter((row) => numberValue(unit === "kg" ? row.deal_total_weight_kg : row.deal_total_cbm) <= 0)
    .map((row) => row.deal_ref || `#${row.deal}`);
}

export function getImportJourneyGuidance(input: ImportJourneyGuidanceInput): ImportJourneyGuidance {
  if (!input.shipmentSaved) {
    return { action: "save_shipment", step: 1, title: "احفظ بيانات الشحنة", description: "أكمل البيانات الأساسية لتبدأ رحلة الاستيراد.", actionLabel: "حفظ الشحنة" };
  }
  if (!input.invoiceEligible) {
    return { action: "manage_local_transport", step: 5, title: "أكمل بيانات النقل المحلي", description: "هذه الشحنة للنقل فقط ولا تحتاج إنشاء فاتورة دولية.", actionLabel: "فتح النقل المحلي" };
  }
  if (input.dealsCount === 0) {
    return { action: "link_deals", step: 2, title: "ضمّ الصفقات إلى الشحنة", description: "اختر الصفقات التي وصلت ضمن هذه الشحنة.", actionLabel: "فتح الصفقات" };
  }
  if (input.freightTotalUsd <= 0) {
    return { action: "set_freight", step: 3, title: "حدّد تكلفة الشحن الدولي", description: "اختر CBM أو KG وأدخل سعر الوحدة ليُوزّع المبلغ تلقائياً.", actionLabel: "إدخال تكلفة الشحن" };
  }
  if (!input.freightFullyPaid) {
    return { action: "pay_freight", step: 3, title: "أكمل دفعات الشحن الدولي", description: "الفاتورة الدولية تحتاج أن تكون دفعات وكيل الشحن مؤكدة.", actionLabel: "تسجيل دفعة شحن" };
  }
  if (!input.clearanceExists) {
    return { action: "create_clearance", step: 4, title: "أنشئ ملف التخليص", description: "سجّل المخلّص ورقم البيان وتكاليف التخليص.", actionLabel: "إنشاء التخليص" };
  }
  if (input.clearanceCostTotal <= 0) {
    return { action: "enter_clearance_costs", step: 4, title: "أدخل تكلفة التخليص", description: "يمكنك إدخال إجمالي واحد أو تفصيل الرسوم إلى بنود.", actionLabel: "إدخال التكلفة" };
  }
  if (input.convertedInvoiceId && input.remainingDealsCount === 0) {
    return { action: "view_invoice", step: 6, title: "رحلة الاستيراد مكتملة", description: `تم إنشاء الفاتورة الدولية #${input.convertedInvoiceId}.`, actionLabel: "فتح الفاتورة" };
  }
  return {
    action: "create_invoice",
    step: 6,
    title: input.convertedInvoiceId ? "توجد صفقات متبقية للتحويل" : "جاهزة لإنشاء الفاتورة الدولية",
    description: input.convertedInvoiceId
      ? `تم تحويل جزء من الشحنة وبقيت ${input.remainingDealsCount} صفقة. يمكنك إنشاء فواتيرها الآن أو لاحقاً.`
      : "لا يشترط دفع التخليص أو النقل المحلي؛ يمكن تسويتهما لاحقاً.",
    actionLabel: input.convertedInvoiceId ? `إنشاء الفواتير المتبقية (${input.remainingDealsCount})` : "إنشاء الفاتورة الدولية",
  };
}
