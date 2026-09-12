import React, { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronLeft, TrendingUp } from "lucide-react";

import {
  getCustomerProfitability,
  type ProfitabilityBoard,
  type ProfitabilityRow,
  type ProfitabilityState,
} from "../../services/platformProfitabilityApi";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";

const now = new Date();

const STATE_TONE: Record<ProfitabilityState, string> = {
  profitable: "bg-emerald-100 text-emerald-700",
  watch: "bg-amber-100 text-amber-700",
  reprice_or_upgrade: "bg-orange-100 text-orange-700",
  losing: "bg-rose-100 text-rose-700",
};

const displayError = (cause: unknown): string =>
  describePlatformOpsError(
    cause,
    "ربحيّةُ العملاء لمدير عمليات المنصّة وحدَه.",
    "تعذّر تحميل لوحة الربحيّة.",
  );

/**
 * `Customer Profitability / Plan Fit` (§٩) — **مؤشّرٌ تشغيليٌّ منفصلٌ** عن صحّة
 * الشركة وعن تقييم الموظّف، فلا يُخلَط صفُّه بصفوفهما.
 *
 * كلُّ رقمٍ يُفتح إلى مصادره: الصفُّ يُوسَّع فيُظهر مساهمةَ كلّ موظّفٍ ووحداتِه
 * وتكلفةَ وحدته. والاقتراحُ **يُعرَض ولا يُنفَّذ**: لا زرَّ ترقيةٍ هنا، لأنّ
 * المواصفة تشترط تأكيدَ السوبر أدمن عبر مسار الاشتراك نفسِه.
 */
export const ProfitabilityPanel: React.FC = () => {
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [expenses, setExpenses] = useState(0);
  const [board, setBoard] = useState<ProfitabilityBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openTenant, setOpenTenant] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setBoard(await getCustomerProfitability(year, month, expenses));
    } catch (cause) {
      setError(displayError(cause));
      setBoard(null);
    } finally {
      setLoading(false);
    }
  }, [year, month, expenses]);

  useEffect(() => { void load(); }, [load]);

  const renderRow = (row: ProfitabilityRow) => {
    const open = openTenant === row.tenant_id;
    return (
      <React.Fragment key={row.tenant_id}>
        <tr className="border-t border-slate-100">
          <td className="px-3 py-2">
            <button
              type="button"
              onClick={() => setOpenTenant(open ? null : row.tenant_id)}
              className="flex items-center gap-1 text-xs font-semibold text-slate-700"
            >
              {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
              {row.company_name}
            </button>
          </td>
          <td className="px-3 py-2 text-xs tabular-nums">{formatNumber(row.revenue)}</td>
          <td className="px-3 py-2 text-xs tabular-nums">{formatNumber(row.total_cost)}</td>
          <td className="px-3 py-2 text-xs tabular-nums">{formatNumber(row.margin)}</td>
          <td className="px-3 py-2 text-xs tabular-nums">
            {row.margin_pct === null ? "—" : `${formatNumber(row.margin_pct)}%`}
          </td>
          <td className="px-3 py-2">
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATE_TONE[row.state]}`}>
              {row.state_label}
            </span>
          </td>
        </tr>
        {open && (
          <tr className="bg-slate-50">
            <td colSpan={6} className="px-3 py-3">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <h4 className="mb-1 text-[11px] font-bold text-slate-600">مصادرُ الأرقام</h4>
                  <ul className="space-y-1 text-[11px] text-slate-600">
                    <li>
                      رسمٌ شهريّ {formatNumber(row.monthly_fee)} · وحداتٌ مستهلَكة{" "}
                      {formatNumber(row.chargeable_units)} من حصّةِ {formatNumber(row.included_quota)} ·
                      تجاوزٌ {formatNumber(row.overage_units)}
                    </li>
                    <li>
                      تكلفةٌ بشريّة {formatNumber(row.human_cost)} · نفقاتٌ مخصَّصة{" "}
                      {formatNumber(row.allocated_expenses)}
                    </li>
                  </ul>
                  {row.contributors.length === 0 ? (
                    <p className="mt-2 text-[11px] text-slate-500">لا وحداتٍ محتسَبةً لموظّفٍ هذا الشهر.</p>
                  ) : (
                    <table className="mt-2 w-full text-[11px]">
                      <thead className="text-slate-500">
                        <tr>
                          <th className="py-1 text-right font-medium">الموظّف</th>
                          <th className="py-1 text-right font-medium">وحدات</th>
                          <th className="py-1 text-right font-medium">تكلفةُ الوحدة</th>
                          <th className="py-1 text-right font-medium">التكلفة</th>
                        </tr>
                      </thead>
                      <tbody>
                        {row.contributors.map((contributor) => (
                          <tr key={contributor.employee_id} className="border-t border-slate-200">
                            <td className="py-1 tabular-nums">#{contributor.employee_id}</td>
                            <td className="py-1 tabular-nums">{formatNumber(contributor.units)}</td>
                            <td className="py-1 tabular-nums">{formatNumber(contributor.unit_cost)}</td>
                            <td className="py-1 tabular-nums">{formatNumber(contributor.cost)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
                <div>
                  <h4 className="mb-1 text-[11px] font-bold text-slate-600">اقتراحاتٌ للنظر — لا تُنفَّذ آلياً</h4>
                  {row.suggestions.length === 0 ? (
                    <p className="text-[11px] text-slate-500">لا اقتراحَ لهذه الشركة هذا الشهر.</p>
                  ) : (
                    <ul className="space-y-2">
                      {row.suggestions.map((suggestion) => (
                        <li key={suggestion.code} className="rounded-lg border border-slate-200 bg-white p-2">
                          <p className="text-[11px] font-semibold text-slate-700">{suggestion.label}</p>
                          <p className="text-[11px] text-slate-500">{suggestion.reason}</p>
                          <p className="mt-1 text-[11px] text-slate-400">
                            {Object.entries(suggestion.evidence)
                              .map(([key, value]) => `${key}: ${value === null ? "—" : formatNumber(Number(value))}`)
                              .join(" · ")}
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </td>
          </tr>
        )}
      </React.Fragment>
    );
  };

  return (
    <div className="space-y-4" dir="rtl">
      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="ml-auto flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-emerald-600" />
          <h2 className="text-sm font-bold text-slate-800">ربحيّةُ العميل ومطابقةُ الخطة</h2>
        </div>
        <label className="space-y-1 text-xs">
          <span className="text-slate-500">السنة</span>
          <input
            type="number"
            value={year}
            onChange={(event) => setYear(Number(event.target.value))}
            className="w-24 rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
          />
        </label>
        <label className="space-y-1 text-xs">
          <span className="text-slate-500">الشهر</span>
          <input
            type="number"
            min={1}
            max={12}
            value={month}
            onChange={(event) => setMonth(Number(event.target.value))}
            className="w-20 rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
          />
        </label>
        <label className="space-y-1 text-xs">
          {/* مُدخَلٌ لا مُشتَقّ: لا مصدرَ للنفقات المخصَّصة في المستودع، فتبقى صفراً حتى تُدخَل. */}
          <span className="text-slate-500">نفقاتٌ مخصَّصة لكلّ شركة</span>
          <input
            type="number"
            min={0}
            value={expenses}
            onChange={(event) => setExpenses(Math.max(0, Number(event.target.value)))}
            className="w-32 rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
          />
        </label>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">{error}</div>
      )}

      {loading ? (
        <p className="text-xs text-slate-500">جارٍ التحميل…</p>
      ) : !board || board.rows.length === 0 ? (
        <p className="rounded-xl border border-slate-200 bg-white p-4 text-xs text-slate-500">
          لا شركاتِ خدمةٍ مؤهَّلةً في هذا الشهر.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full min-w-[640px]">
            <thead className="bg-slate-50 text-[11px] text-slate-500">
              <tr>
                <th className="px-3 py-2 text-right font-medium">الشركة</th>
                <th className="px-3 py-2 text-right font-medium">الإيراد</th>
                <th className="px-3 py-2 text-right font-medium">التكلفة</th>
                <th className="px-3 py-2 text-right font-medium">الهامش</th>
                <th className="px-3 py-2 text-right font-medium">الهامش %</th>
                <th className="px-3 py-2 text-right font-medium">الحالة</th>
              </tr>
            </thead>
            <tbody>{board.rows.map(renderRow)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default ProfitabilityPanel;
