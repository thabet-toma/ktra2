/**
 * TKT-DEV-1 — جسم الجهاز يُبنى في مكانٍ واحد.
 *
 * نموذجان يكتبان السجل نفسه: «الاستقبال» في `SensitiveDevicesScreen.tsx` (بلا
 * `status` — الخادم يفترض الحالة الأولى) و«التعديل» في `DeviceDetailModal.tsx`
 * (معها). نسختان من التطبيع تتباعدان: تنسى إحداهما `photo_url` فتبدو «إزالة
 * الصورة» ناجحة والرابط لم يصل (والتحديث الجزئي الذي لا يحمل المفتاح يُبقي
 * القيمة القديمة — لا يمحوها)، أو تنقصها خانةٌ من `imei` فيرفض الخادم.
 *
 * وحدة نقية بلا شبكة — تُستورَد في اختبارات Node بلا متصفّح.
 */
import type { DeviceDraft } from "../services/devicesApi.ts";
import { imeiDigits, normalizePhone } from "./imei.ts";

/**
 * الجسم الذي يُرسَل للخادم: كل حقول المسودّة إلزاميةً — فحذف حقلٍ من هنا (كأن
 * يُنسى `photo_url`) يُسقط `tsc` قبل أن يصل إلى الخادم — و`status` اختيارية
 * بحسب النموذج الذي يبني الجسم (تسجيلٌ بلا حالة، تعديلٌ معها).
 */
export function buildDeviceBody(
  draft: DeviceDraft,
): Required<Omit<DeviceDraft, "status">> & Pick<DeviceDraft, "status"> {
  const body: Required<Omit<DeviceDraft, "status">> = {
    customer_name: draft.customer_name.trim(),
    customer_phone: normalizePhone(draft.customer_phone),
    model_name: draft.model_name.trim(),
    serial_number: draft.serial_number.trim(),
    imei: imeiDigits(draft.imei),
    technical_notes: draft.technical_notes,
    photo_url: draft.photo_url,
  };
  return draft.status ? { ...body, status: draft.status } : body;
}
