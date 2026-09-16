import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Building2 } from "lucide-react";

import {
  listMyEngagedCompanies,
  type EmployeeEngagedCompanyRow,
} from "../../services/platformEmployeeSpaceApi";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { CcCard, CcEmpty, CcPill, CcProgress, CcSkeleton } from "./ui";

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "هذه القائمة لموظفي عمليات المنصة فقط.", "تعذّر تحميل شركاتك.");

/**
 * شركاتُ ارتباطات الموظّف: حصّةُ كلٍّ وبنودُ صحّتها **المُسنَدةُ إليه** (القصّتان ٣٩، ٤٠).
 *
 * القصة ٤٠ تقول السببَ صراحةً: «لكي **لا أعد العميل بخدمة تتجاوز خطته**» — فالرقمُ
 * المهمُّ هو المتبقّي، ويُعرَض تحذيراً حين ينفد لا رصيداً بالسالب: «-٧ متبقّية» ليست
 * كميّةً متبقّيةً بل زيادةً مستهلَكة، والخادمُ يفصلهما (`remaining_quota`/`over_quota`).
 */
export const EmployeeCompaniesPanel: React.FC = () => {
  const [rows, setRows] = useState<EmployeeEngagedCompanyRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await listMyEngagedCompanies());
    } catch (cause) {
      setError(displayError(cause));
      setRows(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (loading) return <CcSkeleton variant="card" count={2} />;

  if (error) {
    return (
      <CcCard tone="danger" className="flex items-center justify-between p-3 text-xs" dir="rtl">
        <span className="text-rose-400 font-semibold">{error}</span>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 px-3 py-1 text-[11px] font-bold transition-colors"
        >
          إعادة المحاولة
        </button>
      </CcCard>
    );
  }

  if (!rows || rows.length === 0) {
    return (
      <CcEmpty title="لا شركاتِ ارتباطٍ نشطةٍ لك حالياً." />
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4" dir="rtl">
      {rows.map((row) => {
        const exhausted = row.remaining_quota === 0;
        return (
          <CcCard key={row.tenant_id} className="p-4 space-y-4">
            <header className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Building2 className="h-5 w-5 text-sky-400 shrink-0" />
                <h3 className="text-sm font-bold text-cc-text">{row.company_name}</h3>
              </div>
              <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                <CcPill tone="neutral">
                  المشمول: {formatNumber(row.included_quota)}
                </CcPill>
                <CcPill tone="neutral">
                  المستهلَك: {formatNumber(row.consumed_quota)}
                </CcPill>
                {row.over_quota > 0 ? (
                  <CcPill tone="danger">
                    تجاوزٌ: {formatNumber(row.over_quota)} وحدة فوق الخطة
                  </CcPill>
                ) : (
                  <CcPill tone={exhausted ? "warning" : "success"}>
                    المتبقّي: {formatNumber(row.remaining_quota)}
                  </CcPill>
                )}
              </div>
            </header>

            {row.included_quota > 0 && (
              <CcProgress
                value={row.consumed_quota}
                max={row.included_quota}
                tone={row.over_quota > 0 ? "danger" : exhausted ? "warning" : "accent"}
                label="استهلاك الحصة"
              />
            )}

            {(row.over_quota > 0 || exhausted) && (
              <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-2.5 text-[11px] text-amber-300">
                <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
                <span>لا تَعِد العميلَ بعملٍ إضافيٍّ على هذه الخطة قبل مراجعة مدير العمليات.</span>
              </div>
            )}

            <div className="space-y-2 border-t border-cc-border pt-3">
              <h4 className="text-xs font-bold text-cc-text">بنودُ الصحّة المطلوبُ منك علاجُها</h4>
              {row.health_items.length === 0 ? (
                <p className="text-xs text-cc-text-muted">لا بنودَ مُسنَدةً إليك في أحدث فحصٍ معتمد.</p>
              ) : (
                <ul className="space-y-2">
                  {row.health_items.map((item) => (
                    <li key={item.id} className="rounded-lg border border-cc-border bg-cc-surface-2 p-2.5 text-xs space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <CcPill tone={item.status === "risk" ? "danger" : "warning"}>
                          {item.status_display}
                        </CcPill>
                        <span className="font-semibold text-cc-text">{item.code}</span>
                        {item.mandatory && (
                          <CcPill tone="neutral">إلزاميّ للاعتماد</CcPill>
                        )}
                        {item.due_date && (
                          <span className="text-[10px] text-cc-text-muted">الموعد: {formatDateValue(item.due_date)}</span>
                        )}
                      </div>
                      {item.action && <p className="text-cc-text text-xs">{item.action}</p>}
                      {item.evidence_note && <p className="text-[11px] text-cc-text-muted">{item.evidence_note}</p>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </CcCard>
        );
      })}
    </div>
  );
};

export default EmployeeCompaniesPanel;
