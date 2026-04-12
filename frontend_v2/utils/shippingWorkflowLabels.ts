import type { ShippingWorkflowStatus } from "@/types/deal";

export const SHIPPING_WORKFLOW_LABELS: Record<ShippingWorkflowStatus, string> = {
  sw_mfg_start: "بدء التصنيع",
  sw_wait_agent_ship: "تم التصنيع وبانتظار الشحن للوكيل",
  sw_wait_intl_ship: "تم الشحن للوكيل وبانتظار الشحن الدولي",
  sw_wait_arrival: "بانتظار وصول الشحنة",
  sw_wait_clearance: "بانتظار إجراءات التخليص",
  sw_released: "مفرج عنها",
};

export function getShippingWorkflowLabel(
  code: ShippingWorkflowStatus | null | undefined
): string {
  if (!code) return "لم يُحدد وضع الشحنة";
  return SHIPPING_WORKFLOW_LABELS[code] ?? code;
}

export function getShippingWorkflowBadgeClass(
  code: ShippingWorkflowStatus | null | undefined
): string {
  const styles: Record<ShippingWorkflowStatus | "unset", string> = {
    unset:
      "bg-gray-100 text-gray-700 border-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700",
    sw_mfg_start:
      "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/20 dark:text-blue-300 dark:border-blue-800",
    sw_wait_agent_ship:
      "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-900/20 dark:text-indigo-300 dark:border-indigo-800",
    sw_wait_intl_ship:
      "bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-900/20 dark:text-teal-300 dark:border-teal-800",
    sw_wait_arrival:
      "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-900/20 dark:text-amber-300 dark:border-amber-800",
    sw_wait_clearance:
      "bg-orange-50 text-orange-800 border-orange-200 dark:bg-orange-900/20 dark:text-orange-300 dark:border-orange-800",
    sw_released:
      "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-300 dark:border-emerald-800",
  };
  const key = (code ?? "unset") as ShippingWorkflowStatus | "unset";
  return styles[key] ?? styles.unset;
}
