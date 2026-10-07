/**
 * 3ب: تسوية الفاتورة الدولية — تكاليفها الأربع مقابل دفعاتها الأربع.
 * الخادم يحسب (`logistics/domain/import_settlement.py`)، وهنا العرض وحده.
 */
import { formatMoney } from "./formatNumber.ts";
import type { InvoiceFinalCostAllocation } from "./invoiceTaxesAndFees.ts";

export type ImportPaymentComponentKey = "supplier" | "freight" | "clearance" | "local";

export interface ImportPaymentComponent {
  cost: string;
  paid: string;
  remaining: string;
}

export interface ImportPaymentBreakdown {
  payment_status: "paid" | "partially_paid" | "unpaid";
  payment_status_display: string;
  payable_total: string;
  amount_paid: string;
  remaining_balance: string;
  components: Record<ImportPaymentComponentKey, ImportPaymentComponent>;
  /** سطور «إجمالي التكلفة» (`_cost_rows`) — `payable_total` مجموعها من الخادم. */
  cost_rows?: ImportCostRowDto[];
  /** التفصيل وحده: التكلفة النهائية لكل وحدة (`import_invoice_unit_costs`). */
  unit_costs?: Array<{ item_id: number; name: string; quantity: string; unit_cost: string }>;
}

/** سطر «تفصيل التكاليف»: مورد، شحن، تخليص، محلي، عمولات التحويل، `fee:<id>`، ضريبة. */
export interface ImportCostRowDto extends ImportPaymentComponent {
  key: string;
  label: string;
}

export const IMPORT_PAYMENT_LABELS: Record<ImportPaymentComponentKey, string> = {
  supplier: "مورد",
  freight: "شحن",
  clearance: "تخليص",
  local: "محلي",
};

const ORDER: ImportPaymentComponentKey[] = ["supplier", "freight", "clearance", "local"];

/**
 * أساس الدفع في محرّر فاتورة الشراء («ادفع الكل» والتعبئة ولوحة الدفع).
 * المحلية: الإجمالي + الرسوم. الدولية المرحّلة: حصّة المورد التي دائنه بها الترحيل
 * (`payable_total` من الخادم — `logistics/services.py` `import_invoice_ap_credit`)،
 * لا الإجمالي المحمَّل الذي يضمّ حصص الوكيل والمخلّص والناقل — تلك تُدفع لأصحابها.
 */
export function purchasePayableTotal(input: {
  grandTotal: number;
  feesTotal: number;
  international: boolean;
  isPosted: boolean;
  serverPayableTotal?: number | null;
}): number {
  const { grandTotal, feesTotal, international, isPosted, serverPayableTotal } = input;
  if (international && isPosted && typeof serverPayableTotal === "number" && Number.isFinite(serverPayableTotal)) {
    return serverPayableTotal;
  }
  return (Number(grandTotal) || 0) + (Number(feesTotal) || 0);
}

/**
 * أساس **دفع المورد** (لوحة الدفع، «مدفوعة»، الدفعة النقدية التلقائية، تسوية المورد).
 * المسودة الدولية: ما سيدائنه به ترحيلُها (`supplier_payable_total` —
 * `logistics/accruals.py` `import_invoice_supplier_split`)، لا `payableTotal` المحمَّل
 * الذي يضمّ حصص الوكيل والمخلّص والناقل؛ وإلا دُفعت حصصهم للمورد سلفةً.
 * غيرُها: `payableTotal` كما هو — وهو للمرحّلة حصّة المورد من قيدها أصلاً.
 */
export function purchaseSupplierPayBase(input: {
  payableTotal: number;
  international: boolean;
  isPosted: boolean;
  serverSupplierPayable?: number | null;
}): number {
  const { payableTotal, international, isPosted, serverSupplierPayable } = input;
  if (international && !isPosted && typeof serverSupplierPayable === "number" && Number.isFinite(serverSupplierPayable)) {
    return serverSupplierPayable;
  }
  return payableTotal;
}

export interface ImportPaymentRow {
  key: ImportPaymentComponentKey;
  label: string;
  cost: number;
  paid: number;
  remaining: number;
}

/**
 * طباعة الفاتورة الدولية: التكاليف الأربع بترتيبها (مورد · شحن · تخليص · محلي)، كلٌّ بتكلفته
 * ومدفوعه وباقيه من الخادم — فصفّ المورد متّسقٌ (الحصّة − المدفوع = الباقي) بدل «الإجمالي
 * المحمَّل − مدفوع المورد» الذي لا يساوي باقيه.
 */
export function importPaymentRows(ip: ImportPaymentBreakdown | null | undefined): ImportPaymentRow[] {
  if (!ip?.components) return [];
  return ORDER
    .filter((key) => ip.components[key])
    .map((key) => {
      const c = ip.components[key];
      return {
        key,
        label: IMPORT_PAYMENT_LABELS[key],
        cost: Number(c.cost) || 0,
        paid: Number(c.paid) || 0,
        remaining: Number(c.remaining) || 0,
      };
    });
}

/** «مورد X · شحن X · تخليص X · محلي X» — المدفوع لكل دائن من تكلفته. */
export function importPaymentTooltip(ip: ImportPaymentBreakdown | null | undefined): string {
  if (!ip?.components) return "";
  return ORDER
    .filter((key) => ip.components[key])
    .map((key) => {
      const c = ip.components[key];
      return `${IMPORT_PAYMENT_LABELS[key]} ${formatMoney(c.paid)} / ${formatMoney(c.cost)}`;
    })
    .join(" · ");
}

export interface ImportCostRow {
  key: string;
  label: string;
  cost: number;
  paid: number;
  remaining: number;
}

/**
 * «تفصيل التكاليف» للفاتورة الدولية (العرض والطباعة): السطور كما رتّبها الخادم بأرقامها،
 * و«إجمالي التكلفة» ومدفوعه ومتبقّيه من `payable_total`/`amount_paid`/`remaining_balance`
 * — رقمٌ واحد مع المربّع والقائمة، لا مجموعٌ ثانٍ هنا. بلا `cost_rows` ⇒ لا قسم.
 */
export function importCostRows(
  ip: ImportPaymentBreakdown | null | undefined,
): { rows: ImportCostRow[]; totalCost: number; totalPaid: number; totalRemaining: number } | null {
  if (!ip?.cost_rows?.length) return null;
  return {
    rows: ip.cost_rows.map((r) => ({
      key: r.key,
      label: r.label,
      cost: Number(r.cost) || 0,
      paid: Number(r.paid) || 0,
      remaining: Number(r.remaining) || 0,
    })),
    totalCost: Number(ip.payable_total) || 0,
    totalPaid: Number(ip.amount_paid) || 0,
    totalRemaining: Number(ip.remaining_balance) || 0,
  };
}

/**
 * «التكلفة النهائية/وحدة» لبند الفاتورة الدولية (جدول البنود عرضاً وتحريراً، والطباعة):
 * `unit_costs` من الخادم (`import_invoice_unit_costs` — توزيع قيد الاستلام نفسه، فيساوي
 * `avg_cost` عند الاستلام: بالرسوم المرسملة والعمولة، بلا الضريبة) للبند المحفوظ
 * (`serverId`)؛ وإلا `fallback` كما كان (بندٌ لم يُحفظ، المحلية، قائمةٌ بلا تفصيل).
 * كان العمود سعرَ البند المستورد وحده فخالف «تفصيل التكاليف» (INV-0023: 41.44 مقابل 46.0506).
 */
export function importFinalUnitCost(
  ip: ImportPaymentBreakdown | null | undefined,
  serverId: number | null | undefined,
  fallback: number | null | undefined,
): number | null {
  if (serverId != null) {
    const row = ip?.unit_costs?.find((u) => u.item_id === serverId);
    const unit = Number(row?.unit_cost);
    if (row && Number.isFinite(unit)) return unit;
  }
  return fallback ?? null;
}

/**
 * تكلفة كل بند في الشاشة (شبكة التحرير وجدول بنود الشيكل) من مصدر الخادم: البند المحفوظ
 * الذي له `unit_costs` تُستبدل وحدته وسطره (= وحدة × كمية) وحصّته من «ض.ق.م + رسوم» (السطر
 * − ما قبل الضريبة) — فمجموع الأسطر = «إجمالي التكلفة» = مدين المخزون عند الاستلام. كان
 * `allocateInvoiceFinalCosts` يوزّع الضريبة والرسوم وحده بلا العمولة (INV-0023: 15,060.15
 * مقابل 15,196.23). بندٌ لم يُحفظ أو فاتورةٌ بلا تفصيل: التوزيع المحلي كما هو.
 */
export function applyImportUnitCosts<T extends InvoiceFinalCostAllocation>(
  allocations: T[],
  items: Array<{ serverId?: number | null; quantity?: number | string | null }>,
  ip: ImportPaymentBreakdown | null | undefined,
): T[] {
  if (!ip?.unit_costs?.length) return allocations;
  return allocations.map((alloc, index) => {
    const item = items[index];
    const unit = importFinalUnitCost(ip, item?.serverId, null);
    if (unit == null) return alloc;
    const finalLine = unit * (Number(item?.quantity) || 0);
    return { ...alloc, finalUnit: unit, finalLine, taxAndFeesAllocation: finalLine - alloc.preTaxLine };
  });
}
