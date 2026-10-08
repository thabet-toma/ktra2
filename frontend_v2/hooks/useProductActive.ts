/**
 * T4 — إيقاف المنتج وتنشيطه من أيّ شاشة: الإيقاف يجلب أثره (`deactivation-impact/`) ويعرضه في
 * نافذة تأكيد قبل أن يُكتب شيء؛ التنشيط مباشر. الإيقاف جائز بأي رصيد — التحذير لا المنع.
 */
import { useCallback } from "react";
import { inventoryApi } from "../services/inventoryApi";
import { useConfirm } from "../contexts/ConfirmContext";
import { eventBus } from "../utils/eventBus";
import { formatQuantity } from "../utils/formatNumber";
import { resolveTenantId } from "../utils/tenantContext";
import { familyDeactivationConfirmMessage, productDeactivationConfirmMessage } from "../utils/productActiveStatus";

export function useProductActive() {
  const confirm = useConfirm();

  /**
   * يُعيد `true` إن تغيّرت الحالة، و`false` إن ألغى المستخدم. الأخطاء تصعد للمستدعي.
   * `memberIds` (أكثر من واحد) = صفّ منتجٍ ببراندات: الإجراء على كل براندَاته معاً.
   */
  const setProductActive = useCallback(
    async (
      product: { id: number; name: string; memberIds?: number[] },
      nextActive: boolean,
    ): Promise<boolean> => {
      const ids = product.memberIds && product.memberIds.length > 1 ? product.memberIds : [product.id];
      if (!nextActive) {
        const impacts = await Promise.all(ids.map((id) => inventoryApi.getProductDeactivationImpact(id)));
        const message = ids.length > 1
          ? familyDeactivationConfirmMessage(product.name, impacts, (v) => formatQuantity(v))
          : productDeactivationConfirmMessage(product.name, impacts[0], (v) => formatQuantity(v));
        const ok = await confirm({
          title: "إيقاف المنتج",
          message,
          confirmText: "إيقاف",
          danger: false,
        });
        if (!ok) return false;
      }
      if (ids.length > 1) await inventoryApi.bulkSetProductsActive(ids, nextActive);
      else await inventoryApi.setProductActive(ids[0], nextActive);
      // الشاشات التي تحمل قائمتها الخاصة (فاتورة مفتوحة في تبويب آخر) تُنعش قائمة منتقيها.
      eventBus.publish("products", resolveTenantId());
      return true;
    },
    [confirm],
  );

  return { setProductActive };
}
