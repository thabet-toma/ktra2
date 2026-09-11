import React, { useState, useEffect, useCallback } from "react";
import { getCompanyHealth, type CompanyHealthData } from "../../services/platformOpsApi";
import {
  getHealthStatusMeta,
  formatRatingSampleNotice,
  formatReworkDiagnosticNotice,
} from "../../utils/agentBooks";
import { Activity, RefreshCw, AlertTriangle, Info, ChevronDown, ChevronUp } from "lucide-react";
import { formatNumber } from "../../utils/formatNumber";

interface CompanyHealthPanelProps {
  tenantId: number;
  onDrilldown?: (filter: { metric?: "active" | "overdue"; status?: string }) => void;
}

export const CompanyHealthPanel: React.FC<CompanyHealthPanelProps> = ({ tenantId, onDrilldown }) => {
  const [data, setData] = useState<CompanyHealthData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedService, setExpandedService] = useState<boolean>(false);
  const [expandedCustomer, setExpandedCustomer] = useState<boolean>(false);

  const fetchHealth = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await getCompanyHealth(tenantId);
      setData(res);
    } catch (err: any) {
      setError(err?.message || "تعذر تحميل مؤشرات صحة الشركة.");
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void fetchHealth();
  }, [fetchHealth]);

  if (loading) {
    return (
      <div className="p-4 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700 flex items-center justify-center gap-2 text-xs text-slate-500">
        <RefreshCw className="w-4 h-4 animate-spin text-emerald-600" />
        <span>جاري حساب مؤشرات الصحة عند الطلب...</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-xs text-red-700 dark:text-red-300 flex items-center justify-between">
        <span>{error || "تعذر تحميل مؤشرات الصحة."}</span>
        <button
          type="button"
          onClick={() => void fetchHealth()}
          className="font-semibold underline hover:no-underline text-[11px]"
        >
          إعادة المحاولة
        </button>
      </div>
    );
  }

  const { service_health, customer_cooperation, ratings_sample, rework_diagnostic } = data.health_scores;
  const serviceMeta = getHealthStatusMeta(service_health?.status);
  const customerMeta = getHealthStatusMeta(customer_cooperation?.status);

  const sampleNotice = formatRatingSampleNotice(
    ratings_sample?.size ?? 0,
    ratings_sample?.min_sample_size ?? 5,
    ratings_sample?.counts_against_score ?? false,
  );

  const reworkNotice = formatReworkDiagnosticNotice(
    rework_diagnostic?.cancelled_work_orders ?? 0,
  );

  return (
    <div className="mt-3 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 space-y-3 text-right" dir="rtl">
      <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700 pb-2">
        <h5 className="text-xs font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
          <Activity className="w-4 h-4 text-emerald-600" />
          مؤشرات الصحة والأداء (منفصلتان)
        </h5>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* صحة الخدمة */}
        <div className="rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 overflow-hidden transition">
          <button
            type="button"
            aria-expanded={expandedService}
            onClick={() => setExpandedService((prev) => !prev)}
            className="w-full text-right p-3 space-y-2 hover:bg-slate-50/70 dark:hover:bg-slate-800/40 transition block cursor-pointer"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                <span>صحة الخدمة</span>
                {expandedService ? (
                  <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
                ) : (
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                )}
              </span>
              <span
                className={`px-2 py-0.5 text-[10px] font-bold rounded-full border ${serviceMeta.colorClass} ${serviceMeta.bgClass} ${serviceMeta.borderClass}`}
              >
                {serviceMeta.label}
              </span>
            </div>
            <div className="text-xl font-extrabold text-slate-900 dark:text-slate-100">
              {service_health?.score != null ? `${formatNumber(service_health.score)}%` : "—"}
            </div>
            {!expandedService && service_health?.top_reasons && service_health.top_reasons.length > 0 && (
              <ul className="text-[11px] text-slate-500 space-y-0.5 pt-1 border-t border-slate-100 dark:border-slate-800">
                {service_health.top_reasons.slice(0, 3).map((r, i) => (
                  <li key={i} className="leading-relaxed">• {r}</li>
                ))}
              </ul>
            )}
          </button>

          {/* تفصيل الأسباب السببية المنسدلة داخل البطاقة */}
          {expandedService && (
            <div className="p-3 pt-0 border-t border-slate-100 dark:border-slate-800 space-y-1.5 text-xs">
              <div className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 pt-2 pb-1">
                تفصيل الخصومات والأسباب:
              </div>
              {service_health?.breakdown && service_health.breakdown.length > 0 ? (
                <div className="space-y-1">
                  {service_health.breakdown.map((cause) => (
                    <div
                      key={cause.reason_key}
                      className="p-2 rounded bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-700/60 flex items-center justify-between text-[11px]"
                    >
                      <div className="space-y-0.5">
                        <span className="font-medium text-slate-800 dark:text-slate-200">
                          {cause.label}
                        </span>
                        <div className="text-[10px] text-slate-500">
                          العدد: {formatNumber(cause.count)}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {cause.deduction > 0 ? (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-300 border border-red-200 dark:border-red-800">
                            -{formatNumber(cause.deduction)} نقطة
                          </span>
                        ) : (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                            0 نقطة
                          </span>
                        )}
                        {/* رابط تنقيب اختياري ومحدد بدقة لسبب تجاوز الأجل فقط */}
                        {cause.reason_key === "sla_breaches" && onDrilldown && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onDrilldown({ metric: "overdue" });
                            }}
                            className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 hover:underline px-1 cursor-pointer"
                          >
                            عرض الأعمال
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-[11px] text-slate-500 py-1">
                  لا توجد خصومات على صحة الخدمة (١٠٠٪).
                </div>
              )}
            </div>
          )}
        </div>

        {/* تعاون الزبون */}
        <div className="rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 overflow-hidden transition">
          <button
            type="button"
            aria-expanded={expandedCustomer}
            onClick={() => setExpandedCustomer((prev) => !prev)}
            className="w-full text-right p-3 space-y-2 hover:bg-slate-50/70 dark:hover:bg-slate-800/40 transition block cursor-pointer"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                <span>تعاون الزبون</span>
                {expandedCustomer ? (
                  <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
                ) : (
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                )}
              </span>
              <span
                className={`px-2 py-0.5 text-[10px] font-bold rounded-full border ${customerMeta.colorClass} ${customerMeta.bgClass} ${customerMeta.borderClass}`}
              >
                {customerMeta.label}
              </span>
            </div>
            <div className="text-xl font-extrabold text-slate-900 dark:text-slate-100">
              {customer_cooperation?.score != null ? `${formatNumber(customer_cooperation.score)}%` : "—"}
            </div>
            {!expandedCustomer && customer_cooperation?.top_reasons && customer_cooperation.top_reasons.length > 0 && (
              <ul className="text-[11px] text-slate-500 space-y-0.5 pt-1 border-t border-slate-100 dark:border-slate-800">
                {customer_cooperation.top_reasons.slice(0, 3).map((r, i) => (
                  <li key={i} className="leading-relaxed">• {r}</li>
                ))}
              </ul>
            )}
          </button>

          {/* تفصيل الأسباب السببية المنسدلة داخل البطاقة */}
          {expandedCustomer && (
            <div className="p-3 pt-0 border-t border-slate-100 dark:border-slate-800 space-y-1.5 text-xs">
              <div className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 pt-2 pb-1">
                تفصيل الخصومات والأسباب:
              </div>
              {customer_cooperation?.breakdown && customer_cooperation.breakdown.length > 0 ? (
                <div className="space-y-1">
                  {customer_cooperation.breakdown.map((cause) => (
                    <div
                      key={cause.reason_key}
                      className="p-2 rounded bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-700/60 flex items-center justify-between text-[11px]"
                    >
                      <div className="space-y-0.5">
                        <span className="font-medium text-slate-800 dark:text-slate-200">
                          {cause.label}
                        </span>
                        <div className="text-[10px] text-slate-500">
                          العدد: {formatNumber(cause.count)}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {cause.deduction > 0 ? (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-300 border border-red-200 dark:border-red-800">
                            -{formatNumber(cause.deduction)} نقطة
                          </span>
                        ) : (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                            0 نقطة
                          </span>
                        )}
                        {/* رابط تنقيب اختياري ومحدد بدقة لسبب بانتظار رد الزبون فقط */}
                        {cause.reason_key === "waiting_customer" && onDrilldown && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onDrilldown({ status: "waiting_customer" });
                            }}
                            className="text-[10px] font-semibold text-blue-600 dark:text-blue-400 hover:underline px-1 cursor-pointer"
                          >
                            عرض الأعمال
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-[11px] text-slate-500 py-1">
                  لا توجد خصومات على تعاون الزبون (١٠٠٪).
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* تنبيهات العينة والتشخيص */}
      <div className="space-y-1.5 pt-1 text-[11px]">
        {sampleNotice && (
          <div className="p-2 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 flex items-center gap-1.5">
            <Info className="w-3.5 h-3.5 text-slate-500 flex-shrink-0" />
            <span>{sampleNotice}</span>
          </div>
        )}
        {reworkNotice && (
          <div className="p-2 rounded bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800 flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600 flex-shrink-0" />
            <span>{reworkNotice}</span>
          </div>
        )}
      </div>
    </div>
  );
};
