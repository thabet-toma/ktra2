import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { accountingApi } from "../../services/accountingApi";
import { formatMoney } from "../../utils/formatNumber";
import { RefreshCw, Loader2, ExternalLink } from "lucide-react";

interface JournalListItem {
  id: number;
  transaction_date: string | null;
  description?: string | null;
  reference_type?: string | null;
  reference_id?: number | null;
  is_posted: boolean;
  currency_code?: string | null;
  total_debit?: string | number | null;
  lines?: Array<{ debit?: string | number; credit?: string | number }>;
}

interface Props {
  referenceType: string;
  referenceId: number;
  searchQuery?: string; // e.g. invoice number to find related supplier payments
}

export const DocumentPaymentsTab: React.FC<Props> = ({ referenceType, referenceId, searchQuery }) => {
  const navigate = useNavigate();
  const [journals, setJournals] = useState<JournalListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // First, get exact matches by reference
      const exactParams: Record<string, string> = {
        reference_type: referenceType,
        reference_id: String(referenceId),
      };
      
      // P0-5: القائمة مُرقَّمة إلزامياً — البحث المرجعي الدقيق صغير بطبيعته،
      // والبحث النصي يكتفي بأفضل 200 مطابقة (asList يفكّ غلاف results).
      const [exactData, searchData] = await Promise.all([
        accountingApi.getJournals({ ...exactParams, page_size: "200" }),
        searchQuery ? accountingApi.getJournals({ search: searchQuery, page_size: "200" }) : Promise.resolve([])
      ]);

      // Merge and deduplicate by journal ID
      const mergedMap = new Map<number, JournalListItem>();
      (exactData as JournalListItem[]).forEach(j => mergedMap.set(j.id, j));
      
      if (searchQuery) {
        (searchData as JournalListItem[]).forEach(j => {
          if (!mergedMap.has(j.id)) {
            mergedMap.set(j.id, j);
          }
        });
      }

      // Sort by date descending, then by id descending
      const sorted = Array.from(mergedMap.values()).sort((a, b) => {
        const dateA = a.transaction_date || "";
        const dateB = b.transaction_date || "";
        if (dateA !== dateB) return dateA < dateB ? 1 : -1;
        return b.id - a.id;
      });

      setJournals(sorted);
    } catch (e: any) {
      setError(e instanceof Error ? e.message : "فشل جلب الحركات المالية");
    } finally {
      setLoading(false);
    }
  }, [referenceType, referenceId, searchQuery]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8 aseel-text-soft">
        <Loader2 className="w-5 h-5 animate-spin ml-2" />
        جارٍ جلب الحركات المالية...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 m-4 rounded-lg bg-red-50 text-red-800 dark:bg-red-900/30 dark:text-red-300">
        {error}
      </div>
    );
  }

  if (journals.length === 0) {
    return (
      <div className="p-8 text-center aseel-text-soft">
        لا توجد حركات مالية مسجلة لهذا المستند حتى الآن.
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4" dir="rtl">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-lg aseel-text-ink">الحركات المالية المرتبطة</h3>
        <button onClick={load} className="p-2 hover:aseel-bg-panel rounded-full text-[var(--color-text-muted)] transition-colors" title="تحديث">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>
      
      <div className="overflow-x-auto rounded-lg border aseel-border-soft dark:aseel-border-soft">
        <table className="w-full text-sm text-right">
          <thead className="aseel-bg-panel dark:aseel-bg-panel text-xs text-[var(--color-text-muted)]">
            <tr className="border-b aseel-border-soft dark:aseel-border-soft">
              <th className="px-4 py-3 font-medium">رقم القيد</th>
              <th className="px-4 py-3 font-medium">التاريخ</th>
              <th className="px-4 py-3 font-medium">النوع</th>
              <th className="px-4 py-3 font-medium">البيان</th>
              <th className="px-4 py-3 font-medium">المبلغ</th>
              <th className="px-4 py-3 font-medium text-center">الحالة</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)] bg-[var(--color-surface)]">
            {journals.map(j => {
              const amount = Number(j.total_debit) || j.lines?.reduce((sum, l) => sum + (Number(l.debit) || 0), 0) || 0;
              return (
                <tr key={j.id} className="hover:bg-[var(--color-surface-2)] transition-colors">
                  <td className="px-4 py-3 font-mono text-xs">{j.id}</td>
                  <td className="px-4 py-3">{(j.transaction_date || "").slice(0, 10)}</td>
                  <td className="px-4 py-3 text-xs text-[var(--color-text-muted)]">{j.reference_type || "عام / يدوي"}</td>
                  <td className="px-4 py-3 max-w-xs truncate" title={j.description || ""}>{j.description || "—"}</td>
                  <td className="px-4 py-3 font-mono">
                    {formatMoney(amount)} {j.currency_code}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${
                      j.is_posted 
                        ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
                        : "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300"
                    }`}>
                      {j.is_posted ? "مرحَّل" : "مسودة"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-left">
                    <button 
                      onClick={() => navigate(`/accounting/journals/${j.id}`)}
                      className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 hover:underline"
                    >
                      <span>عرض</span>
                      <ExternalLink className="w-3 h-3" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
