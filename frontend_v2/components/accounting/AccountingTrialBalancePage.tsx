import React, { useState, useEffect, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import type { TrialBalanceRow } from "../../types/accounting";
import { Scale, Search } from "lucide-react";

export const AccountingTrialBalancePage: React.FC = () => {
  const today = new Date();
  const [start, setStart] = useState(
    `${today.getFullYear()}-01-01`
  );
  const [end, setEnd] = useState(today.toISOString().split("T")[0]);
  const [unposted, setUnposted] = useState(false);
  const [rows, setRows] = useState<TrialBalanceRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const params: Record<string, string> = { start_date: start, end_date: end };
      if (unposted) params.include_unposted = "true";
      const data = await accountingApi.getTrialBalance(params);
      setRows(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التقرير");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [start, end, unposted]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const td = rows.reduce((s, r) => s + Number(r.total_debit), 0);
  const tc = rows.reduce((s, r) => s + Number(r.total_credit), 0);

  const fmt = (n: number) =>
    n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 p-4 bg-gradient-to-l from-indigo-900 to-slate-900 text-white rounded-xl">
        <Scale className="w-8 h-8 text-indigo-300" />
        <div>
          <h1 className="text-lg font-bold">ميزان المراجعة</h1>
          <p className="text-xs text-indigo-200">أرصدة حسب الحساب</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 items-end bg-white dark:bg-gray-800 p-4 rounded-xl border border-gray-200 dark:border-gray-700">
        <div>
          <label className="block text-xs text-gray-500 mb-1">من</label>
          <input
            type="date"
            className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">إلى</label>
          <input
            type="date"
            className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </div>
        <label className="flex items-center gap-2 text-sm pb-2">
          <input
            type="checkbox"
            checked={unposted}
            onChange={(e) => setUnposted(e.target.checked)}
          />
          تضمين غير المرحّل
        </label>
        <button
          type="button"
          onClick={fetchData}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm"
        >
          <Search className="w-4 h-4" />
          تحديث
        </button>
      </div>

      {err && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 text-sm">
          {err}
        </div>
      )}

      {loading ? (
        <div className="py-16 text-center text-gray-500">جاري التحميل…</div>
      ) : (
        <div className="overflow-x-auto bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                <th className="text-right p-3">كود</th>
                <th className="text-right p-3">اسم الحساب</th>
                <th className="text-right p-3">مدين</th>
                <th className="text-right p-3">دائن</th>
                <th className="text-right p-3">الرصيد</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className="border-t border-gray-100 dark:border-gray-700"
                >
                  <td className="p-3 font-mono">{r.code}</td>
                  <td className="p-3">{r.name}</td>
                  <td className="p-3">{fmt(Number(r.total_debit))}</td>
                  <td className="p-3">{fmt(Number(r.total_credit))}</td>
                  <td className="p-3 font-medium">{fmt(Number(r.balance))}</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-gray-100 dark:bg-gray-900/40 font-semibold">
              <tr>
                <td colSpan={2} className="p-3">
                  الإجمالي
                </td>
                <td className="p-3">{fmt(td)}</td>
                <td className="p-3">{fmt(tc)}</td>
                <td className="p-3">{fmt(td - tc)}</td>
              </tr>
            </tfoot>
          </table>
          {rows.length === 0 && (
            <p className="p-8 text-center text-gray-500">لا بيانات</p>
          )}
        </div>
      )}
    </div>
  );
};
