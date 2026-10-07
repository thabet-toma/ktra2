/**
 * «سجل الاستحقاق» — المنطق الخالص: لقطات بنود الاستحقاق (التخليص · شحن الوكيل · الإرسالية)
 * كما يرسلها الخادم، ومجموع البنود بالسنت، ولون الفرق، وأسماء الأنواع.
 * مصدر واحد للعرض في شاشة الاستيراد وكشف الحساب (`AccrualBreakdownTable`).
 */
import type { AccrualKind } from "./voucherAllocation";
import { formatMoney } from "./formatNumber.ts";

export type { AccrualKind };

/** بند من لقطة — المبلغ بالعملة الأساسية (₪) نصّاً عشرياً. */
export interface AccrualSnapshotLine { label: string; type: string; amount: string }

export type AccrualDiffStatus = "new" | "removed" | "changed" | "same";

export interface AccrualDiffRow {
  label: string;
  type: string;
  before: string;
  after: string;
  /** after − before */
  difference: string;
  status: AccrualDiffStatus;
}

export interface AccrualSnapshot {
  id: number;
  kind: AccrualKind;
  role: "original" | "adjustment";
  journal_id: number;
  /** تاريخ القيد YYYY-MM-DD */
  date: string | null;
  /** إجمالي اللقطة: الأصل = مبلغ قيد الاستحقاق، والتعديل = المستحق بعده. */
  total: string;
  /** null للأصل؛ للتعديل = total − إجمالي ما قبله (= مبلغ قيد التعديل). */
  difference: string | null;
  /** false = لا تفصيل بعد (بند إجمالي واحد) ⇒ «إضافة بنود». */
  detailed: boolean;
  lines: AccrualSnapshotLine[];
  /** null للأصل؛ مجموع diff.difference == difference. */
  diff: AccrualDiffRow[] | null;
  created_at: string;
}

/** أسماء أنواع البنود — تُقترَح كـ«بيان» عند اختيار نوع لبند التخليص بلا بيان. */
export const CLEARANCE_LINE_TYPE_LABELS: Record<string, string> = {
  vat: "ضريبة القيمة المضافة",
  declaration_fee: "رسوم البيان",
  terminal: "محطة الشحن",
  permits: "تصاريح",
  broker_commission: "عمولة المخلص",
  customs_system: "نظام الجمارك",
  "شحن محلي": "شحن محلي",
  other: "أخرى",
};

const ACCRUAL_TYPE_LABELS: Record<string, string> = {
  ...CLEARANCE_LINE_TYPE_LABELS,
  freight: "شحن دولي",
  local: "نقل محلي",
  total: "إجمالي",
};

export const accrualTypeLabel = (type: string): string => ACCRUAL_TYPE_LABELS[type] || type;

/** الأنواع المتاحة في محرّر «إضافة بنود» حسب نوع المستحق. */
export function accrualTypeOptions(kind: AccrualKind): string[] {
  if (kind === "freight") return ["freight", "other"];
  if (kind === "local") return ["local", "other"];
  return ["vat", "declaration_fee", "terminal", "permits", "broker_commission", "customs_system", "other"];
}

/** مبلغ عشري نصّي ← سنتات صحيحة، بلا انزلاق الفاصلة العائمة (0.1 + 0.2 = 0.3). */
export function toCents(value: string | number | null | undefined): number {
  const s = String(value ?? "").trim();
  const m = /^([+-]?)(\d*)(?:\.(\d*))?$/.exec(s);
  if (!m || (m[2] === "" && !m[3])) {
    const n = Number(s);
    return s !== "" && Number.isFinite(n) ? Math.round(n * 100) : 0;
  }
  const frac = (m[3] ?? "").padEnd(3, "0");
  let cents = Number(m[2] || "0") * 100 + Number(frac.slice(0, 2));
  if (Number(frac[2]) >= 5) cents += 1;
  return m[1] === "-" ? -cents : cents;
}

export interface FillLineDraft { label: string; type: string; amount: string }

export interface FillProgress { sumCents: number; totalCents: number; matches: boolean; canSave: boolean }

/** عدّاد «المجموع X من Y» والحفظ: يُفتح فقط حين يساوي المجموعُ الإجماليَّ بالسنت. */
export function fillProgress(lines: FillLineDraft[], total: string): FillProgress {
  const sumCents = lines.reduce((acc, l) => acc + toCents(l.amount), 0);
  const totalCents = toCents(total);
  const matches = sumCents === totalCents;
  const canSave = matches && lines.length > 0 && lines.every((l) => l.label.trim() !== "");
  return { sumCents, totalCents, matches, canSave };
}

/** لون صفّ الفرق: نقصُ المستحق أخضر، وزيادته أحمر، وبلا تغيّر محايد. */
export function diffRowClass(difference: string): string {
  const c = toCents(difference);
  if (c < 0) return "text-emerald-700";
  if (c > 0) return "text-red-600";
  return "";
}

export function diffRowBadge(status: AccrualDiffStatus): string | null {
  if (status === "new") return "جديد";
  if (status === "removed") return "محذوف";
  return null;
}

export function diffTotals(rows: AccrualDiffRow[]): { before: number; after: number; difference: number } {
  return rows.reduce(
    (acc, r) => ({
      before: acc.before + toCents(r.before),
      after: acc.after + toCents(r.after),
      difference: acc.difference + toCents(r.difference),
    }),
    { before: 0, after: 0, difference: 0 },
  );
}

/** مبلغ بإشارته: «+1,500» للزيادة و«-20.5» للنقص. */
export function signedMoney(value: string | number | null | undefined): string {
  const c = toCents(value);
  return `${c > 0 ? "+" : ""}${formatMoney(c / 100)}`;
}
