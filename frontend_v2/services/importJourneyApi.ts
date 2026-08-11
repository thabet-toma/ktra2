import { apiGetObject } from "./restApi";
import { resolveTenantId } from "@/utils/tenantContext";
import type { ImportJourneySummaryFacts } from "@/components/import-flow/importJourneyGuidance";

/**
 * وقائع رحلات الاستيراد النشطة — نداء واحد يغذّي المرشد العام في كل الشاشات.
 * القرار (أي مرحلة وأي زر) يُحسب في الواجهة من `importJourneyGuidance`.
 */
export function fetchImportJourneySummary(): Promise<ImportJourneySummaryFacts> {
  return apiGetObject<ImportJourneySummaryFacts>("logistics/import-journey/", {
    tenantId: resolveTenantId(),
  });
}
