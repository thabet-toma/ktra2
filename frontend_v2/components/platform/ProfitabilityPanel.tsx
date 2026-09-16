import React, { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronLeft } from "lucide-react";

import {
  getCustomerProfitability,
  type ProfitabilityBoard,
  type ProfitabilityRow,
  type ProfitabilityState,
} from "../../services/platformProfitabilityApi";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { type CcTone } from "../../utils/ccTone";
import {
  CcCard,
  CcEmpty,
  CcPill,
  CcSectionTitle,
  CcSkeleton,
  CcTable,
  CcTd,
  CcTh,
  CcThead,
  CcTr,
} from "./ui";

const now = new Date();

const STATE_TONE: Record<ProfitabilityState, CcTone> = {
  profitable: "success",
  watch: "warning",
  reprice_or_upgrade: "warning",
  losing: "danger",
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
        <CcTr className={open ? "bg-cc-surface-2/40" : ""}>
          <CcTd>
            <button
              type="button"
              onClick={() => setOpenTenant(open ? null : row.tenant_id)}
              className="flex items-center gap-1.5 text-xs font-semibold text-cc-text hover:text-sky-400 transition"
            >
              {open ? <ChevronDown className="h-3.5 w-3.5 text-sky-400" /> : <ChevronLeft className="h-3.5 w-3.5 text-cc-text-muted" />}
              {row.company_name}
            </button>
          </CcTd>
          <CcTd className="text-xs tabular-nums font-semibold">{formatNumber(row.revenue)}</CcTd>
          <CcTd className="text-xs tabular-nums">{formatNumber(row.total_cost)}</CcTd>
          <CcTd className="text-xs tabular-nums font-bold">
            {formatNumber(row.margin)}
          </CcTd>
          <CcTd className="text-xs tabular-nums">
            {row.margin_pct === null ? "—" : `${formatNumber(row.margin_pct)}%`}
          </CcTd>
          <CcTd>
            <CcPill tone={STATE_TONE[row.state] || "neutral"}>
              {row.state_label}
            </CcPill>
          </CcTd>
        </CcTr>
        {open && (
          <CcTr className="bg-cc-surface-2/20">
            <CcTd colSpan={6} className="p-4">
              <div className="grid gap-6 md:grid-cols-2">
                <div>
                  <h4 className="mb-2 text-xs font-bold text-cc-text">مصادرُ الأرقام</h4>
                  <ul className="space-y-1.5 text-xs text-cc-text-muted">
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
                    <p className="mt-3 text-xs text-cc-text-muted">لا وحداتٍ محتسَبةً لموظّفٍ هذا الشهر.</p>
                  ) : (
                    <div className="mt-3">
                      <CcTable>
                        <CcThead>
                          <tr>
                            <CcTh>الموظّف</CcTh>
                            <CcTh>وحدات</CcTh>
                            <CcTh>تكلفةُ الوحدة</CcTh>
                            <CcTh>التكلفة</CcTh>
                          </tr>
                        </CcThead>
                        <tbody>
                          {row.contributors.map((contributor) => (
                            <CcTr key={contributor.employee_id}>
                              <CcTd className="tabular-nums font-medium">#{contributor.employee_id}</CcTd>
                              <CcTd className="tabular-nums">{formatNumber(contributor.units)}</CcTd>
                              <CcTd className="tabular-nums">{formatNumber(contributor.unit_cost)}</CcTd>
                              <CcTd className="tabular-nums font-semibold">{formatNumber(contributor.cost)}</CcTd>
                            </CcTr>
                          ))}
                        </tbody>
                      </CcTable>
                    </div>
                  )}
                </div>
                <div>
                  <h4 className="mb-2 text-xs font-bold text-cc-text">اقتراحاتٌ للنظر — لا تُنفَّذ آلياً</h4>
                  {row.suggestions.length === 0 ? (
                    <p className="text-xs text-cc-text-muted">لا اقتراحَ لهذه الشركة هذا الشهر.</p>
                  ) : (
                    <ul className="space-y-2">
                      {row.suggestions.map((suggestion) => (
                        <li key={suggestion.code} className="rounded-lg border border-cc-border bg-cc-surface p-3">
                          <p className="text-xs font-semibold text-cc-text">{suggestion.label}</p>
                          <p className="mt-0.5 text-xs text-cc-text-muted">{suggestion.reason}</p>
                          <p className="mt-1 text-[11px] text-cc-text-muted/80">
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
            </CcTd>
          </CcTr>
        )}
      </React.Fragment>
    );
  };

  return (
    <div className="space-y-6" dir="rtl">
      <CcSectionTitle
        title="ربحيّةُ العميل ومطابقةُ الخطة"
        subtitle="مؤشّرٌ تشغيليٌّ منفصلٌ عن صحّة الشركة وعن تقييم الموظّف"
        badge={board?.rows?.length}
      />

      <CcCard className="p-5">
        <div className="flex flex-wrap items-end gap-4">
          <label className="space-y-1 text-xs">
            <span className="text-cc-text-muted">السنة</span>
            <input
              type="number"
              value={year}
              onChange={(event) => setYear(Number(event.target.value))}
              className="ktra-input h-9 w-28 text-xs"
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-cc-text-muted">الشهر</span>
            <input
              type="number"
              min={1}
              max={12}
              value={month}
              onChange={(event) => setMonth(Number(event.target.value))}
              className="ktra-input h-9 w-24 text-xs"
            />
          </label>
          <label className="space-y-1 text-xs">
            {/* مُدخَلٌ لا مُشتَقّ: لا مصدرَ للنفقات المخصَّصة في المستودع، فتبقى صفراً حتى تُدخَل. */}
            <span className="text-cc-text-muted">نفقاتٌ مخصَّصة لكلّ شركة</span>
            <input
              type="number"
              min={0}
              value={expenses}
              onChange={(event) => setExpenses(Math.max(0, Number(event.target.value)))}
              className="ktra-input h-9 w-36 text-xs"
            />
          </label>
        </div>
      </CcCard>

      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-400 font-semibold" role="alert">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          <CcSkeleton variant="card" count={2} />
        </div>
      ) : !board || board.rows.length === 0 ? (
        <CcEmpty title="لا شركاتِ خدمةٍ مؤهَّلةً في هذا الشهر." />
      ) : (
        <CcTable className="min-w-[640px]">
          <CcThead>
            <tr>
              <CcTh>الشركة</CcTh>
              <CcTh>الإيراد</CcTh>
              <CcTh>التكلفة</CcTh>
              <CcTh>الهامش</CcTh>
              <CcTh>الهامش %</CcTh>
              <CcTh>الحالة</CcTh>
            </tr>
          </CcThead>
          <tbody>{board.rows.map(renderRow)}</tbody>
        </CcTable>
      )}
    </div>
  );
};

export default ProfitabilityPanel;
