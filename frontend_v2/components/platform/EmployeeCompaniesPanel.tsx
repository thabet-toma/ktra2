import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Building2 } from "lucide-react";

import {
  listMyEngagedCompanies,
  type EmployeeEngagedCompanyRow,
} from "../../services/platformEmployeeSpaceApi";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";

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

  if (loading) return <div className="py-10 text-center text-xs text-slate-400">جاري التحميل...</div>;

  if (error) {
    return (
      <div className="flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800" dir="rtl">
        <span>{error}</span>
        <button type="button" onClick={() => void load()} className="rounded-lg bg-rose-100 px-3 py-1 text-[11px] font-bold hover:bg-rose-200">
          إعادة المحاولة
        </button>
      </div>
    );
  }

  if (!rows || rows.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white py-10 text-center text-xs text-slate-400" dir="rtl">
        لا شركاتِ ارتباطٍ نشطةٍ لك حالياً.
      </div>
    );
  }

  return (
    <div className="space-y-4" dir="rtl">
      {rows.map((row) => {
        const exhausted = row.remaining_quota === 0;
        return (
          <section key={row.tenant_id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Building2 className="h-4 w-4 text-slate-500" />
                <h3 className="text-sm font-bold text-slate-800">{row.company_name}</h3>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-[11px]">
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">
                  المشمول: {formatNumber(row.included_quota)}
                </span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">
                  المستهلَك: {formatNumber(row.consumed_quota)}
                </span>
                {row.over_quota > 0 ? (
                  <span className="rounded-full bg-rose-100 px-2 py-0.5 font-bold text-rose-700">
                    تجاوزٌ: {formatNumber(row.over_quota)} وحدة فوق الخطة
                  </span>
                ) : (
                  <span className={`rounded-full px-2 py-0.5 font-bold ${exhausted ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-700"}`}>
                    المتبقّي: {formatNumber(row.remaining_quota)}
                  </span>
                )}
              </div>
            </header>

            {(row.over_quota > 0 || exhausted) && (
              <p className="mb-3 flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-800">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
                لا تَعِد العميلَ بعملٍ إضافيٍّ على هذه الخطة قبل مراجعة مدير العمليات.
              </p>
            )}

            <h4 className="mb-1.5 text-xs font-bold text-slate-700">بنودُ الصحّة المطلوبُ منك علاجُها</h4>
            {row.health_items.length === 0 ? (
              <p className="text-xs text-slate-500">لا بنودَ مُسنَدةً إليك في أحدث فحصٍ معتمد.</p>
            ) : (
              <ul className="space-y-1.5">
                {row.health_items.map((item) => (
                  <li key={item.id} className="rounded-lg border border-slate-100 bg-slate-50 p-2 text-xs">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${item.status === "risk" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"}`}>
                        {item.status_display}
                      </span>
                      <span className="font-semibold text-slate-800">{item.code}</span>
                      {item.mandatory && (
                        <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] text-slate-700">إلزاميّ للاعتماد</span>
                      )}
                      {item.due_date && (
                        <span className="text-[10px] text-slate-500">الموعد: {formatDateValue(item.due_date)}</span>
                      )}
                    </div>
                    {item.action && <p className="mt-1 text-slate-600">{item.action}</p>}
                    {item.evidence_note && <p className="mt-0.5 text-[11px] text-slate-500">{item.evidence_note}</p>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
};

export default EmployeeCompaniesPanel;
