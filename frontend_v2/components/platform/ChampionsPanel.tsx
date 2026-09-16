import React, { useCallback, useEffect, useState } from "react";
import { Trophy } from "lucide-react";

import { getChampionsBoard, type ChampionsBoard } from "../../services/platformEmployeeSpaceApi";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { CcAvatar, CcCard, CcEmpty, CcSectionTitle, CcSkeleton } from "./ui";

const now = new Date();

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "هذه اللوحة لموظفي عمليات المنصة فقط.", "تعذّر تحميل اللوحة.");

/**
 * لوحةُ KTRA Champions (§١٠) — **إيجابيّةٌ فقط**.
 *
 * ما لا تعرضه بنصّ المواصفة: لا رواتب، ولا قيمَ عمولات (الاكتسابُ عددُ عملاء)، ولا
 * أسماءَ عملاء، ولا ترتيبَ للأسوأ — الخادمُ يعيد القمّةَ وحدَها، والواجهةُ لا
 * تُكمل القائمةَ ولا تعرض مرتبةً لمن ليس عليها.
 */
export const ChampionsPanel: React.FC = () => {
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [board, setBoard] = useState<ChampionsBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setBoard(await getChampionsBoard(year, month));
    } catch (cause) {
      setError(displayError(cause));
      setBoard(null);
    } finally {
      setLoading(false);
    }
  }, [year, month]);

  useEffect(() => { void load(); }, [load]);

  const medal = (index: number): string => (index === 0 ? "🥇" : index === 1 ? "🥈" : "🥉");

  return (
    <div className="space-y-4" dir="rtl">
      <CcCard className="p-4 flex flex-wrap items-end gap-3">
        <div className="ml-auto flex items-center gap-2">
          <Trophy className="h-5 w-5 text-amber-400" />
          <CcSectionTitle title="KTRA Champions" />
        </div>
        <label className="space-y-1 text-xs">
          <span className="text-cc-text-muted">السنة</span>
          <input
            type="number"
            value={year}
            onChange={(event) => setYear(Number(event.target.value))}
            className="w-24 rounded-lg bg-cc-bg border border-cc-border text-cc-text px-2.5 py-1.5 text-xs focus:outline-none focus:border-sky-500"
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
            className="w-20 rounded-lg bg-cc-bg border border-cc-border text-cc-text px-2.5 py-1.5 text-xs focus:outline-none focus:border-sky-500"
          />
        </label>
      </CcCard>

      {error && (
        <CcCard tone="danger" className="flex items-center justify-between p-3 text-xs">
          <span className="text-rose-400 font-semibold">{error}</span>
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 px-3 py-1 text-[11px] font-bold transition-colors"
          >
            إعادة المحاولة
          </button>
        </CcCard>
      )}

      {loading ? (
        <CcSkeleton variant="card" count={3} />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {(board?.categories ?? []).map((category) => (
            <CcCard key={category.category} className="p-4 space-y-3">
              <h3 className="text-xs sm:text-sm font-bold text-cc-text">{category.category_label}</h3>
              {category.entries.length === 0 ? (
                <CcEmpty title="لا مرشّحين بحدّ العينة هذا الشهر." className="py-6" />
              ) : (
                <ol className="space-y-2">
                  {category.entries.map((entry, index) => (
                    <li
                      key={entry.employee_id}
                      className="flex items-center justify-between gap-3 p-2.5 rounded-lg border border-cc-border bg-cc-surface-2 hover:bg-cc-surface transition-colors"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <span className="text-base shrink-0">{medal(index)}</span>
                        <CcAvatar name={entry.employee_name} size="sm" />
                        <div className="min-w-0">
                          <p className="text-xs font-semibold text-cc-text truncate">{entry.employee_name}</p>
                          <p className="text-[10px] text-cc-text-muted truncate">{entry.evidence}</p>
                        </div>
                      </div>
                      <div className="shrink-0 text-left">
                        <span className="text-xs font-bold text-sky-400">
                          {formatNumber(entry.value)}
                        </span>
                        <span className="text-[10px] text-cc-text-muted mr-1">
                          {category.unit}
                        </span>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </CcCard>
          ))}
        </div>
      )}
    </div>
  );
};

export default ChampionsPanel;
