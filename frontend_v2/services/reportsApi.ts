/**
 * T-REPORTS: عميل قسم التقارير — نقطتان لا أكثر.
 * كل تقرير جديد في الخادم يظهر هنا تلقائياً بلا سطر واجهة إضافي.
 */
import { apiGetObject } from "./restApi";
import { resolveTenantId } from "../utils/tenantContext";
import {
  reportQuery,
  type ReportCategoryDto,
  type ReportDrillResultDto,
  type ReportResultDto,
} from "../utils/reportFormat";

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

  /**
   * فتح صفّ مجمَّع على الأسطر التي كوّنته.
   *
   * تُرسَل **نفس** فلاتر التشغيل ومعها مفاتيح الصفّ — لا مجموعة ثانية: لو فلتر
   * التنقيب بغير ما فلتر به التقرير لاختلف مجموعُه عن الرقم الذي فُتح لأجله،
   * وهو بالضبط ما جاء التنقيب ليُثبته.
   */
  drill: (
    key: string,
    filters: Record<string, string>,
    rowKeys: Record<string, string>,
  ): Promise<ReportDrillResultDto> => {
    // `reportQuery` يُسقط الفارغ، ومفتاح الصفّ قد يكون فارغاً بحقّ (مستودعٌ غير
    // محدَّد، ماركةٌ بلا اسم)، فيُضمّ بعده كي لا يسقط ويفتح الصفَّ على غيره.
    const query = new URLSearchParams(reportQuery(filters));
    for (const [name, value] of Object.entries(rowKeys)) query.set(name, value ?? "");
    return apiGetObject<ReportDrillResultDto>(
      `reports/${encodeURIComponent(key)}/drill/?${query.toString()}`,
      { tenantId: resolveTenantId() },
    );
  },
};
