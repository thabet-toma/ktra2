import { formatDateValue } from "./formatDate.ts";

/**
 * موافقة الزبون على المستند (T2/T3): فاتورة بيع وإرسالية وسند قبض جهّزها تطبيق المستودع
 * الخارجي ويقرّها الزبون أو يعترض. `not_required` هو الأصل لكل ما تنشئه المنصة — لا شارة ولا
 * تحذير. القيم تطابق `CustomerApprovalFields.APPROVAL_*` في `sales/models.py`.
 */
export type CustomerApprovalStatus = "not_required" | "pending" | "approved" | "rejected";

export type CustomerApprovalBadgeMeta = { label: string; className: string };

// ألوان الشارات كما في `PaymentStatusBadge` (أخضر/كهرماني/أحمر) — بلا inline styles.
const META: Record<Exclude<CustomerApprovalStatus, "not_required">, CustomerApprovalBadgeMeta> = {
  pending: { label: "بانتظار موافقة الزبون", className: "bg-amber-100 text-amber-700" },
  approved: { label: "وافق الزبون", className: "bg-green-100 text-green-700" },
  rejected: { label: "اعترض الزبون", className: "bg-red-100 text-red-700" },
};

/** نص الشارة وصنفها؛ `null` ⇒ لا تُعرض شارة (`not_required` أو غياب الحقل أو قيمة مجهولة). */
export function customerApprovalBadge(
  status: string | null | undefined,
  display?: string | null,
): CustomerApprovalBadgeMeta | null {
  if (status !== "pending" && status !== "approved" && status !== "rejected") return null;
  const meta = META[status];
  return { label: display || meta.label, className: meta.className };
}

/** هل يستحق الترحيل تحذير المحاسب؟ بانتظار أو اعتراض فقط (الموافق والمنصّة لا). */
export function needsApprovalWarning(status: string | null | undefined): boolean {
  return status === "pending" || status === "rejected";
}

/** تلميح الشارة: من قرّر ومتى وملاحظته (التاريخ عبر `formatDateValue`). */
export function customerApprovalTooltip(doc: {
  customer_approval_by?: string | null;
  customer_approval_at?: string | null;
  customer_approval_note?: string | null;
}): string {
  const parts: string[] = [];
  if (doc.customer_approval_by) parts.push(doc.customer_approval_by);
  const at = formatDateValue(doc.customer_approval_at);
  if (at) parts.push(at);
  const head = parts.join(" — ");
  const note = (doc.customer_approval_note || "").trim();
  return [head, note].filter(Boolean).join("\n");
}

/**
 * سبب التحذير بنفس صياغة الخادم (`approval_post_issue`) لسؤال التأكيد قبل الترحيل:
 * «بانتظار موافقة الزبون» أو «اعترض الزبون (الاسم) — الملاحظة». فارغ حين لا تحذير.
 */
export function approvalWarningReason(doc: {
  customer_approval_status?: string | null;
  customer_approval_by?: string | null;
  customer_approval_note?: string | null;
}): string {
  if (doc.customer_approval_status === "pending") return META.pending.label;
  if (doc.customer_approval_status !== "rejected") return "";
  let text = META.rejected.label;
  const by = (doc.customer_approval_by || "").trim();
  const note = (doc.customer_approval_note || "").trim();
  if (by) text += ` (${by})`;
  if (note) text += ` — ${note}`;
  return text;
}

/** حقول الموافقة وحدها من مستندٍ أعاده الخادم — حالة الشاشة لا تحمل المستند كله. */
export function pickCustomerApproval(doc: {
  customer_approval_status?: CustomerApprovalStatus;
  customer_approval_status_display?: string;
  customer_approval_at?: string | null;
  customer_approval_by?: string;
  customer_approval_note?: string;
}) {
  return {
    customer_approval_status: doc.customer_approval_status,
    customer_approval_status_display: doc.customer_approval_status_display,
    customer_approval_at: doc.customer_approval_at,
    customer_approval_by: doc.customer_approval_by,
    customer_approval_note: doc.customer_approval_note,
  };
}
