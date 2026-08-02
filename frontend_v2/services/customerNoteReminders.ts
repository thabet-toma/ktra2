import { fetchDueCustomerNoteReminders } from "./customerNotesApi";
import { notificationsService } from "./notificationsService";
import { resolveTenantId } from "../utils/tenantContext";

const LS_PREFIX = "ktra_cust_note_reminder_v1";

/**
 * تذكيرات ملاحظات الزبون: لكل ملاحظة غير منجزة حلّ يوم تذكيرها (أو تجاوزه)،
 * يُنشئ إشعاراً داخل الموقع يوجّه إلى بطاقة الزبون ← تبويب «ملاحظات الزبون»
 * مع تحديد الملاحظة. يمنع التكرار عبر localStorage مرة واحدة لكل
 * (شركة، ملاحظة، يوم تقويم) — على نمط تذكيرات وصول الشحنات.
 */
export async function runCustomerNoteReminders(userId: string): Promise<void> {
  if (!userId) return;
  let due;
  try {
    due = await fetchDueCustomerNoteReminders();
  } catch {
    return;
  }
  const tid = resolveTenantId();
  const todayKey = new Date().toISOString().slice(0, 10);
  for (const r of due) {
    const dedupe = `${LS_PREFIX}:${tid}:${r.id}:${todayKey}`;
    try {
      if (localStorage.getItem(dedupe)) continue;
    } catch {
      /* خاصية خاصة */
    }
    const partnerTarget = r.partner_id != null;
    await notificationsService.addNotification({
      userId: "all_managers",
      title: partnerTarget
        ? `تذكير طرف: ${r.partner_name}`
        : `تذكير: ${r.target_label || "المنصة"}`,
      message: r.title,
      type: partnerTarget ? "customer_note_reminder" : "platform_note_reminder",
      ...(partnerTarget
        ? {
            targetView: "partner-profile" as const,
            targetId: String(r.partner_id),
            targetTab: "customer_notes",
            targetSecondaryId: String(r.id),
          }
        : { targetPath: r.target_path || "/dashboard" }),
    });
    try {
      localStorage.setItem(dedupe, "1");
    } catch {
      /* ignore */
    }
  }
}
