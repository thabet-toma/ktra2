import { shipmentsService } from "./shipmentsService";
import { notificationsService } from "./notificationsService";
import type { Shipment } from "../types";

const LS_PREFIX = "ktra_ship_eta_v1";

function parseArrivalDate(iso: string | undefined): Date | null {
  if (!iso || typeof iso !== "string") return null;
  const d = new Date(iso.slice(0, 10) + "T12:00:00");
  return Number.isNaN(d.getTime()) ? null : d;
}

/** فرق أيام التقويم (موجب = الوصول لاحقاً) */
function calendarDaysUntil(arrival: Date): number {
  const today = new Date();
  const a = new Date(arrival);
  today.setHours(0, 0, 0, 0);
  a.setHours(0, 0, 0, 0);
  return Math.round((a.getTime() - today.getTime()) / 86400000);
}

function shouldRemindShipment(s: Shipment): boolean {
  if (s.status === "draft" || s.status === "cancelled" || s.status === "delivered") return false;
  const route = (s.shippingInfo?.shipmentStatus?.status || "").toLowerCase();
  if (route.includes("released") || route.includes("sw_released")) return false;
  return true;
}

/**
 * إشعارات وصول الشحنة: عند بقاء ≤ 3 أيام على تاريخ الوصول (وما زالت في الطريق).
 * يمنع التكرار عبر localStorage مرة واحدة لكل (شحنة، يوم تقويم، قيمة العدّاد).
 */
export async function runShipmentArrivalReminders(userId: string): Promise<void> {
  if (!userId) return;
  let list: Shipment[];
  try {
    list = await shipmentsService.listShipmentsOnce();
  } catch {
    return;
  }
  const todayKey = new Date().toISOString().slice(0, 10);
  for (const s of list) {
    if (!shouldRemindShipment(s)) continue;
    const ad = parseArrivalDate(s.shippingInfo?.arrivalDate);
    if (!ad) continue;
    const days = calendarDaysUntil(ad);
    if (days < 0 || days > 3) continue;
    const dedupe = `${LS_PREFIX}:${s.id}:${todayKey}:${days}`;
    try {
      if (localStorage.getItem(dedupe)) continue;
    } catch {
      /* خاصية خاصة */
    }
    const num = s.shipmentNumber || `شحنة #${s.id}`;
    const dayWord =
      days === 0 ? "اليوم" : days === 1 ? "يوم واحد" : days === 2 ? "يومان" : `${days} أيام`;
    await notificationsService.addNotification({
      userId: "all_managers",
      title: "اقتراب وصول شحنة",
      message: `${num}: بقي ${dayWord} على تاريخ الوصول (${s.shippingInfo?.arrivalDate?.slice(0, 10) ?? ""}).`,
      type: "shipment_arrival_soon",
      targetId: s.id,
      targetView: "shipments-management",
    });
    try {
      localStorage.setItem(dedupe, "1");
    } catch {
      /* ignore */
    }
  }
}
