import { apiGetObject, apiPostObject } from "./restApi";
import type { Tenant } from "../contexts/CompanyContext";

/**
 * ISSUE #65 — دفاتر عملاء المكتب. النقطة قائمة منذ #52 وبلا مستدعٍ في الواجهة:
 * `GET/POST /api/tenants/companies/{office}/managed-books/`.
 *
 * **الإنشاء من هنا وحده**: `POST /api/tenants/companies/` ينشئ شركةً عادية بلا
 * `managed_by` وبلا فحص حصّة `office.managed_books` — فدفترٌ فُتح من ذاك الباب
 * يظهر في مبدّل الشركات العادي ولا يُحسب على المكتب.
 *
 * ونثبّت `X-Tenant-Id` على المكتب في الحالتين: الشركة النشطة قد تكون دفتر عميلٍ
 * نحن داخله الآن، والترويسة تمرّ على حارس قناع القالب (`TemplateSurfacePermission`).
 */
const path = (officeId: number) => `tenants/companies/${officeId}/managed-books/`;

export const listManagedBooks = (officeId: number) =>
  apiGetObject<Tenant[]>(path(officeId), { tenantId: officeId });

export const createManagedBook = (
  officeId: number,
  body: { CompanyName: string; template: string },
) => apiPostObject<Tenant>(path(officeId), body, { tenantId: officeId });
