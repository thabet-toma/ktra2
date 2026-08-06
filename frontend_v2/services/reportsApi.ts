/**
 * T-REPORTS: عميل قسم التقارير — نقطتان لا أكثر.
 * كل تقرير جديد في الخادم يظهر هنا تلقائياً بلا سطر واجهة إضافي.
 */
import { apiGetObject } from "./restApi";
import { resolveTenantId } from "../utils/tenantContext";
import { reportQuery, type ReportCategoryDto, type ReportResultDto } from "../utils/reportFormat";

export const reportsApi = {
  /** فهرس التقارير مجمَّعاً بالفئات — مصفّى بصلاحيات المستخدم من الخادم. */
  catalog: async (): Promise<ReportCategoryDto[]> => {
    const data = await apiGetObject<{ categories: ReportCategoryDto[] }>(
      "reports/", { tenantId: resolveTenantId() },
    );
    return data?.categories || [];
  },

  /** تشغيل تقرير بفلاتره. الفلاتر الفارغة لا تُرسَل. */
  run: (key: string, filters: Record<string, string>): Promise<ReportResultDto> => {
    const query = new URLSearchParams(reportQuery(filters)).toString();
    return apiGetObject<ReportResultDto>(
      `reports/${encodeURIComponent(key)}/${query ? `?${query}` : ""}`,
      { tenantId: resolveTenantId() },
    );
  },
};
