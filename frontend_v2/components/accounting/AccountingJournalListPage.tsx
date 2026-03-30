import React, { useEffect, useState, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import {
  Plus,
  Search,
  CheckCircle,
  FileText,
  Loader2,
} from "lucide-react";

export interface JournalListItem {
  id: number;
  transaction_date: string | null;
  description?: string | null;
  reference_id?: number | null;
  is_posted: boolean;
}

interface Props {
  onNew: () => void;
  onOpen: (id: number) => void;
}

export const AccountingJournalListPage: React.FC<Props> = ({
  onNew,
  onOpen,
}) => {
  const [rows, setRows] = useState<JournalListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [posting, setPosting] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [postErr, setPostErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const data = (await accountingApi.getJournals()) as JournalListItem[];
      setRows(data.sort((a, b) => b.id - a.id));
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handlePost = async (id: number) => {
    if (
      !confirm(
        "ترحيل القيد؟ no يمكن التعديل بعد الترحيل."
      )
    )
      return;
    setPostErr(null);
    setPosting(id);
    try {
      await accountingApi.postJournal(id);
      setRows((r) =>
        r.map((j) => (j.id === id ? { ...j, is_posted: true } : j))
      );
    } catch (e: unknown) {
      setPostErr(e instanceof Error ? e.message : "فشل الترحيل");
    } finally {
      setPosting(null);
    }
  };

  const filtered = rows.filter(
    (j) =>
      !search.trim() ||
      String(j.id).includes(search) ||
      (j.description || "").toLowerCase().includes(search.toLowerCase()) ||
      String(j.reference_id || "").includes(search)
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-gradient-to-l from-slate-800 to-slate-900 text-white rounded-xl shadow">
        <div className="flex items-center gap-3">
          <FileText className="w-8 h-8 text-amber-400" />
          <div>
            <h1 className="text-lg font-bold">دفتر اليومية</h1>
            <p className="text-xs text-slate-400">القيود والترحيل</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onNew}
          className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-500 rounded-lg text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          قيد جديد
        </button>
      </div>

      <div className="flex flex-wrap gap-2 items-center bg-white dark:bg-gray-800 p-3 rounded-xl border border-gray-200 dark:border-gray-700">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            placeholder="بحث برقم القيد أو البيان…"
            className="w-full border rounded-lg pr-10 pl-3 py-2 text-sm dark:bg-gray-900 dark:border-gray-600"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {err && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm">
          {err}
        </div>
      )}
      {postErr && (
        <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 text-amber-900 dark:text-amber-200 text-sm border border-amber-200 dark:border-amber-800">
          {postErr}
        </div>
      )}

      {loading ? (
        <div className="py-20 text-center text-gray-500">جاري التحميل…</div>
      ) : (
        <div className="overflow-x-auto bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50 text-gray-600 dark:text-gray-400">
              <tr>
                <th className="text-right p-3 font-semibold">رقم</th>
                <th className="text-right p-3 font-semibold">التاريخ</th>
                <th className="text-right p-3 font-semibold">البيان</th>
                <th className="text-right p-3 font-semibold">المرجع</th>
                <th className="text-right p-3 font-semibold">الحالة</th>
                <th className="text-right p-3 font-semibold w-40">إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((j) => (
                <tr
                  key={j.id}
                  className="border-t border-gray-100 dark:border-gray-700 hover:bg-gray-50/80 dark:hover:bg-gray-900/30"
                >
                  <td className="p-3 font-mono">{j.id}</td>
                  <td className="p-3">{j.transaction_date || "—"}</td>
                  <td className="p-3 max-w-xs truncate">
                    {j.description || "—"}
                  </td>
                  <td className="p-3">{j.reference_id ?? "—"}</td>
                  <td className="p-3">
                    {j.is_posted ? (
                      <span className="text-emerald-600 dark:text-emerald-400 text-xs font-medium">
                        مرحّل
                      </span>
                    ) : (
                      <span className="text-amber-600 text-xs font-medium">
                        مسودة
                      </span>
                    )}
                  </td>
                  <td className="p-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => onOpen(j.id)}
                      className="px-2 py-1 text-xs rounded-lg bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200"
                    >
                      فتح
                    </button>
                    {!j.is_posted && (
                      <button
                        type="button"
                        disabled={posting === j.id}
                        onClick={() => handlePost(j.id)}
                        className="flex items-center gap-1 px-2 py-1 text-xs rounded-lg bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200 disabled:opacity-50"
                      >
                        {posting === j.id ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <CheckCircle className="w-3 h-3" />
                        )}
                        ترحيل
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <p className="p-8 text-center text-gray-500">لا قيود</p>
          )}
        </div>
      )}
    </div>
  );
};
