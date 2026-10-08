/**
 * T5 — إيقاف الطرف وتنشيطه من أيّ شاشة: الإيقاف يجلب أثره (`deactivation-impact/`) ويعرضه في
 * نافذة تأكيد قبل أن يُكتب شيء؛ التنشيط مباشر. الإيقاف جائز بأي رصيد — التحذير لا المنع.
 */
import { useCallback } from "react";
import { apiGetObject, apiPatchObject, apiPostObject } from "../services/restApi";
import { useConfirm } from "../contexts/ConfirmContext";
import { formatMoney } from "../utils/formatNumber";
import {
  bulkDeactivationConfirmMessage,
  deactivationConfirmMessage,
  type PartnerDeactivationImpact,
} from "../utils/partnerActiveStatus";

export function usePartnerActive(tenantId: number) {
  const confirm = useConfirm();

  /** يُعيد `true` إن تغيّرت الحالة، و`false` إن ألغى المستخدم. الأخطاء تصعد للمستدعي. */
  const setPartnerActive = useCallback(
    async (partner: { id: number; name: string }, nextActive: boolean): Promise<boolean> => {
      if (!nextActive) {
        const impact = await apiGetObject<PartnerDeactivationImpact>(
          `partners/${partner.id}/deactivation-impact/`, { tenantId },
        );
        const ok = await confirm({
          title: "إيقاف الطرف",
          message: deactivationConfirmMessage(partner.name, impact, (v) => formatMoney(v)),
          confirmText: "إيقاف",
          danger: false,
        });
        if (!ok) return false;
      }
      await apiPatchObject(`partners/${partner.id}/`, { is_active: nextActive }, { tenantId });
      return true;
    },
    [confirm, tenantId],
  );

  /** إيقاف/تنشيط جماعي؛ يُعيد عدد ما تغيّر، أو `null` إن ألغى المستخدم. */
  const bulkSetPartnersActive = useCallback(
    async (ids: number[], nextActive: boolean): Promise<number | null> => {
      if (!nextActive) {
        const impacts = await Promise.all(ids.map((id) => apiGetObject<PartnerDeactivationImpact>(
          `partners/${id}/deactivation-impact/`, { tenantId },
        )));
        const ok = await confirm({
          title: "إيقاف الأطراف المحدَّدة",
          message: bulkDeactivationConfirmMessage(ids.length, impacts),
          confirmText: "إيقاف",
          danger: false,
        });
        if (!ok) return null;
      }
      const res = await apiPostObject<{ updated: number }>(
        "partners/bulk-set-active/", { ids, is_active: nextActive }, { tenantId },
      );
      return res.updated;
    },
    [confirm, tenantId],
  );

  return { setPartnerActive, bulkSetPartnersActive };
}
