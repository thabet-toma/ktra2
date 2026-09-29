import { usePermissions } from "../../contexts/PermissionsContext";

/**
 * #239 — هل يظهر زرّ «أرسل» للشهادة؟ الوحدة مرخّصة **و** صلاحية مشاركة
 * المستندات (`sales.document.share`)، وهما شرطا الخادم نفسهما على
 * `warranty_card` و`warranty_certificate`. الخادم يفرضهما مرةً ثانية؛ هذا
 * يمنع ظهور زرٍّ سيردّه الخادم.
 */
export function useCanSendWarranty(): boolean {
  const { modules, can } = usePermissions();
  return Boolean(modules["after_sales"]) && can("sales.document.share");
}
