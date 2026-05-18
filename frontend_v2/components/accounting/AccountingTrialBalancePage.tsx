import React, { useState, useEffect, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import type { TrialBalanceResponse, TrialBalanceRow } from "../../types/accounting";
import { Scale, Search, CheckCircle2, AlertTriangle } from "lucide-react";

export const AccountingTrialBalancePage: React.FC = () => {
  const today = new Date();
  const [start, setStart] = useState(`${today.getFullYear()}-01-01`);
  const [end, setEnd] = useState(today.toISOString().split("T")[0]);
  const [unposted, setUnposted] = useState(false);
  const [showZero, setShowZero] = useState(false);
  const [data, setData] = useState<TrialBalanceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [search, setSearch] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const params: Record<string, string> = {
        start_date: start,
        end_date: end,
        show_all: showZero ? "true" : "false",
      };
      if (unposted) params.include_unposted = "true";
      const resp = await accountingApi.getTrialBalance(params);
      // backward compat: legacy response was an array
      if (Array.isArray(resp)) {
        setData({
          start_date: start,
          end_date: end,
          rows: resp as TrialBalanceRow[],
          totals: {
            period_debit: 0,
            period_credit: 0,
            closing_debit: 0,
            closing_credit: 0,
            balanced: true,
            period_difference: 0,
            closing_difference: 0,
          },
        });
      } else {
        setData(resp as TrialBalanceResponse);
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التقرير");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [start, end, unposted, showZero]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const fmt = (n: number | undefined) =>
    (Number(n) || 0).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

  const rows = (data?.rows || []).filter((r) => {
    if (typeFilter && (r.account_type || "") !== typeFilter) return false;
    if (search) {
      const s = search.toLowerCase();
      if (
        !String(r.code || "").toLowerCase().includes(s) &&
        !String(r.name || "").toLowerCase().includes(s)
      )
        return false;
    }
    return true;
  });

  const types = Array.from(
    new Set((data?.rows || []).map((r) => r.account_type).filter(Boolean)),
  ) as string[];

  const totals = data?.totals;
  const pd = totals?.period_debit || 0;
  const pc = totals?.period_credit || 0;
  const cd = totals?.closing_debit || 0;
  const cc = totals?.closing_credit || 0;

  return (
    <div className="space-y-4" dir="rtl">
      <div className="flex flex-wrap items-center gap-3 p-4 bg-gradient-to-l from-[var(--color-primary)] to-slate-900 text-white rounded-xl">
        <Scale className="w-8 h-8 text-[var(--color-primary)]" />
        <div className="flex-1">
          <h1 className="text-lg font-bold">ميزان المراجعة</h1>
          <p className="text-xs text-[var(--color-primary)]">
            افتتاحي + حركة الفترة + ختامي — مع التحقق من التوازن
          </p>
        </div>
        {totals && (
          <div
            className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium ${
              totals.balanced
                ? "bg-emerald-500/20 text-emerald-200"
                : "bg-red-500/20 text-red-200"
            }`}
          >
            {totals.balanced ? (
              <CheckCircle2 className="w-4 h-4" />
            ) : (
              <AlertTriangle className="w-4 h-4" />
            )}
            {totals.balanced ? "متوازن" : `فرق ${fmt(totals.period_difference)}`}
          </div>
        )}
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
        <div>
          <label className="block text-xs text-gray-500 mb-1">نوع</label>
          <select
            className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600 min-w-[120px]"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">الكل</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1 min-w-[200px]">
          <label className="block text-xs text-gray-500 mb-1">بحث</label>
          <input
            type="text"
            placeholder="كود أو اسم..."
            className="w-full border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
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
        <label className="flex items-center gap-2 text-sm pb-2">
          <input
            type="checkbox"
            checked={showZero}
            onChange={(e) => setShowZero(e.target.checked)}
          />
          عرض الحسابات بدون حركة
        </label>
        <button
          type="button"
          onClick={fetchData}
          className="flex items-center gap-2 px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg text-sm"
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
                <th rowSpan={2} className="text-right p-3 border-b">
                  كود
                </th>
                <th rowSpan={2} className="text-right p-3 border-b">
                  الحساب
                </th>
                <th rowSpan={2} className="text-center p-3 border-b">
                  النوع
                </th>
                <th colSpan={2} className="text-center p-2 border-b bg-slate-100 dark:bg-slate-900/40">
                  الرصيد الافتتاحي
                </th>
                <th colSpan={2} className="text-center p-2 border-b bg-blue-50 dark:bg-blue-900/20">
                  حركة الفترة
                </th>
                <th colSpan={2} className="text-center p-2 border-b bg-emerald-50 dark:bg-emerald-900/20">
                  الرصيد الختامي
                </th>
              </tr>
              <tr className="text-xs">
                <th className="text-right p-2 bg-slate-100 dark:bg-slate-900/40">مدين</th>
                <th className="text-right p-2 bg-slate-100 dark:bg-slate-900/40">دائن</th>
                <th className="text-right p-2 bg-blue-50 dark:bg-blue-900/20">مدين</th>
                <th className="text-right p-2 bg-blue-50 dark:bg-blue-900/20">دائن</th>
                <th className="text-right p-2 bg-emerald-50 dark:bg-emerald-900/20">مدين</th>
                <th className="text-right p-2 bg-emerald-50 dark:bg-emerald-900/20">دائن</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const pdN = r.period_debit ?? r.total_debit ?? 0;
                const pcN = r.period_credit ?? r.total_credit ?? 0;
                return (
                  <tr
                    key={r.id}
                    className="border-t border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-900/40"
                  >
                    <td className="p-2 font-mono">{r.code}</td>
                    <td className="p-2">{r.name}</td>
                    <td className="p-2 text-center text-xs text-gray-500">
                      {r.account_type}
                    </td>
                    <td className="p-2 text-right">{fmt(r.opening_debit)}</td>
                    <td className="p-2 text-right">{fmt(r.opening_credit)}</td>
                    <td className="p-2 text-right">{fmt(pdN)}</td>
                    <td className="p-2 text-right">{fmt(pcN)}</td>
                    <td className="p-2 text-right font-medium text-emerald-700 dark:text-emerald-400">
                      {fmt(r.closing_debit)}
                    </td>
                    <td className="p-2 text-right font-medium text-rose-700 dark:text-rose-400">
                      {fmt(r.closing_credit)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
            {totals && rows.length > 0 && (
              <tfoot className="bg-gray-100 dark:bg-gray-900/40 font-semibold">
                <tr>
                  <td colSpan={5} className="p-3 text-right">
                    الإجمالي
                  </td>
                  <td className="p-2 text-right">{fmt(pd)}</td>
                  <td className="p-2 text-right">{fmt(pc)}</td>
                  <td className="p-2 text-right">{fmt(cd)}</td>
                  <td className="p-2 text-right">{fmt(cc)}</td>
                </tr>
              </tfoot>
            )}
          </table>
          {rows.length === 0 && (
            <p className="p-8 text-center text-gray-500">لا بيانات</p>
          )}
        </div>
      )}
    </div>
  );
};
