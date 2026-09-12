import React, { useCallback, useEffect, useState } from "react";
import { Trophy } from "lucide-react";

import { getChampionsBoard, type ChampionsBoard } from "../../services/platformEmployeeSpaceApi";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";

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
      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="ml-auto flex items-center gap-2">
          <Trophy className="h-4 w-4 text-amber-500" />
          <h2 className="text-sm font-bold text-slate-800">KTRA Champions</h2>
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
      </div>

      {error && (
        <div className="flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
          <span>{error}</span>
          <button type="button" onClick={() => void load()} className="rounded-lg bg-rose-100 px-3 py-1 text-[11px] font-bold hover:bg-rose-200">
            إعادة المحاولة
          </button>
        </div>
      )}

      {loading ? (
        <div className="py-10 text-center text-xs text-slate-400">جاري التحميل...</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {(board?.categories ?? []).map((category) => (
            <section key={category.category} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <h3 className="mb-2 text-xs font-bold text-slate-700">{category.category_label}</h3>
              {category.entries.length === 0 ? (
                <p className="text-[11px] text-slate-400">لا مرشّحين بحدّ العينة هذا الشهر.</p>
              ) : (
                <ol className="space-y-2">
                  {category.entries.map((entry, index) => (
                    <li key={entry.employee_id} className="rounded-lg bg-slate-50 p-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-slate-800">
                          <span className="ml-1">{medal(index)}</span>
                          {entry.employee_name}
                        </span>
                        <span className="text-xs font-bold text-slate-700">
                          {formatNumber(entry.value)} {category.unit}
                        </span>
                      </div>
                      <p className="mt-0.5 text-[10px] text-slate-500">{entry.evidence}</p>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          ))}
        </div>
      )}
    </div>
  );
};

export default ChampionsPanel;
