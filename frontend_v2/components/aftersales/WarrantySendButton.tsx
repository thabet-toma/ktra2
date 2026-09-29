import React from "react";
import { ShareRowButton } from "../shared/ShareRowButton";
import { useCanSendWarranty } from "./useCanSendWarranty";

/**
 * #239 — «أرسل»: يفتح نافذة المشاركة القائمة بنوع الشهادة المناسب. شهادة
 * الفاتورة (`warranty_certificate` + رقم الفاتورة) أو بطاقةٌ واحدة
 * (`warranty_card` + رقم البطاقة). يختفي بلا أثر إن لم تُرخَّص الوحدة أو لم تتوفّر
 * صلاحية المشاركة.
 */
export const WarrantySendButton: React.FC<{
  docType: "warranty_certificate" | "warranty_card";
  docId: number;
  docLabel: string;
  partyName?: string;
  className?: string;
}> = ({ docType, docId, docLabel, partyName, className }) => {
  const allowed = useCanSendWarranty();
  if (!allowed) return null;
  return (
    <ShareRowButton
      docType={docType}
      docId={docId}
      docLabel={docLabel}
      partyName={partyName}
      className={className}
      label="أرسل"
    />
  );
};
