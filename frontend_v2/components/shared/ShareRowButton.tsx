/**
 * زرّ «مشاركة» داخل صفّ قائمة — يحمل حالته ونافذته معه.
 *
 * شاشاتُ القوائم (السندات، الإرساليات، الإشعارات، الكفالات، أوامر الصيانة)
 * لا محرّرَ مستندٍ لها بشريط أدوات، فالمشاركة تسكن في خلية إجراءات الصفّ.
 * وتكرارُ ثلاثيّة «حالة + نافذة + زرّ» في كل شاشة كان يعني سبع نسخٍ تنحرف:
 * واحدةٌ تنسى `partyName`، وأخرى تُبقي النافذة مركّبةً بعد الإغلاق.
 *
 * **والنافذة تُركَّب عند الفتح فقط** (`open &&`)، فقائمةٌ بمئة صفّ لا تُنشئ
 * مئة نافذة ولا مئة نداء `listDocumentShares` — النداء يقع داخل النافذة عند
 * تركيبها.
 */
import React, { useState } from "react";
import { Share2 } from "lucide-react";

import { ShareDocumentModal } from "./ShareDocumentModal";
import type { ShareDocType } from "../../services/docShareApi";

export interface ShareRowButtonProps {
  docType: ShareDocType;
  docId: number;
  /** «سند قبض #12» — يظهر في العنوان وفي نصّ رسالة واتساب. */
  docLabel: string;
  /** اسم الطرف (زبون أو مورّد)، لتحية الرسالة. */
  partyName?: string;
  /** صنف الزرّ — ليطابق بقيّة أزرار الصفّ في الشاشة المضيفة. */
  className?: string;
  /** نصّ الزرّ. أيقونةٌ وحدها حين يكون الصفّ ضيّقاً. */
  label?: string;
  /** يُستدعى بعد إنشاء أول رابط — لتحديث القائمة عند المستدعي. */
  onShared?: () => void;
}

export const ShareRowButton: React.FC<ShareRowButtonProps> = ({
  docType,
  docId,
  docLabel,
  partyName,
  className = "text-blue-600 hover:underline",
  label = "مشاركة",
  onShared,
}) => {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        className={className}
        title="مشاركة برابط عام"
        onClick={() => setOpen(true)}
      >
        <Share2 className="inline h-3.5 w-3.5" />
        {label ? <span className="ms-1">{label}</span> : null}
      </button>
      {open && (
        <ShareDocumentModal
          open
          onClose={() => setOpen(false)}
          docType={docType}
          docId={docId}
          docLabel={docLabel}
          partyName={partyName}
          onShared={onShared ? () => onShared() : undefined}
        />
      )}
    </>
  );
};
