import React from "react";
import type { CustomerApprovalFields } from "../../services/salesApi";
import { customerApprovalBadge, customerApprovalTooltip } from "../../utils/customerApproval";

/**
 * شارة موافقة الزبون (T3) على الفاتورة وسند القبض والإرسالية: بانتظار / وافق / اعترض.
 * لا شيء يُعرض لـ`not_required` (كل ما تنشئه المنصة). الاسم والتاريخ والملاحظة في التلميح.
 */
export const CustomerApprovalBadge: React.FC<{ doc: CustomerApprovalFields }> = ({ doc }) => {
  const meta = customerApprovalBadge(doc.customer_approval_status, doc.customer_approval_status_display);
  if (!meta) return null;
  return (
    <span
      data-testid="customer-approval-badge"
      title={customerApprovalTooltip(doc) || undefined}
      className={`inline-flex whitespace-nowrap rounded px-2 py-0.5 text-xs font-semibold ${meta.className}`}
    >
      {meta.label}
    </span>
  );
};
