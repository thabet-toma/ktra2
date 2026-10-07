/**
 * 3ب: تسوية الفاتورة الدولية — تكاليفها الأربع مقابل دفعاتها الأربع.
 * الخادم يحسب (`logistics/domain/import_settlement.py`)، وهنا العرض وحده.
 */
import { formatMoney } from "./formatNumber.ts";

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
