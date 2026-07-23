import React from "react";

export type InvoicePaymentStatus = "paid" | "partially_paid" | "unpaid";

const META: Record<InvoicePaymentStatus, { label: string; className: string }> = {
  paid: {
    label: "مدفوعة بالكامل",
    className: "bg-green-100 text-green-700",
  },
  partially_paid: {
    label: "مدفوعة جزئياً",
    className: "bg-amber-100 text-amber-700",
  },
  unpaid: {
    label: "غير مدفوعة",
    className: "bg-red-100 text-red-700",
  },
};

export const PaymentStatusBadge: React.FC<{
  status?: InvoicePaymentStatus;
  label?: string;
}> = ({ status = "unpaid", label }) => {
  const meta = META[status];
  return (
    <span className={`inline-flex rounded px-2 py-0.5 text-xs font-semibold whitespace-nowrap ${meta.className}`}>
      {label || meta.label}
    </span>
  );
};
