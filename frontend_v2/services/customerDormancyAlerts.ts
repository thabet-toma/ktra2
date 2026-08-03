import { getDormantCustomers } from "./salesApi";
import { notificationsService } from "./notificationsService";
import { resolveTenantId } from "../utils/tenantContext";

const LS_PREFIX = "ktra_cust_dormant_v1";

/**
 * تنبيه «العميل المختفي»: عميل كان يشتري ثم توقّف مدّة تتجاوز عتبة إعدادات
 * المبيعات (dormant_customer_days، افتراضها 30 يوماً) — يُنشئ إشعاراً داخل الموقع
 * يفتح بطاقة الزبون. المصدر الوحيد للحقيقة هو تقرير الخادم (فواتير بيع مرحّلة).
 *
 * يمنع التكرار عبر localStorage مرة واحدة لكل (شركة، عميل، تاريخ آخر شراء) —
 * أي إشعار واحد لكل «نوبة اختفاء»: لا يتكرّر يومياً، ويعود التنبيه من جديد إن
 * اشترى العميل ثم اختفى ثانيةً (تاريخ آخر شراء تغيّر ⇒ مفتاح جديد).
 */
export async function runCustomerDormancyAlerts(userId: string): Promise<void> {
  if (!userId) return;
  let rows;
  try {
    rows = await getDormantCustomers();
  } catch {
    return;
  }
  const tid = resolveTenantId();
  for (const r of rows) {
    const dedupe = `${LS_PREFIX}:${tid}:${r.partner_id}:${r.last_sale_date}`;
    try {
      if (localStorage.getItem(dedupe)) continue;
    } catch {
      /* خاصية خاصة */
    }
    const lastDoc = r.last_invoice_number ? ` (آخر فاتورة ${r.last_invoice_number})` : "";
    await notificationsService.addNotification({
      userId: "all_managers",
      title: `عميل مختفٍ: ${r.partner_name}`,
      message: `لم يشترِ منذ ${r.days_since} يوماً — آخر شراء ${r.last_sale_date}${lastDoc}.`,
      type: "customer_dormant",
      targetView: "partner-profile",
      targetId: String(r.partner_id),
    });
    try {
      localStorage.setItem(dedupe, "1");
    } catch {
      /* ignore */
    }
  }
}
